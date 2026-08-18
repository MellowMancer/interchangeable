"""Every abstract seam in the package. Implementations live further out; none is imported here.

`Protocol`, not `ABC`: an adapter satisfies a port by having the right methods, so the
caller may substitute its own persistence or its own transport without inheriting
anything of ours.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from bdheal.models import (
    Baseline,
    BenchCase,
    CollectorSpec,
    DetectVerdict,
    HealEvent,
    RunResult,
    VerifyReport,
)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """What a finished command left behind. The only shape `CommandRunner` returns."""

    returncode: int
    stdout: str
    stderr: str


class StudioClient(Protocol):
    """The Bright Data boundary.

    One port rather than one per subcommand: there is a single CLI and a single reason
    to change. Every quirk stays behind this line — realtime-to-batch escalation, per-row
    error codes, 3600-attempt polling, and the approval gate. Nothing above it may know
    that a subprocess exists.
    """

    def create(self, url: str, description: str) -> str:
        """Build a collector and return its id. Raises `CollectorCreateError` on failure."""
        ...

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Run the collector over `urls`, validating each row against `spec.row_schema`."""
        ...

    def heal(self, spec: CollectorSpec, prompt: str, *, auto_approve: bool = False) -> HealEvent:
        """Heal the collector in place. The collector id does not change."""
        ...

    def approve(self, spec: CollectorSpec, url: str, *, reject: bool = False) -> HealEvent:
        """Promote or reject a pending heal, anchored on `url`."""
        ...

    def fetch_html(self, url: str) -> str:
        """Fetch a page's raw HTML, for the skeleton hash. The package owns no HTTP client."""
        ...


class HealStore(Protocol):
    """Everything the package remembers between runs.

    One port rather than three: there is a single backing store and a single reason to
    change. Baselines, heal events and benchmark case state are persisted together
    because they are read together — a resume needs all three.
    """

    def save_baseline(self, baseline: Baseline) -> None:
        """Insert or replace the known-good shape for one collector."""
        ...

    def baseline(self, collector_id: str) -> Baseline | None:
        """The stored baseline, or `None` on a collector's first-ever run."""
        ...

    def save_heal_event(self, event: HealEvent) -> HealEvent:
        """Append a heal event, returning it with its assigned id."""
        ...

    def heal_events(self, collector_id: str) -> list[HealEvent]:
        """Every heal event for a collector, oldest first."""
        ...

    def save_bench_case(self, case: BenchCase) -> None:
        """Insert or replace one benchmark case outcome. Idempotent, so a resume is safe."""
        ...

    def completed_case_ids(self, run_id: str) -> list[str]:
        """The case ids already finished in this run. The runner skips these."""
        ...


class Clock(Protocol):
    """Time, injected.

    One port with two readings: `now` timestamps records, `monotonic` measures durations.
    Splitting them would let a test freeze one and not the other, which is how a
    deterministic timing assertion stops being deterministic.
    """

    def now(self) -> datetime:
        """Current wall-clock time, timezone-aware."""
        ...

    def monotonic(self) -> float:
        """Seconds from an arbitrary origin. Only differences are meaningful."""
        ...


class CommandRunner(Protocol):
    """Runs one command and returns its result.

    argv is a `list[str]` and there is no shell (G3): collector ids and heal prompts are
    interpolated values, so this signature is the injection boundary.
    """

    def __call__(self, argv: list[str], timeout_s: int) -> ProcessResult:
        """Run `argv` to completion or raise on timeout."""
        ...


class HealLoop(Protocol):
    """The self-healing loop as its consumers see it — the `Healer` facade's shape.

    It exists so the benchmark can drive the loop without importing the concrete facade:
    `bench/` depends on this abstraction, never on its parent's implementation.
    """

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Run the collector."""
        ...

    def detect(self, spec: CollectorSpec, result: RunResult) -> DetectVerdict:
        """Decide whether the run shows a break."""
        ...

    def heal(self, spec: CollectorSpec, verdict: DetectVerdict) -> HealEvent:
        """Diagnose the verdict and heal the collector."""
        ...

    def verify(
        self,
        spec: CollectorSpec,
        golden: Sequence[dict[str, Any]],
        old_layout_url: str,
    ) -> VerifyReport:
        """Score the healed collector against golden records and the old layout."""
        ...
