"""Shared stubs and fixtures. Tests exercise the ports, never the concrete adapters.

Nothing here opens a socket, a database file or a process — that is the isolation
guarantee (G1), and these stubs are where it is enforced rather than hoped for. Every
feature reuses them; a test that needs different behaviour programmes the stub it was
given instead of writing a near-copy beside it.
"""

import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel

from bdheal.models import (
    Baseline,
    BenchCase,
    CollectorSpec,
    HealEvent,
    RunResult,
)
from bdheal.ports import Clock, HealStore, ProcessResult, StudioClient
from bdheal.vocabulary import HealStatus

# marker -> (environment variable that enables it, what it does once enabled)
NETWORK_GATES: dict[str, tuple[str, str]] = {
    "live": ("BDHEAL_LIVE", "call the real bdata CLI"),
    "publish": ("BDHEAL_PUBLISH_CHECK", "build the package and install it from a package index"),
}
FIXED_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
STUB_COLLECTOR_ID = "c_stub00000000000000"


class SampleRow(BaseModel):
    """A caller's row schema, deliberately generic — no test may rely on a problem domain."""

    title: str
    url: str
    published: str | None = None


class FixedClock:
    """Time that only moves when a test moves it, so durations are exact values."""

    def __init__(self, now: datetime = FIXED_NOW, monotonic: float = 0.0) -> None:
        self._now = now
        self._monotonic = monotonic

    def now(self) -> datetime:
        """The current frozen wall-clock time."""
        return self._now

    def monotonic(self) -> float:
        """The current frozen monotonic reading."""
        return self._monotonic

    def advance(self, seconds: float) -> None:
        """Move both readings forward by `seconds`."""
        self._monotonic += seconds
        self._now = self._now + timedelta(seconds=seconds)


class StubStudioClient:
    """A programmable `StudioClient`: queue the responses, then assert on the calls.

    `calls` records every invocation as a tuple, so argv-shaping tests assert what was
    asked for without a process ever starting.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or FixedClock()
        self.run_results: list[RunResult] = []
        self.heal_events: list[HealEvent] = []
        self.pages: dict[str, str] = {}
        self.created_id = STUB_COLLECTOR_ID
        self.calls: list[tuple[Any, ...]] = []
        self.urls_run: list[str] = []

    def create(self, url: str, description: str) -> str:
        """Record the call and hand back the canned collector id."""
        self.calls.append(("create", url, description))
        return self.created_id

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Pop the next queued result, or an empty one when the queue is exhausted."""
        self.calls.append(("run", spec.collector_id, *urls))
        self.urls_run.extend(urls)
        if self.run_results:
            return self.run_results.pop(0)
        return RunResult(collector_id=spec.collector_id, fetched_at=self.clock.now())

    def heal(self, spec: CollectorSpec, prompt: str, *, auto_approve: bool = False) -> HealEvent:
        """Pop the next queued heal event, defaulting to a pending one at the gate."""
        self.calls.append(("heal", spec.collector_id, prompt, auto_approve))
        if self.heal_events:
            return self.heal_events.pop(0)
        status = HealStatus.DONE if auto_approve else HealStatus.AWAITING_APPROVAL
        return HealEvent(
            collector_id=spec.collector_id,
            status=status,
            created_at=self.clock.now(),
            prompt=prompt,
            promoted=auto_approve,
        )

    def approve(self, spec: CollectorSpec, url: str, *, reject: bool = False) -> HealEvent:
        """Resolve the gate the way the test asked for."""
        self.calls.append(("approve", spec.collector_id, url, reject))
        return HealEvent(
            collector_id=spec.collector_id,
            status=HealStatus.REJECTED if reject else HealStatus.DONE,
            created_at=self.clock.now(),
            promoted=not reject,
        )

    def fetch_html(self, url: str) -> str:
        """Serve the HTML the test registered for this URL."""
        self.calls.append(("fetch_html", url))
        return self.pages.get(url, "")


class InMemoryHealStore:
    """A `HealStore` held in dictionaries. No file, no schema, no tmp_path needed."""

    def __init__(self) -> None:
        self.baselines: dict[str, Baseline] = {}
        self.events: list[HealEvent] = []
        self.cases: dict[tuple[str, str], BenchCase] = {}

    def save_baseline(self, baseline: Baseline) -> None:
        """Insert or replace the known-good shape for one collector."""
        self.baselines[baseline.collector_id] = baseline

    def baseline(self, collector_id: str) -> Baseline | None:
        """The stored baseline, or `None` when nothing has been recorded yet."""
        return self.baselines.get(collector_id)

    def save_heal_event(self, event: HealEvent) -> HealEvent:
        """Append the event with the next id, mirroring the SQLite adapter's contract."""
        stored = event.model_copy(update={"id": len(self.events) + 1})
        self.events.append(stored)
        return stored

    def heal_events(self, collector_id: str) -> list[HealEvent]:
        """Every event for a collector, in insertion order."""
        return [event for event in self.events if event.collector_id == collector_id]

    def save_bench_case(self, case: BenchCase) -> None:
        """Insert or replace one case outcome, keyed as the primary key is."""
        self.cases[(case.run_id, case.case_id)] = case

    def completed_case_ids(self, run_id: str) -> list[str]:
        """The case ids already finished in this run."""
        return [case_id for run, case_id in self.cases if run == run_id]


class RecordingRunner:
    """A `CommandRunner` that records argv and replays queued results. Starts nothing."""

    def __init__(self, results: list[ProcessResult] | None = None) -> None:
        self.results = results or []
        self.argvs: list[list[str]] = []
        self.timeouts: list[int] = []

    def __call__(self, argv: list[str], timeout_s: int) -> ProcessResult:
        """Record the invocation and return the next queued result, or an empty success."""
        self.argvs.append(argv)
        self.timeouts.append(timeout_s)
        if self.results:
            return self.results.pop(0)
        return ProcessResult(returncode=0, stdout="", stderr="")


class ForbiddenRunner:
    """A `CommandRunner` that fails the test if anything tries to leave the process."""

    def __call__(self, argv: list[str], timeout_s: int) -> ProcessResult:
        """Always raises: reaching here means a test was about to hit the network."""
        raise AssertionError(f"the suite must not start a process (argv[0]={argv[0]!r})")


@pytest.fixture
def clock() -> Clock:
    """A frozen clock, typed as the port."""
    return FixedClock()


@pytest.fixture
def studio(clock: Clock) -> StudioClient:
    """A programmable StudioClient, typed as the port."""
    return StubStudioClient(clock)


@pytest.fixture
def store() -> HealStore:
    """An in-memory HealStore, typed as the port."""
    return InMemoryHealStore()


@pytest.fixture
def recording_runner() -> RecordingRunner:
    """A CommandRunner that captures argv, for the injection and flag assertions."""
    return RecordingRunner()


@pytest.fixture
def forbidden_runner() -> ForbiddenRunner:
    """A CommandRunner that turns any process launch into a test failure."""
    return ForbiddenRunner()


@pytest.fixture
def spec() -> CollectorSpec:
    """A generic collector spec with a generic row schema."""
    return CollectorSpec(
        collector_id=STUB_COLLECTOR_ID,
        name="stub collector",
        anchor_urls=["https://example.test/list"],
        row_schema=SampleRow,
    )


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip every network-gated marker unless its variable is set. The default suite is offline."""
    for marker, (variable, what) in NETWORK_GATES.items():
        if marker in item.keywords and os.environ.get(variable) != "1":
            pytest.skip(f"set {variable}=1 to run tests that {what}")
