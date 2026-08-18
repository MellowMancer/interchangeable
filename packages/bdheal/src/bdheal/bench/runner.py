"""Drives mutated fixtures through the loop and persists each case as it finishes.

A full benchmark is hours of wall-clock, so state is written per case and a restart
executes only what is left. The loop arrives as a `HealLoop`, so the benchmark never
names the concrete facade and runs green in tests against stubbed ports.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from bdheal.models import BenchCase, CollectorSpec
from bdheal.ports import Clock, HealLoop, HealStore
from bdheal.vocabulary import ExpectedSignal, MutationClass


@dataclass(frozen=True, slots=True)
class BenchCaseSpec:
    """One case to run: which mutation, hosted where, scored against which golden rows."""

    case_id: str
    mutation: MutationClass
    expected_signal: ExpectedSignal
    spec: CollectorSpec
    fixture_url: str
    old_layout_url: str
    golden: tuple[dict[str, Any], ...]


def run_benchmark(
    run_id: str,
    cases: Sequence[BenchCaseSpec],
    loop: HealLoop,
    store: HealStore,
    clock: Clock,
) -> list[BenchCase]:
    """Run every case not already completed under `run_id`, returning all outcomes."""
    raise NotImplementedError
