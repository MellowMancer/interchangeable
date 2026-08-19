"""Drives mutated fixtures through the loop and persists each case as it finishes.

A full benchmark is hours of wall-clock, so state is written per case and a restart
executes only what is left. The loop arrives as a `HealLoop`, so the benchmark never
names the concrete facade and runs green in tests against stubbed ports.

Three things the runner does that are decisions rather than plumbing:

- **Each case is anchored on its own fixture.** A `RunResult` does not carry the URLs it
  came from, so the loop's own retry re-runs `spec.anchor_urls`; a spec pointing anywhere
  else would silently score a different page. The runner re-anchors rather than trusting
  the caller to have done it.
- **The old layout is run first.** The skeleton and volume detectors have nothing to
  compare against until a known-good shape exists, so every case takes its baseline from
  the unmutated page before the mutated one is judged. Only the judged pass is timed.
- **A heal's outcome is read from the terminal-most heal row, never from a row count.** A
  gated cycle leaves two rows before verification settles it with a third, so counting
  rows would count a gate as a heal.

Nothing is caught here. A case the target refused, or one whose loop raised, is simply
never saved — and an unsaved case is exactly what a restart re-runs.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from bdheal.models import BenchCase, CollectorSpec, DetectVerdict, latest_settled
from bdheal.ports import Clock, HealLoop, HealStore
from bdheal.vocabulary import SIGNAL_PRECEDENCE, MutationClass, SignalKind

# The facade heals exactly once per pass through the loop, so a case that was attempted
# costs one pass. Attempts-to-heal counts these, not heal calls and not the verification
# passes inside one `verify()`.
LOOP_PASSES_PER_CASE = 1


@dataclass(frozen=True, slots=True)
class BenchCaseSpec:
    """One case to run: which mutation, hosted where, scored against which golden rows."""

    case_id: str
    mutation: MutationClass
    expected_signals: frozenset[SignalKind]
    spec: CollectorSpec
    fixture_url: str
    old_layout_url: str
    golden: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _Outcome:
    """What one case's pass through the loop established, before it is timed and stored."""

    caught_by: SignalKind | None
    healed: bool
    field_accuracy: float | None
    non_regression_passed: bool | None
    attempts: int


# A case no detector saw. Nothing was attempted on it, so it is a coverage gap rather than
# a heal that failed — the distinction the whole matrix exists to publish.
_MISSED = _Outcome(
    caught_by=None, healed=False, field_accuracy=None, non_regression_passed=None, attempts=0
)


def run_benchmark(
    run_id: str,
    cases: Sequence[BenchCaseSpec],
    loop: HealLoop,
    store: HealStore,
    clock: Clock,
) -> list[BenchCase]:
    """Run every case not already completed under `run_id`, returning the outcomes it produced.

    Already-finished cases are skipped whole rather than re-run, so restarting after a
    crash costs only what was left. The return value is therefore this call's work, not the
    run's: publish the run's numbers from `store.bench_cases(run_id)`, which is every case
    including the ones a previous process executed.
    """
    completed = set(store.completed_case_ids(run_id))
    return [
        _run_case(run_id, case, loop, store, clock)
        for case in cases
        if case.case_id not in completed
    ]


def _run_case(
    run_id: str, case: BenchCaseSpec, loop: HealLoop, store: HealStore, clock: Clock
) -> BenchCase:
    """Drive one case and persist it. Saving is the last thing that happens, by contract."""
    _capture_old_layout(case, loop)
    started = clock.monotonic()
    outcome = _drive(case, loop, store)
    finished = BenchCase(
        run_id=run_id,
        case_id=case.case_id,
        mutation=case.mutation,
        expected_signals=case.expected_signals,
        caught_by=outcome.caught_by,
        healed=outcome.healed,
        field_accuracy=outcome.field_accuracy,
        non_regression_passed=outcome.non_regression_passed,
        attempts=outcome.attempts,
        elapsed_s=clock.monotonic() - started,
        completed_at=clock.now(),
    )
    store.save_bench_case(finished)
    return finished


def _capture_old_layout(case: BenchCaseSpec, loop: HealLoop) -> None:
    """One judged run against the unmutated page, whose side effect is the known-good shape.

    The verdict is deliberately unread: a first run has nothing to compare against, so what
    matters is the baseline it leaves behind for the mutated pass to be judged against.
    """
    spec = _anchored(case.spec, case.old_layout_url)
    loop.detect(spec, loop.run(spec, spec.anchor_urls))


def _drive(case: BenchCaseSpec, loop: HealLoop, store: HealStore) -> _Outcome:
    """Judge the mutated page, heal what it found, and score what the heal did."""
    spec = _anchored(case.spec, case.fixture_url)
    verdict = loop.detect(spec, loop.run(spec, spec.anchor_urls))
    if not verdict.broken:
        return _MISSED
    caught_by = _credited(verdict)
    if not loop.heal(spec, verdict).promoted:
        return _unscored(caught_by)
    report = loop.verify(spec, case.golden, case.old_layout_url)
    return _Outcome(
        caught_by=caught_by,
        healed=_kept(store, spec.collector_id),
        field_accuracy=report.field_accuracy,
        non_regression_passed=report.non_regression_passed,
        attempts=LOOP_PASSES_PER_CASE,
    )


def _unscored(caught_by: SignalKind | None) -> _Outcome:
    """A break the gate refused to heal: attempted and failed, with nothing to score.

    Verifying here would run the *unhealed* collector and publish its accuracy as a heal's,
    so the case carries no score at all — the heal rate already counts it as the failure it
    is.
    """
    return _Outcome(
        caught_by=caught_by,
        healed=False,
        field_accuracy=None,
        non_regression_passed=None,
        attempts=LOOP_PASSES_PER_CASE,
    )


def _anchored(spec: CollectorSpec, url: str) -> CollectorSpec:
    """The case's collector pointed at one page, so every retry inside the loop re-runs it."""
    return spec.model_copy(update={"anchor_urls": [url]})


def _credited(verdict: DetectVerdict) -> SignalKind | None:
    """Which detector is credited with catching this mutation, or `None` if none did.

    `None` is not automatically a coverage gap: the loop escalates ambiguous error codes
    without fabricating a signal, so a broken verdict with nothing fired means the loop's
    retry caught what no detector could name.
    """
    fired = verdict.fired_kinds
    return next((kind for kind in SIGNAL_PRECEDENCE if kind in fired), None)


def _kept(store: HealStore, collector_id: str) -> bool:
    """Whether the heal survived verification, read from the cycle's terminal-most row."""
    settled = latest_settled(store.heal_events(collector_id))
    return settled is not None and settled.promoted
