"""Nine domain-free HTML perturbations. Structure and text, never meaning.

Each generator is a pure `str -> str` function and carries, as data, the detect signal it
is *declared* to trip. The declaration is a claim the benchmark then checks against what
actually fired; where the two disagree the result is a published coverage gap, not a
hidden failure. `link_label` is declared `NONE` on purpose — no detector can see it, and
saying so is the honest finding.

The declared signal for each class is fixed in ARCHITECTURE.md; F11 populates
`MUTATIONS` to match it.
"""

from collections.abc import Callable
from dataclasses import dataclass

from bdheal.vocabulary import ExpectedSignal, MutationClass


@dataclass(frozen=True, slots=True)
class Mutation:
    """One perturbation: what it is called, what it does, and what should catch it."""

    mutation: MutationClass
    expected_signal: ExpectedSignal
    apply: Callable[[str], str]

    def __post_init__(self) -> None:
        if not callable(self.apply):
            raise ValueError("a mutation must carry a callable generator")


MUTATIONS: tuple[Mutation, ...] = ()
