"""The five benchmark metrics and the signal-by-mutation coverage matrix.

Pure functions over finished cases: no ports, no clock, no I/O. Timings arrive already
measured on `BenchCase`, which is what makes the numbers assertable to an exact value.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from bdheal.models import BenchCase
from bdheal.vocabulary import ExpectedSignal, MutationClass, SignalKind


@dataclass(frozen=True, slots=True)
class Metrics:
    """The five numbers the benchmark exists to produce."""

    heal_rate: float
    field_accuracy: float
    non_regression_rate: float
    mean_time_to_heal_s: float
    mean_attempts_to_heal: float


@dataclass(frozen=True, slots=True)
class CoverageRow:
    """What was declared to catch a mutation class against what actually did."""

    mutation: MutationClass
    expected_signal: ExpectedSignal
    caught_by: SignalKind | None
    is_gap: bool


def metrics(cases: Sequence[BenchCase]) -> Metrics:
    """Aggregate finished cases into the five headline metrics."""
    raise NotImplementedError


def coverage(cases: Sequence[BenchCase]) -> list[CoverageRow]:
    """One row per mutation class. A class no signal caught is a gap, not a heal failure."""
    raise NotImplementedError
