"""The four break detectors, and the throttling policy that keeps them honest.

Nothing in this module names a problem domain: it compares this run against the stored
baseline and against the caller's schema, and that is all it knows. History is read
through the `HealStore` port only — detect never touches a database or a network.

One line governs the whole module: **extraction problems justify a heal; target-side
problems justify a retry; neither justifies silence.**

So a row carrying a target-side or ambiguous `error_code` — `rate_limit`, but equally
blocked, captcha'd, timed out, or a `dead_page` one run cannot attribute — makes the
sample incomplete: the volume-based detectors record `INCONCLUSIVE`, a retry is
requested, and the observed codes are named in the reason (resolved Q3, widened after F6
verification found a run half-refused with `blocked` coming back silent). Healing cannot
fix a refused fetch, so none of that proposes a heal.

A code Bright Data attributes to the scraper itself is the other half, and it is not an
exception to the rule but the rule's other side: retrying reproduces it exactly, so the
sample is whole and the row is evidence about the extractor. A row that came back and
produced no usable data reads the same way — the caller's schema rejected it, or it was
not an object at all. Either stands as break evidence whatever happened to its siblings.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bdheal.models import (
    Baseline,
    CollectorSpec,
    DetectVerdict,
    RowError,
    RunResult,
    Signal,
    fired_signals,
)
from bdheal.ports import HealStore

# Aliased because `capture_baseline` takes a `skeleton_hash` value and the two would
# otherwise share a name.
from bdheal.skeleton import skeleton_hash as structural_hash
from bdheal.vocabulary import (
    AMBIGUOUS_CODES,
    UNTRUSTWORTHY_SAMPLE_CODES,
    THROTTLE_CODES,
    SignalKind,
    SignalOutcome,
)

# How an incomplete sample is announced. Throttling gets its own word because it is the
# one target-side failure that clears up on its own; every other code reads the same way
# to this module and is told apart by the code named alongside it.
THROTTLED_LABEL = "throttled"
INCOMPLETE_LABEL = "incomplete sample"

# How far a field's null rate must climb above its baseline before that counts as a
# break. Half the sample losing a field it always carried is a collector that stopped
# extracting; anything gentler is a page with gaps in it, and a false break here costs
# real credits and can promote a collector fitted to bad data.
NULL_RATE_SPIKE = 0.5


@dataclass(frozen=True, slots=True)
class _TargetSide:
    """The rows the target itself refused, and the codes it gave for refusing them.

    A count of zero means the sample is whole and the volume detectors may speak. Never
    leaves this module, so it is a dataclass rather than a boundary model.
    """

    count: int
    codes: tuple[str, ...]


def detect(
    spec: CollectorSpec,
    result: RunResult,
    store: HealStore,
    page_html: str | None = None,
) -> DetectVerdict:
    """Judge one run against its baseline. `page_html` enables the skeleton signal.

    A collector with no stored baseline is never broken — there is nothing to compare
    against, and a first run reporting a break would be noise.
    """
    baseline = store.baseline(spec.collector_id)
    target = _target_side(result)
    fields = list(spec.row_schema.model_fields)
    candidates = (
        _schema_signal(result.errors, len(result.rows)),
        _zero_rows_signal(result, baseline, target),
        _skeleton_signal(page_html, baseline),
        _null_rate_signal(result, baseline, fields, target),
    )
    signals = [signal for signal in candidates if signal is not None]
    fired = fired_signals(signals)
    return DetectVerdict(
        broken=bool(fired),
        signals=signals,
        incomplete=bool(target.count),
        retry_requested=bool(target.count),
        ambiguous_codes=tuple(code for code in target.codes if code in AMBIGUOUS_CODES),
        reason=_reason(fired, target),
    )


def _target_side(result: RunResult) -> _TargetSide:
    """What the target refused, by count and by code.

    Only codes in `TARGET_REFUSAL_CODES` count. A code alone is not enough: real payloads
    carry `dead_page` and `parse_error`, which are the collector's own faults — a retry
    reproduces them exactly, and a heal is what fixes them.
    """
    refusals = [error for error in result.errors if _is_refusal(error)]
    return _TargetSide(
        count=len(refusals),
        codes=tuple(dict.fromkeys(error.error_code for error in refusals if error.error_code)),
    )


def _is_refusal(error: RowError) -> bool:
    """Whether this row leaves the sample incomplete rather than indicting the extractor.

    Refusals and ambiguous codes both do: the target would not serve us, or might not
    have. Only a code Bright Data attributes to the scraper itself — or no code at all —
    is evidence about extraction.
    """
    return error.error_code in UNTRUSTWORTHY_SAMPLE_CODES


def null_rates(rows: list[dict], fields: list[str]) -> dict[str, float]:
    """Fraction of rows where each field is null or blank. Empty input gives 0.0 per field."""
    if not rows:
        return dict.fromkeys(fields, 0.0)
    return {
        field: sum(1 for row in rows if _is_blank(row.get(field))) / len(rows) for field in fields
    }


def capture_baseline(
    result: RunResult,
    fields: list[str],
    captured_at: datetime,
    skeleton_hash: str | None = None,
) -> Baseline:
    """The known-good shape of a healthy run, ready to store."""
    return Baseline(
        collector_id=result.collector_id,
        captured_at=captured_at,
        row_count=len(result.rows),
        null_rates=null_rates(result.rows, fields),
        skeleton_hash=skeleton_hash,
    )


def _schema_signal(errors: list[RowError], row_count: int) -> Signal | None:
    """Rows that came back and yielded nothing usable — an extraction fault, so a heal fits.

    Everything the target did **not** refuse is evidence about the extractor: a validation
    failure, a row that was not an object at all, and a collector-side code such as
    `dead_page` or `parse_error`. Only a genuine refusal is excluded — that row never
    reached the extractor, so it says nothing about it.
    """
    failed = [error for error in errors if not _is_refusal(error)]
    if not failed:
        return None
    return Signal(
        kind=SignalKind.SCHEMA,
        outcome=SignalOutcome.FIRED,
        detail=(
            f"{len(failed)} of the {row_count + len(failed)} rows that came back "
            "did not validate against the collector's row schema"
        ),
    )


def _zero_rows_signal(
    result: RunResult, baseline: Baseline | None, target: _TargetSide
) -> Signal | None:
    """Silence where the prior run had rows — unless the target refused part of the sample."""
    if baseline is None or baseline.row_count == 0:
        return None
    if target.count:
        return _abstention(SignalKind.ZERO_ROWS, target)
    if result.rows:
        return None
    return Signal(
        kind=SignalKind.ZERO_ROWS,
        outcome=SignalOutcome.FIRED,
        detail=f"no rows came back, against a baseline of {baseline.row_count}",
    )


def _skeleton_signal(page_html: str | None, baseline: Baseline | None) -> Signal | None:
    """The page's tag and class tree against the stored one. Skipped when no HTML is given."""
    if page_html is None or baseline is None or baseline.skeleton_hash is None:
        return None
    if structural_hash(page_html) == baseline.skeleton_hash:
        return None
    return Signal(
        kind=SignalKind.SKELETON,
        outcome=SignalOutcome.FIRED,
        detail="the page's tag and class tree no longer hashes to the stored one",
    )


def _null_rate_signal(
    result: RunResult,
    baseline: Baseline | None,
    fields: list[str],
    target: _TargetSide,
) -> Signal | None:
    """Fields that stopped being extracted — unless the target refused part of the sample."""
    if baseline is None or not baseline.null_rates:
        return None
    if target.count:
        return _abstention(SignalKind.NULL_RATE, target)
    spiked = _spiked_fields(null_rates(result.rows, fields), baseline.null_rates)
    if not spiked:
        return None
    return Signal(
        kind=SignalKind.NULL_RATE,
        outcome=SignalOutcome.FIRED,
        detail=(
            f"null rate rose by at least {NULL_RATE_SPIKE} above the baseline for: "
            f"{', '.join(spiked)}"
        ),
    )


def _spiked_fields(current: dict[str, float], prior: dict[str, float]) -> list[str]:
    """Baseline fields whose null rate climbed past the threshold. Sorted, so detail is stable.

    Iteration is over the baseline's fields, never this run's: a field the caller added
    to `row_schema` since the baseline was captured has no prior rate to spike above.
    """
    return sorted(
        field
        for field, prior_rate in prior.items()
        if current.get(field, 0.0) - prior_rate >= NULL_RATE_SPIKE
    )


def _abstention(kind: SignalKind, target: _TargetSide) -> Signal:
    """A volume detector declining to answer, with the incomplete sample as the reason."""
    return Signal(
        kind=kind,
        outcome=SignalOutcome.INCONCLUSIVE,
        detail=f"{_refusals(target)}, so the sample is incomplete and this detector abstains",
    )


def _refusals(target: _TargetSide) -> str:
    """How many inputs the target refused and what it called it. Codes are named, never mapped."""
    return f"{target.count} input(s) came back {', '.join(target.codes)}"


def _label(target: _TargetSide) -> str:
    """Throttling by name where it applies, an incomplete sample where it does not."""
    return THROTTLED_LABEL if THROTTLE_CODES.intersection(target.codes) else INCOMPLETE_LABEL


def _reason(fired: list[Signal], target: _TargetSide) -> str | None:
    """The verdict in one line: what fired, and whether the sample can be trusted at all."""
    parts: list[str] = []
    if fired:
        parts.append(f"break evidence from {', '.join(signal.kind for signal in fired)}")
    if target.count:
        parts.append(
            f"{_label(target)}: {_refusals(target)}, so the volume detectors "
            "abstained — retry before healing"
        )
    return "; ".join(parts) or None


def _is_blank(value: Any) -> bool:
    """Whether a field carries nothing usable. An empty string is as absent as a `None`."""
    return value is None or (isinstance(value, str) and not value.strip())
