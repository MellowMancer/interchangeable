"""The facade: the one object a caller needs.

Both ports and the clock are constructor arguments. There is no module-level client, no
global state and no default that reaches the network implicitly — if this object was
never handed a `StudioClient`, nothing can leave the process.
"""

from collections.abc import Sequence
from typing import Any

from bdheal.models import CollectorSpec, DetectVerdict, HealEvent, RunResult, VerifyReport
from bdheal.ports import Clock, HealStore, StudioClient


class Healer:
    """Run, detect, heal, verify — the self-healing loop over one collector."""

    def __init__(self, studio: StudioClient, store: HealStore, clock: Clock) -> None:
        self._studio = studio
        self._store = store
        self._clock = clock

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Run the collector and return validated rows alongside per-row errors."""
        raise NotImplementedError

    def detect(self, spec: CollectorSpec, result: RunResult) -> DetectVerdict:
        """Judge the run against its stored baseline. Updates the baseline when healthy."""
        raise NotImplementedError

    def heal(self, spec: CollectorSpec, verdict: DetectVerdict) -> HealEvent:
        """Diagnose the verdict, heal in place, and record the outcome."""
        raise NotImplementedError

    def verify(
        self,
        spec: CollectorSpec,
        golden: Sequence[dict[str, Any]],
        old_layout_url: str,
    ) -> VerifyReport:
        """Score the healed collector against golden records and the old layout."""
        raise NotImplementedError
