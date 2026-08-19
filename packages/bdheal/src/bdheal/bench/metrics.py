"""The five benchmark metrics and the signal-by-mutation coverage matrix.

Pure functions over finished cases: no ports, no clock, no I/O. Timings arrive already
measured on `BenchCase`, which is what makes the numbers assertable to an exact value.

These numbers are published, so every denominator is a decision and each one is recorded
here rather than left to the reader:

- **A case nothing detected is not a failed heal.** No heal was attempted on it, so it
  cannot appear in the heal rate's denominator; it appears in the coverage matrix as a
  gap instead. `link_label` is expected to be exactly that, and an honest published gap is
  a finding where a silent one is a fabricated success rate.
- **The non-regression rate covers six of the nine mutation classes**, and says so in the
  result itself rather than in this docstring. The three text-changing classes cannot be
  scored: one golden set has to score both layouts, and their mutation changes the page's
  text, so scoring them would report a heal that broke nothing as a regression.
- **A metric with an empty denominator is `None`, not `0.0`.** A rate over no cases is
  unmeasured, and publishing zero for it invents the one number that was missing.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from bdheal.models import BenchCase
from bdheal.vocabulary import MutationClass, SignalKind

# The three classes whose mutation rewrites the page's text rather than its structure. One
# golden set cannot score both layouts for these, so they are left out of the
# non-regression rate entirely rather than scored against records that no longer describe
# the old page (resolved 2026-08-19).
EXCLUDED_FROM_NON_REGRESSION: frozenset[MutationClass] = frozenset(
    {MutationClass.DATE_FORMAT, MutationClass.URL_PATTERN, MutationClass.LINK_LABEL}
)

# What is left: the structural classes, whose mutation moves the markup and leaves every
# record on the page exactly where it was.
NON_REGRESSION_CLASSES: frozenset[MutationClass] = (
    frozenset(MutationClass) - EXCLUDED_FROM_NON_REGRESSION
)

# The two floors a heal has to clear to be kept. Restated here rather than imported: this
# module is Entities and `verify` and `healer` are use cases, so the dependency would point
# outward. `tests/test_bench_metrics.py` pins both to their originals, because a published
# methodology that has drifted from the running code is worse than none.
PUBLISHED_NON_REGRESSION_FLOOR = 1.0
PUBLISHED_FIELD_ACCURACY_FLOOR = 0.0

# Wording fixed in `GOAL.md`. It travels on every `Metrics` value because a limit disclosed
# only in documentation is not disclosed to whoever reads the number.
# Both the names and the count come from the set. Spelling the names as prose while
# computing the count lets a tenth class update the number and leave the list naming the
# old three — a disclosure contradicting its own arithmetic, on the artifact whose whole
# job is being honest about what it does not measure.
def _and_list(names: list[str]) -> str:
    """`a, b and c` — the excluded classes read as a sentence, not a machine dump."""
    return " and ".join(filter(None, [", ".join(names[:-1]), names[-1]]))


NON_REGRESSION_NOTE = (
    f"{_and_list(sorted(EXCLUDED_FROM_NON_REGRESSION))} are excluded from the "
    "non-regression rate: their mutation changes the page text, so one golden set cannot "
    "score both layouts. Scoring them would report a heal that broke nothing as a "
    f"regression. The rate therefore covers {len(NON_REGRESSION_CLASSES)} of "
    f"{len(MutationClass)} mutation classes."
)

# Without both floors the heal rate is not reproducible: it is the fraction of attempted
# heals that cleared *these*, and a reader who does not know them cannot repeat the run.
METHODOLOGY: tuple[str, ...] = (
    f"A heal is kept only if the old layout still yields every golden field "
    f"(non-regression floor {PUBLISHED_NON_REGRESSION_FLOOR}).",
    f"A heal is kept only if it recovered something on the layout it was healed for "
    f"(field accuracy above {PUBLISHED_FIELD_ACCURACY_FLOOR}), so a collector that "
    f"extracts nothing cannot promote by regressing nothing.",
    "Attempts count loop passes, not heal calls: the loop heals once per pass.",
    "A case whose verification the target refused is never recorded, so it can neither "
    "inflate nor deflate a rate.",
)


@dataclass(frozen=True, slots=True)
class Metrics:
    """The five numbers the benchmark exists to produce, with the limits they carry.

    Every rate is `None` when nothing was measured, so an unmeasured benchmark cannot be
    read as a benchmark that scored zero.
    """

    heal_rate: float | None
    field_accuracy: float | None
    non_regression_rate: float | None
    mean_time_to_heal_s: float | None
    mean_attempts_to_heal: float | None
    non_regression_note: str
    methodology: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoverageRow:
    """What was declared to catch a mutation class against what actually did.

    `as_declared` says every signal that fired was one the generator declared. It is
    vacuously true when nothing fired at all, which is what `is_gap` and `escalated` are
    for: a class no detector saw, and a class only the loop's own retry caught.

    `cases` distinguishes both from a class that was never run — `cases == 0` is not a
    detection gap, it is an untested class, and reporting the two the same way would
    overstate coverage on a partial run.
    """

    mutation: MutationClass
    expected_signals: frozenset[SignalKind]
    caught_by: frozenset[SignalKind]
    cases: int
    escalated: int
    is_gap: bool
    as_declared: bool


def metrics(cases: Sequence[BenchCase]) -> Metrics:
    """Aggregate finished cases into the five headline metrics."""
    if not cases:
        raise ValueError("there are no cases to compute metrics over")
    healed = [case for case in cases if case.healed]
    return Metrics(
        heal_rate=_mean([float(case.healed) for case in cases if case.attempts]),
        field_accuracy=_mean(
            [case.field_accuracy for case in cases if case.field_accuracy is not None]
        ),
        non_regression_rate=_mean(
            [float(case.non_regression_passed) for case in cases if _scores_regression(case)]
        ),
        mean_time_to_heal_s=_mean([case.elapsed_s for case in healed]),
        mean_attempts_to_heal=_mean([float(case.attempts) for case in healed]),
        non_regression_note=NON_REGRESSION_NOTE,
        methodology=METHODOLOGY,
    )


def coverage(cases: Sequence[BenchCase]) -> list[CoverageRow]:
    """One row per mutation class — including classes no case ran.

    Dropping the empty ones made "never attempted" indistinguishable from "absent from the
    table", so a partial run published a matrix where every listed row looked healthy and
    the reader had to count rows against `MutationClass` to notice. `cases` says which it
    is, on the artifact whose whole subject is what was and was not covered.
    """
    return [_row(mutation, _of_class(cases, mutation)) for mutation in MutationClass]


def _of_class(cases: Sequence[BenchCase], mutation: MutationClass) -> list[BenchCase]:
    """Every case that ran this mutation class."""
    return [case for case in cases if case.mutation == mutation]


def _row(mutation: MutationClass, cases: list[BenchCase]) -> CoverageRow:
    """One class's declaration set against everything that actually fired for it.

    A case with no signal but a loop pass behind it was escalated rather than missed (F10):
    the loop's retry caught what no detector could name, and reporting that as a detection
    gap would credit the detectors with a blind spot they do not have.
    """
    expected = frozenset[SignalKind]().union(*(case.expected_signals for case in cases))
    caught = frozenset(case.caught_by for case in cases if case.caught_by is not None)
    escalated = sum(1 for case in cases if case.caught_by is None and case.attempts)
    return CoverageRow(
        mutation=mutation,
        expected_signals=expected,
        caught_by=caught,
        cases=len(cases),
        escalated=escalated,
        # A class nobody ran is not a gap. Calling it one would report a detector blind
        # spot that was never tested for, which overstates the very thing this measures.
        is_gap=bool(cases) and not caught and not escalated,
        as_declared=caught <= expected,
    )


def _scores_regression(case: BenchCase) -> bool:
    """Whether this case may enter the non-regression rate.

    Two exclusions, both of them findings rather than failures: a text-changing class one
    golden set cannot score, and a verification that never produced a reading.
    """
    return case.mutation in NON_REGRESSION_CLASSES and case.non_regression_passed is not None


def _mean(values: Sequence[float]) -> float | None:
    """The mean, or `None` when there was nothing to average. Never zero by default."""
    return sum(values) / len(values) if values else None
