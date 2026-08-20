"""The facade: the one object a caller needs, and where every branch decided upstream falls due.

Both ports and the clock are constructor arguments. There is no module-level client, no
global state and no default that reaches the network implicitly — this module imports no
adapter at all, so a `Healer` that was never handed a `StudioClient` can reach nothing.

Four branches meet here, each already argued by the feature that found it and none of them
re-derived:

- **A gate call that failed is not promoted.** `heal.heal` and `heal.approve` write their
  row and then re-raise, so there is no `failed` event to branch on: the catch itself is
  the branch, and the row is already written by the time it happens. The recorded row is
  returned rather than the error re-raised, because one collector the CLI refused must not
  end a run over the other twenty-nine.
- **A verification the target refused is retried, never rolled back.** The heal was never
  actually tested, so rolling back would discard a heal that may be fine and publish a
  non-regression failure nobody measured.
- **A report that came back false is refused**: one heal event saying so, and the
  stored known-good shape left exactly where it was.
- **Ambiguous error codes are retried once.** `detect` judges one run and stays stateless,
  so the loop belongs here. Codes that come back a second time are no longer plausibly
  transient, and become extraction evidence.

What the facade adds beyond composition is the known-good shape: it is captured when a run
judges healthy and again when a heal is promoted, and left untouched when one is rolled
back. That is this package's only record of "what the collector currently is", and it is
what `collectors.schema_version` is to the application that consumes us — bdheal does not
own collectors, so it does not own that column either.
"""

from collections.abc import Sequence
from typing import Any

from bdheal.diagnose import Diagnosis, diagnose
from bdheal.errors import StudioError, VerificationIncompleteError
from bdheal.models import (
    CollectorSpec,
    DetectVerdict,
    HealEvent,
    RunResult,
    VerifyReport,
    latest_settled,
)
from bdheal.ports import Clock, HealStore, StudioClient
from bdheal.skeleton import skeleton_hash
from bdheal.vocabulary import HealStatus, UNTRUSTWORTHY_SAMPLE_CODES

# Aliased where the facade's own method shares the use case's name.
from bdheal.detect import capture_baseline, detect as run_detectors
from bdheal.heal import approve, heal as request_heal
from bdheal.verify import verify as score_layouts

# One retry, and exactly one. Bright Data classes the ambiguous codes as "either side's
# fault — debug required", and a single re-fetch is all it takes to tell a transient
# refusal from a standing one: a code that comes back a second time is not plausibly
# transient. Retrying further would keep a permanently dead target in a loop, paying for
# every pass and never healing; not retrying at all would make the distinction unmakeable
# and heal against a page that was merely slow.
AMBIGUOUS_RETRIES = 1

# The same shape for a verification the target refused: score it again once, then let the
# error stand. A refused sample is not a regression, and `VerifyReport` has no value for
# "not measured", so the caller excludes the case rather than publishing a check nobody
# performed.
VERIFICATION_PASSES = 2

# A heal has to recover something on the layout it was healed for. The non-regression pass
# cannot see this on its own: a collector that extracts nothing regresses nothing, so it
# scores perfectly against the old layout.
NO_FIELDS_RECOVERED = 0.0


class Healer:
    """Run, detect, heal, verify — the self-healing loop over one collector."""

    def __init__(self, studio: StudioClient, store: HealStore, clock: Clock) -> None:
        self._studio = studio
        self._store = store
        self._clock = clock

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Run the collector and return validated rows alongside per-row errors."""
        return self._studio.run(spec, urls)

    def detect(self, spec: CollectorSpec, result: RunResult) -> DetectVerdict:
        """Judge the run against its stored baseline. Updates the baseline when healthy.

        Ambiguous codes are retried before they are believed. `detect` sees one run and
        cannot tell a target that refused from a collector that asked wrongly, so the loop
        runs the collector again and calls the codes evidence only if the same ones come
        back. The retry uses the collector's own anchors, since a `RunResult` does not
        carry the URLs it came from.
        """
        verdict = self._judge(spec, result)
        for _ in range(AMBIGUOUS_RETRIES):
            if not verdict.ambiguous_codes:
                return verdict
            verdict, persistent = self._retry(spec, verdict)
            if persistent:
                return _escalate(verdict, persistent)
        return verdict

    def heal(self, spec: CollectorSpec, verdict: DetectVerdict) -> HealEvent:
        """Diagnose the verdict, heal in place, and record the outcome.

        A gate call that failed comes back as its own recorded row — unpromoted, carrying
        the reason — rather than as an exception, so a caller driving many collectors reads
        one failure as a result instead of losing the run to it.
        """
        diagnosis = diagnose(spec, verdict)
        if diagnosis is None:
            raise ValueError(f"{spec.collector_id} is not broken, so there is nothing to heal")
        try:
            return self._gate(spec, diagnosis)
        except StudioError:
            recorded = self._settled(spec.collector_id)
            if recorded is None:
                raise
            return recorded

    def verify(
        self,
        spec: CollectorSpec,
        golden: Sequence[dict[str, Any]],
        old_layout_url: str,
    ) -> VerifyReport:
        """Score the healed collector against golden records and the old layout.

        The score decides the heal: a report that clears both halves is promoted, anything
        else is refused, and either way one heal event records which it was. Refusal is a
        verdict, not an undo — see `_settle`.
        """
        report = self._score(spec, golden, old_layout_url)
        self._settle(spec, report)
        return report

    def _judge(self, spec: CollectorSpec, result: RunResult) -> DetectVerdict:
        """One detect pass, with the page fetched so the skeleton signal has something to read.

        A healthy, whole run becomes the new known-good shape. An incomplete one never
        does: a baseline taken from a sample the target half-refused would teach the volume
        detectors that the truncation is normal.
        """
        page_html = self._page_html(spec)
        verdict = run_detectors(spec, result, self._store, page_html)
        if not verdict.broken:
            self._capture(spec, result, page_html)
        return verdict

    def _retry(
        self, spec: CollectorSpec, verdict: DetectVerdict
    ) -> tuple[DetectVerdict, tuple[str, ...]]:
        """Judge a second run, and report which of the ambiguous codes came back with it."""
        retried = self._judge(spec, self.run(spec, spec.anchor_urls))
        persistent = tuple(
            code for code in retried.ambiguous_codes if code in verdict.ambiguous_codes
        )
        return retried, persistent

    def _gate(self, spec: CollectorSpec, diagnosis: Diagnosis) -> HealEvent:
        """Heal, then approve if the CLI left the heal waiting at the gate."""
        pending = request_heal(spec, diagnosis, self._studio, self._store, self._clock)
        if pending.status is not HealStatus.AWAITING_APPROVAL:
            return pending
        return approve(spec, pending, self._studio, self._store, self._clock)

    def _score(
        self, spec: CollectorSpec, golden: Sequence[dict[str, Any]], old_layout_url: str
    ) -> VerifyReport:
        """Score the layouts, giving a refused pass one more go before the error stands.

        The final pass is deliberately unguarded, so a target that keeps refusing reaches
        the caller as the error it is rather than as a regression that was never observed.
        """
        for attempt in range(1, VERIFICATION_PASSES):
            retried = self._pass_or_none(spec, golden, old_layout_url, attempt)
            if retried is not None:
                return retried
        return self._pass(spec, golden, old_layout_url, VERIFICATION_PASSES)

    def _pass_or_none(
        self,
        spec: CollectorSpec,
        golden: Sequence[dict[str, Any]],
        old_layout_url: str,
        attempt: int,
    ) -> VerifyReport | None:
        """One scoring pass, or `None` when the target refused it and a retry is owed."""
        try:
            return self._pass(spec, golden, old_layout_url, attempt)
        except VerificationIncompleteError:
            return None

    def _pass(
        self,
        spec: CollectorSpec,
        golden: Sequence[dict[str, Any]],
        old_layout_url: str,
        attempt: int,
    ) -> VerifyReport:
        """One scoring pass, numbered so the report says which attempt produced it."""
        return score_layouts(
            spec, golden, old_layout_url, self._studio, self._clock, attempts=attempt
        )

    def _settle(self, spec: CollectorSpec, report: VerifyReport) -> None:
        """Promote or refuse: one heal event either way, the baseline only on a promotion.

        A heal that is not promoted leaves the stored known-good shape exactly where it was.
        Moving it for a heal nobody kept would tell the next run that the break is the new
        normal.

        **This does not undo the heal on Bright Data.** `heal` runs with `--auto-save`, so
        the new template is already live, and `approve` refuses anything not still waiting
        at the gate — by the time verification has a verdict there is nothing pending to
        reject, and the API exposes no way to restore a previous template. So "not promoted"
        is this package's judgement of a change it cannot reverse: the collector stays
        healed and the record says the heal was not kept. Anything driving many collectors
        has to treat a refused heal as a permanent modification.
        """
        promoted = _promotable(report)
        self._store.save_heal_event(self._settlement(spec, report, promoted=promoted))
        if promoted:
            self._remember(spec)

    def _settlement(
        self, spec: CollectorSpec, report: VerifyReport, *, promoted: bool
    ) -> HealEvent:
        """The row recording what verification decided, carrying the heal's audit forward."""
        outcome: dict[str, Any] = {
            "id": None,
            "status": HealStatus.DONE if promoted else HealStatus.REJECTED,
            "created_at": self._clock.now(),
            "promoted": promoted,
            "error": None if promoted else _not_promoted_reason(report),
        }
        healed = self._settled(spec.collector_id)
        if healed is None:
            return HealEvent(collector_id=spec.collector_id, **outcome)
        return healed.model_copy(update=outcome)

    def _settled(self, collector_id: str) -> HealEvent | None:
        """The terminal-most heal row: a gate cycle is two rows, so a count is not a cycle count."""
        return latest_settled(self._store.heal_events(collector_id))

    def _remember(self, spec: CollectorSpec) -> None:
        """Record the promoted collector's shape as the new known-good one.

        It costs one confirming run, and skipping it costs far more: the stored skeleton
        hash still describes the layout that broke, so the next detect would fire on it,
        heal again, and keep doing so for as long as the collector is scheduled.
        """
        self._capture(spec, self.run(spec, spec.anchor_urls), self._page_html(spec))

    def _capture(self, spec: CollectorSpec, result: RunResult, page_html: str) -> None:
        """Store this run as the collector's known-good shape — if the run was whole.

        The guard belongs here, not at the call sites. A baseline taken from a sample the
        target half-refused teaches the volume detectors that the truncation is normal, so
        the next genuine break in row count or field extraction does not fire. `_judge`
        checked this; `_remember` — the post-promotion confirming run — did not, which left
        exactly one path able to poison the baseline it had just healed.
        """
        if any(error.error_code in UNTRUSTWORTHY_SAMPLE_CODES for error in result.errors):
            return
        self._store.save_baseline(
            capture_baseline(
                result,
                list(spec.row_schema.model_fields),
                self._clock.now(),
                skeleton_hash(page_html),
            )
        )

    def _page_html(self, spec: CollectorSpec) -> str:
        """The collector's first anchor as the page stands now — the skeleton signal's input."""
        return self._studio.fetch_html(spec.anchor_urls[0])


def _escalate(verdict: DetectVerdict, codes: tuple[str, ...]) -> DetectVerdict:
    """Ambiguous codes that survived a retry, promoted to break evidence.

    No signal is fabricated. None of the four detectors saw this, and inventing one would
    tell the benchmark's coverage matrix that a detector caught what the loop caught. The
    verdict is broken with the codes named, which diagnose renders under the generic
    template — the honest template for a cause no single symptom narrowed.
    """
    return verdict.model_copy(
        update={
            "broken": True,
            "retry_requested": False,
            "reason": (
                f"{', '.join(codes)} came back after a retry, so the codes are extraction "
                "evidence rather than a target-side refusal"
            ),
        }
    )


def _promotable(report: VerifyReport) -> bool:
    """Whether the report justifies keeping the heal.

    Both halves have to hold. The old layout must still yield every golden field, which
    `verify` has already applied its floor to, and the healed layout must have recovered
    something: a collector that extracts nothing regresses nothing, so non-regression
    alone would promote a heal that did no work.
    """
    return report.non_regression_passed and report.field_accuracy > NO_FIELDS_RECOVERED


def _not_promoted_reason(report: VerifyReport) -> str:
    """Why the heal was not kept, in numbers alone: no page content, no URL, no credential (G6)."""
    outcome = "passed" if report.non_regression_passed else "failed"
    return (
        f"not promoted after verification: field accuracy {report.field_accuracy}, "
        f"non-regression {outcome}"
    )
