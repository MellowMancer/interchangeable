"""Golden diff plus the non-regression check.

A heal that fixes the new layout by breaking the old one is an overfit, not a repair, so
the healed collector is re-run against `old_layout_url` and diffed too. That second pass
is the measurement nobody else takes.
"""

from collections.abc import Sequence
from typing import Any

from bdheal.models import CollectorSpec, VerifyReport
from bdheal.ports import Clock, StudioClient


def field_accuracy(rows: Sequence[dict[str, Any]], golden: Sequence[dict[str, Any]]) -> float:
    """Fraction of golden fields recovered exactly, in 0.0..1.0. Missing rows count as misses."""
    raise NotImplementedError


def verify(
    spec: CollectorSpec,
    golden: Sequence[dict[str, Any]],
    old_layout_url: str,
    studio: StudioClient,
    clock: Clock,
    *,
    attempts: int = 1,
) -> VerifyReport:
    """Score the healed collector against golden records, then against the old layout."""
    raise NotImplementedError
