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
    RowError,
    RunResult,
)
from bdheal.ports import Clock, HealStore, ProcessResult, StudioClient
from bdheal.studio import _distinct_codes
from bdheal.vocabulary import (
    FailureClass,
    HealStatus,
    MutationClass,
    SignalKind,
)

# marker -> (environment variable that enables it, what it does once enabled)
NETWORK_GATES: dict[str, tuple[str, str]] = {
    "live": ("BDHEAL_LIVE", "call the real bdata CLI"),
    "publish": ("BDHEAL_PUBLISH_CHECK", "build the package and install it from a package index"),
}

# The problem-domain vocabulary `bdheal` must never contain. Owned by no single feature: every
# module carrying a "domain-free" criterion asserts against this one list, so the bar
# cannot drift feature by feature. The application's own name is deliberately absent —
# that is G2's job, and naming it here would make the invariant's own `rg` check match.
# `corpus` is deliberately absent: it is not domain vocabulary but the generic word for
# a body of documents, and the package's own docstring says it is "corpus-agnostic".
# Listing it would make the rule fight the sentence that states the rule holds.
DOMAIN_TERMS = (
    "agencies",
    "agency",
    "agenda",
    "award",
    "bainbridge",
    "bothell",
    "capital",
    "council",
    "lakehaven",
    "lexicon",
    "meeting",
    "municipal",
    "packet",
    "procurement",
    "rfp",
    "solicitation",
    "tier",
    "wastewater",
)


def assert_names_no_problem_domain(source: str) -> None:
    """Fail if `source` carries any problem-domain word.

    Substring, not word-boundary: `\\bmeeting\\b` misses `meetings`, and a plural is every
    bit as much a corpus term as its singular. Three feature files each grew their own
    version of this check, with two different predicates, before it was consolidated —
    exactly the drift the shared list was meant to prevent, one layer up.
    """
    lowered = source.lower()
    found = sorted(term for term in DOMAIN_TERMS if term in lowered)
    assert not found, f"problem-domain vocabulary present: {', '.join(found)}"

FIXED_NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
STUB_COLLECTOR_ID = "c_stub00000000000000"

# Credential-shaped values that are not credentials: an API key and a JWT, shaped like the
# real ones so a redaction test proves something. They live here because two features
# assert against them — the prompt that must never read one, and the CLI output that must
# never persist one — and two constants of the same fake key would drift.
FAKE_API_KEY = "bd_live_00000000000000000000000000000000"
FAKE_BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIwMDAwMDAwIn0.00Ftj0eZ4CVPmB92K27uhbUJU1p1"
# Deliberately SHORT — under the catch-all's opaque-run threshold, so only the
# `Authorization:` pattern can save it. A long JWT passes even when that pattern is
# broken, which is exactly how a real leak shipped green once.
FAKE_SHORT_TOKEN = "s3cr3t42"

# A heal preview as `scraper heal` actually returned one on 2026-08-20, transcribed from
# the validation error that discarded the envelope: a JSON *array* holding one object
# whose key carries the extracted rows. It lives here because the parse and the round-trip
# both pin it, and two hand-written copies of a vendor payload would drift apart.
ARRAY_PREVIEW_RESULT = [{"components": [{"ref": f"RF-{index:03d}"} for index in range(1, 13)]}]

# What `scraper heal` printed for five straight hours on 2026-08-20, against a collector
# whose gate an earlier run had left parked: Bright Data had finished that repair and was
# waiting for an answer nobody ever sent, so it refused every heal proposed afterwards.
# The collector became usable again only when the pending gate was rejected by hand.
# Three files assert against this text — the adapter that must type it, the gate that must
# record it, and the facade that must recover from it — and three copies would drift.
STRANDED_GATE_STDERR = (
    "Failed to start self-healing for collector c_mt25s8wzts19a6xf8:\n"
    "  Error: Another refactor job is still in progress\n"
    "  Status: 409"
)


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

    def bench_runs(self) -> list[str]:
        """Every run id present, ordered as the SQLite adapter orders them."""
        def when(case: BenchCase) -> tuple[bool, object]:
            return (case.completed_at is None, case.completed_at)

        by_run: dict[str, BenchCase] = {}
        for case in sorted(self.cases.values(), key=when):
            by_run.setdefault(case.run_id, case)
        return list(by_run)

    def bench_cases(self, run_id: str) -> list[BenchCase]:
        """Every finished case in this run, ordered as the SQLite adapter orders them."""
        return [case for (run, _), case in sorted(self.cases.items()) if run == run_id]


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



# Boundary-model factories. Every one takes `**overrides`, so a test states only the field
# its scenario turns on. These were written separately in four feature test files, because
# shared files were locked while those features were built in parallel — which meant adding
# one required field to a model was a five-site edit.


def baseline(**overrides: object) -> Baseline:
    """A prior run to compare against."""
    fields: dict[str, object] = {
        "collector_id": STUB_COLLECTOR_ID,
        "captured_at": FIXED_NOW,
        "row_count": 3,
        "null_rates": {"title": 0.0, "url": 0.0},
        "skeleton_hash": None,
    }
    return Baseline(**(fields | overrides))


def run_result(**overrides: object) -> RunResult:
    """A run shaped exactly as the studio adapter builds one.

    `error_codes` is *derived* from the adapter's own rule, never restated, so a change to
    that rule cannot leave these fixtures describing a shape production no longer emits.

    `errors` is coerced first: `RunResult` accepts plain dicts there, and deriving the
    codes off raw dicts would raise rather than validate.
    """
    fields: dict[str, object] = {
        "collector_id": STUB_COLLECTOR_ID,
        "fetched_at": FIXED_NOW,
        "rows": [],
        "errors": [],
    }
    merged = fields | overrides
    errors = [error if isinstance(error, RowError) else RowError(**error) for error in merged["errors"]]
    merged["errors"] = errors
    merged.setdefault("error_codes", _distinct_codes(errors))
    return RunResult(**merged)


def heal_event(**overrides: object) -> HealEvent:
    """One trip through the heal gate, stopped at the approval step."""
    fields: dict[str, object] = {
        "collector_id": STUB_COLLECTOR_ID,
        "status": HealStatus.AWAITING_APPROVAL,
        "created_at": FIXED_NOW,
        "prompt": "the table became a div; re-anchor on the row wrapper",
        "preview_result": {"rows": [{"title": "a", "url": "https://example.test/a"}]},
        "promoted": False,
        "failure_class": FailureClass.STRUCTURE_CHANGED,
        "template_id": "structure_changed_v1",
        "attempts": 2,
        "error": None,
    }
    return HealEvent(**(fields | overrides))


def bench_case(**overrides: object) -> BenchCase:
    """One benchmark case's outcome."""
    fields: dict[str, object] = {
        "run_id": "run_01",
        "case_id": "case_01",
        "mutation": MutationClass.TABLE_TO_DIV,
        "expected_signals": frozenset({SignalKind.SKELETON}),
        "caught_by": SignalKind.SKELETON,
        "healed": True,
        "field_accuracy": 0.75,
        "non_regression_passed": True,
        "attempts": 1,
        "elapsed_s": 12.5,
        "completed_at": FIXED_NOW,
    }
    return BenchCase(**(fields | overrides))


def row_error(index: int, **overrides: object) -> RowError:
    """One row that did not survive the boundary."""
    fields: dict[str, object] = {"index": index, "message": "boom"}
    return RowError(**(fields | overrides))


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
