"""The benchmark runner: cases through the loop, one persisted row each, resumable.

The runner is driven twice over. Most tests use a scripted `HealLoop`, because a resume
has to be provoked mid-run and a detector has to be made to miss on purpose; one test
drives a real `Healer` over the stubbed ports, so the scripted loop cannot quietly diverge
from the facade it stands in for.

The scripted loop writes the gate's two rows *and* the settlement row, the way the facade
does, so the runner is read against a real gate cycle rather than one tidy row.
"""

import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from conftest import (
    FixedClock,
    InMemoryHealStore,
    SampleRow,
    StubStudioClient,
    bench_case,
    row_error,
    run_result,
)

from bdheal.bench import runner as runner_module
from bdheal.bench.metrics import coverage, metrics
from bdheal.bench.mutate import MUTATIONS
from bdheal.bench.runner import BenchCaseSpec, run_benchmark
from bdheal.errors import VerificationIncompleteError
from bdheal.healer import Healer
from bdheal.models import (
    BenchCase,
    CollectorSpec,
    DetectVerdict,
    HealEvent,
    RunResult,
    Signal,
    VerifyReport,
)
from bdheal.ports import Clock, HealLoop, HealStore
from bdheal.store import SqliteHealStore, connect
from bdheal.vocabulary import HealStatus, MutationClass, SignalKind, SignalOutcome

# What each step of the scripted loop costs, so `elapsed_s` is an exact number rather than
# whatever the machine happened to take.
RUN_SECONDS = 1.0
HEAL_SECONDS = 2.0
VERIFY_SECONDS = 4.0
CASE_SECONDS = RUN_SECONDS + HEAL_SECONDS + VERIFY_SECONDS

RUN_ID = "run_bench_01"
ORIGINAL_URL = "https://example.test/original"
MUTATED_URL = "https://example.test/mutated"

GOLDEN = ({"title": "first", "url": "https://example.test/1"},)
ROWS = [record | {"published": "2026-01-01"} for record in GOLDEN]

# A single self-contained page with nothing to crawl to, per the benchmark's scoping rule.
ORIGINAL_HTML = (
    "<html><body><table class='list'>"
    "<tr class='row'><td class='title'>first</td><td class='when'>2026-01-01</td></tr>"
    "</table></body></html>"
)

TABLE_TO_DIV = next(item for item in MUTATIONS if item.mutation is MutationClass.TABLE_TO_DIV)
MUTATED_HTML = TABLE_TO_DIV.apply(ORIGINAL_HTML)


@dataclass(frozen=True, slots=True)
class Script:
    """What the scripted loop reports for one case: what fired, and how the heal scored."""

    fired: tuple[SignalKind, ...] = (SignalKind.SKELETON,)
    broken: bool = True
    field_accuracy: float = 1.0
    non_regression_passed: bool = True
    refused: bool = False


@dataclass
class ScriptedLoop:
    """A `HealLoop` that answers from a per-collector script and records what it drove.

    The first `detect` for a collector is its baseline pass and always comes back healthy;
    every later one is the mutated page being judged.
    """

    store: HealStore
    clock: FixedClock
    scripts: dict[str, Script]
    crash_on: str | None = None
    runs: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    judged: list[str] = field(default_factory=list)
    heals: list[str] = field(default_factory=list)
    verifications: list[tuple[str, str]] = field(default_factory=list)

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Record which collector was run against which URLs, and charge the clock for it."""
        self.runs.append((spec.collector_id, tuple(urls)))
        self.clock.advance(RUN_SECONDS)
        return RunResult(collector_id=spec.collector_id, fetched_at=self.clock.now())

    def detect(self, spec: CollectorSpec, result: RunResult) -> DetectVerdict:
        """Healthy on the baseline pass, the script's verdict afterwards."""
        baseline_pass = spec.collector_id not in self.judged
        self.judged.append(spec.collector_id)
        if baseline_pass:
            return DetectVerdict(broken=False)
        if spec.collector_id == self.crash_on:
            raise RuntimeError("the benchmark stopped part-way through a case")
        script = self.scripts[spec.collector_id]
        return DetectVerdict(broken=script.broken, signals=[_fired(kind) for kind in script.fired])

    def heal(self, spec: CollectorSpec, verdict: DetectVerdict) -> HealEvent:
        """Write the gate's two rows and hand back the terminal one, as the facade does."""
        self.heals.append(spec.collector_id)
        self.clock.advance(HEAL_SECONDS)
        pending = HealEvent(
            collector_id=spec.collector_id,
            status=HealStatus.AWAITING_APPROVAL,
            created_at=self.clock.now(),
            prompt="re-derive every selector from the current page",
        )
        self.store.save_heal_event(pending)
        return self.store.save_heal_event(
            pending.model_copy(update={"status": HealStatus.DONE, "promoted": True})
        )

    def verify(
        self, spec: CollectorSpec, golden: Sequence[dict[str, Any]], old_layout_url: str
    ) -> VerifyReport:
        """Score the case, then settle the heal the way the facade settles it."""
        self.verifications.append((spec.collector_id, old_layout_url))
        self.clock.advance(VERIFY_SECONDS)
        script = self.scripts[spec.collector_id]
        if script.refused:
            raise VerificationIncompleteError("the target refused every verification pass")
        report = VerifyReport(
            field_accuracy=script.field_accuracy,
            non_regression_passed=script.non_regression_passed,
            attempts=1,
            elapsed_s=VERIFY_SECONDS,
        )
        self._settle(spec, report)
        return report

    def _settle(self, spec: CollectorSpec, report: VerifyReport) -> None:
        """The facade's promotion rule, written as the row the runner reads back."""
        promoted = report.non_regression_passed and report.field_accuracy > 0.0
        self.store.save_heal_event(
            HealEvent(
                collector_id=spec.collector_id,
                status=HealStatus.DONE if promoted else HealStatus.REJECTED,
                created_at=self.clock.now(),
                promoted=promoted,
            )
        )


def _fired(kind: SignalKind) -> Signal:
    """One detector reporting evidence."""
    return Signal(kind=kind, outcome=SignalOutcome.FIRED, detail="the benchmark scripted this")


def case_spec(number: int, mutation: MutationClass = MutationClass.TABLE_TO_DIV) -> BenchCaseSpec:
    """One case, its collector named after it so a scripted loop can be keyed by collector."""
    return BenchCaseSpec(
        case_id=f"case_{number}",
        mutation=mutation,
        expected_signals=frozenset({SignalKind.SKELETON}),
        spec=CollectorSpec(
            collector_id=f"c_case{number:016d}",
            name=f"benchmark case {number}",
            anchor_urls=[MUTATED_URL],
            row_schema=SampleRow,
        ),
        fixture_url=MUTATED_URL,
        old_layout_url=ORIGINAL_URL,
        golden=GOLDEN,
    )


def scripted(cases: Sequence[BenchCaseSpec], script: Script | None = None) -> dict[str, Script]:
    """The same script for every case unless a test wants one that differs."""
    return {case.spec.collector_id: script or Script() for case in cases}


def loop_for(
    cases: Sequence[BenchCaseSpec],
    store: HealStore,
    clock: FixedClock,
    script: Script | None = None,
    crash_on: str | None = None,
) -> ScriptedLoop:
    """A scripted loop wired to this store and clock."""
    return ScriptedLoop(store, clock, scripted(cases, script), crash_on)


def varied(cases: Sequence[BenchCaseSpec]) -> dict[str, Script]:
    """One script per case, each scoring differently: healed, half-healed, rolled back, missed.

    Identical cases would make a resumed run's metrics match whether the rows written
    before the crash were read back or silently lost, because the mean of a subset of
    equal values is that value. The assertion has to be able to tell the difference.
    """
    outcomes = (
        Script(),
        Script(field_accuracy=0.5),
        Script(field_accuracy=0.25, non_regression_passed=False),
        Script(fired=(), broken=False),
    )
    return {
        case.spec.collector_id: script for case, script in zip(cases, outcomes, strict=True)
    }


@pytest.fixture
def bench_clock() -> FixedClock:
    """A clock the scripted loop moves in fixed steps, so every timing is an exact value."""
    return FixedClock()


def test_a_case_runs_the_whole_loop_and_is_recorded(bench_clock: FixedClock) -> None:
    """(a) One case in, one finished `BenchCase` out, carrying everything a metric reads."""
    store = InMemoryHealStore()
    cases = [case_spec(1)]

    outcomes = run_benchmark(RUN_ID, cases, loop_for(cases, store, bench_clock), store, bench_clock)

    assert [outcome.case_id for outcome in outcomes] == ["case_1"]
    assert outcomes[0] == BenchCase(
        run_id=RUN_ID,
        case_id="case_1",
        mutation=MutationClass.TABLE_TO_DIV,
        expected_signals=frozenset({SignalKind.SKELETON}),
        caught_by=SignalKind.SKELETON,
        fired_kinds=frozenset({SignalKind.SKELETON}),
        healed=True,
        field_accuracy=1.0,
        non_regression_passed=True,
        attempts=1,
        elapsed_s=CASE_SECONDS,
        completed_at=outcomes[0].completed_at,
    )
    assert outcomes[0].completed_at is not None


def test_every_case_is_persisted_as_it_finishes(bench_clock: FixedClock) -> None:
    """(b) Save-on-completion is the whole resume contract: an unsaved case simply re-runs."""
    store = InMemoryHealStore()
    cases = [case_spec(number) for number in (1, 2, 3)]

    run_benchmark(RUN_ID, cases, loop_for(cases, store, bench_clock), store, bench_clock)

    assert sorted(store.completed_case_ids(RUN_ID)) == ["case_1", "case_2", "case_3"]


def test_the_baseline_is_taken_from_the_old_layout_before_the_mutation_is_judged(
    bench_clock: FixedClock,
) -> None:
    """A skeleton signal has nothing to compare against until the old layout has been seen."""
    store = InMemoryHealStore()
    cases = [case_spec(1)]
    loop = loop_for(cases, store, bench_clock)

    run_benchmark(RUN_ID, cases, loop, store, bench_clock)

    collector = cases[0].spec.collector_id
    assert loop.runs[:2] == [(collector, (ORIGINAL_URL,)), (collector, (MUTATED_URL,))]


def test_each_case_is_anchored_on_its_own_fixture(bench_clock: FixedClock) -> None:
    """the facade: a `RunResult` carries no URLs, so a retry re-runs the spec's anchors.

    A spec anchored anywhere but this case's fixture would send the loop's own retry to a
    different page and score it as if it were this one.
    """
    store = InMemoryHealStore()
    case = case_spec(1)
    elsewhere = case.spec.model_copy(update={"anchor_urls": ["https://example.test/somewhere"]})
    cases = [
        BenchCaseSpec(
            case_id=case.case_id,
            mutation=case.mutation,
            expected_signals=case.expected_signals,
            spec=elsewhere,
            fixture_url=MUTATED_URL,
            old_layout_url=ORIGINAL_URL,
            golden=GOLDEN,
        )
    ]
    loop = loop_for(cases, store, bench_clock)

    run_benchmark(RUN_ID, cases, loop, store, bench_clock)

    assert [urls for _, urls in loop.runs] == [(ORIGINAL_URL,), (MUTATED_URL,)]
    assert loop.verifications == [(elsewhere.collector_id, ORIGINAL_URL)]


def test_a_case_no_detector_saw_is_a_gap_and_not_a_heal_failure(bench_clock: FixedClock) -> None:
    """(e) `link_label` is expected to evade all four detectors; the matrix says so out loud."""
    store = InMemoryHealStore()
    cases = [case_spec(1, MutationClass.LINK_LABEL)]
    loop = loop_for(cases, store, bench_clock, Script(fired=(), broken=False))

    outcomes = run_benchmark(RUN_ID, cases, loop, store, bench_clock)

    assert loop.heals == []
    assert outcomes[0].attempts == 0
    assert outcomes[0].caught_by is None
    assert next(r for r in coverage(outcomes) if r.cases).is_gap is True
    assert metrics(outcomes).heal_rate is None


def test_an_escalated_case_is_credited_to_no_signal_but_is_not_a_gap(
    bench_clock: FixedClock,
) -> None:
    """the facade: no `SignalKind` means the loop's retry caught it, which is not a blind detector."""
    store = InMemoryHealStore()
    cases = [case_spec(1)]
    loop = loop_for(cases, store, bench_clock, Script(fired=()))

    outcomes = run_benchmark(RUN_ID, cases, loop, store, bench_clock)

    assert outcomes[0].caught_by is None
    assert outcomes[0].attempts == 1
    assert next(r for r in coverage(outcomes) if r.cases).escalated == 1
    assert next(r for r in coverage(outcomes) if r.cases).is_gap is False


def test_the_credited_signal_is_the_cause_and_not_the_symptom(bench_clock: FixedClock) -> None:
    """A moved tag-and-class tree is why the others fired, so the matrix credits it."""
    store = InMemoryHealStore()
    cases = [case_spec(1)]
    both = Script(fired=(SignalKind.SCHEMA, SignalKind.SKELETON))
    loop = loop_for(cases, store, bench_clock, both)

    outcomes = run_benchmark(RUN_ID, cases, loop, store, bench_clock)

    assert outcomes[0].caught_by is SignalKind.SKELETON


def test_a_heal_is_read_from_the_terminal_row_and_never_from_a_row_count(
    bench_clock: FixedClock,
) -> None:
    """the approval gate: a gated heal leaves two rows before verification settles it with a third."""
    store = InMemoryHealStore()
    cases = [case_spec(1)]
    loop = loop_for(cases, store, bench_clock, Script(non_regression_passed=False))

    outcomes = run_benchmark(RUN_ID, cases, loop, store, bench_clock)

    statuses = [event.status for event in store.heal_events(cases[0].spec.collector_id)]
    assert statuses == [HealStatus.AWAITING_APPROVAL, HealStatus.DONE, HealStatus.REJECTED]
    assert outcomes[0].healed is False
    assert outcomes[0].non_regression_passed is False


def test_a_verification_the_target_refused_records_no_case_and_reaches_the_caller(
    bench_clock: FixedClock,
) -> None:
    """verification: the check never ran, so there is no case to publish and none is invented."""
    store = InMemoryHealStore()
    cases = [case_spec(1)]
    loop = loop_for(cases, store, bench_clock, Script(refused=True))

    with pytest.raises(VerificationIncompleteError):
        run_benchmark(RUN_ID, cases, loop, store, bench_clock)

    assert store.completed_case_ids(RUN_ID) == []


def test_a_restarted_run_executes_only_the_cases_left(bench_clock: FixedClock) -> None:
    """(b) Two of four finished before the crash, so a restart drives the other two."""
    store = InMemoryHealStore()
    cases = [case_spec(number) for number in (1, 2, 3, 4)]
    crashed = cases[2].spec.collector_id
    interrupted = loop_for(cases, store, bench_clock, crash_on=crashed)

    with pytest.raises(RuntimeError, match="part-way"):
        run_benchmark(RUN_ID, cases, interrupted, store, bench_clock)
    assert store.completed_case_ids(RUN_ID) == ["case_1", "case_2"]

    resumed = loop_for(cases, store, bench_clock)
    remaining = run_benchmark(RUN_ID, cases, resumed, store, bench_clock)

    assert [outcome.case_id for outcome in remaining] == ["case_3", "case_4"]
    assert sorted(store.completed_case_ids(RUN_ID)) == ["case_1", "case_2", "case_3", "case_4"]


def test_a_case_that_already_finished_is_never_executed_again(bench_clock: FixedClock) -> None:
    """(b) The saved cases are skipped whole — not re-run and quietly overwritten."""
    store = InMemoryHealStore()
    cases = [case_spec(number) for number in (1, 2, 3, 4)]
    crashed = cases[2].spec.collector_id
    interrupted = loop_for(cases, store, bench_clock, crash_on=crashed)
    with pytest.raises(RuntimeError):
        run_benchmark(RUN_ID, cases, interrupted, store, bench_clock)

    resumed = loop_for(cases, store, bench_clock)
    run_benchmark(RUN_ID, cases, resumed, store, bench_clock)

    finished = {cases[0].spec.collector_id, cases[1].spec.collector_id}
    assert finished & {collector for collector, _ in resumed.runs} == set()
    assert [collector for collector, _ in resumed.runs].count(crashed) == 2


def test_a_resumed_run_publishes_the_same_metrics_as_an_uninterrupted_one(
    tmp_path: Path,
) -> None:
    """(b) The point of resuming: the numbers are the run's, not the surviving process's.

    Every part of this is deliberate. The resumed side is a **new store object over a
    reopened file**, because a restart is a new process and an object that never left
    memory proves nothing about one that did. The numbers are then read back **through the
    port**, from the persisted rows, never from a test double's internals — the cases that
    finished before the crash exist only as rows by then, and if they cannot be read back
    the run they belong to has no publishable metrics at all.

    The uninterrupted side is compared as the runner returned it, so a value lost in
    serialisation shows up here as a difference rather than cancelling out on both sides.
    The four cases score differently on purpose — see `varied`.
    """
    cases = [case_spec(number) for number in (1, 2, 3, 4)]
    whole_clock = FixedClock()
    whole_store = SqliteHealStore(connect(tmp_path / "whole.db"))
    whole = run_benchmark(
        RUN_ID,
        cases,
        ScriptedLoop(whole_store, whole_clock, varied(cases)),
        whole_store,
        whole_clock,
    )

    clock = FixedClock()
    db_path = tmp_path / "resumed.db"
    store = SqliteHealStore(connect(db_path))
    with pytest.raises(RuntimeError):
        run_benchmark(
            RUN_ID,
            cases,
            ScriptedLoop(store, clock, varied(cases), cases[2].spec.collector_id),
            store,
            clock,
        )

    reopened = SqliteHealStore(connect(db_path))
    run_benchmark(
        RUN_ID, cases, ScriptedLoop(reopened, clock, varied(cases)), reopened, clock
    )

    assert metrics(reopened.bench_cases(RUN_ID)) == metrics(whole)


def test_a_persisted_case_reads_back_exactly_as_it_was_written(tmp_path: Path) -> None:
    """The resume's other half: rows the metrics are computed from must survive the file.

    It lives with the runner's tests rather than the store's because the round trip is only
    load-bearing for this feature — `bench_cases` exists so a restarted process can publish
    the whole run's numbers, and a field lost here is a fabricated metric there.
    """
    store = SqliteHealStore(connect(tmp_path / "bdheal.db"))
    written = [
        bench_case(run_id=RUN_ID, case_id="case_2"),
        bench_case(
            run_id=RUN_ID,
            case_id="case_1",
            mutation=MutationClass.LINK_LABEL,
            expected_signals=frozenset(),
            caught_by=None,
            healed=False,
            field_accuracy=None,
            non_regression_passed=None,
            attempts=0,
        ),
    ]
    for case in written:
        store.save_bench_case(case)

    read_back = SqliteHealStore(connect(tmp_path / "bdheal.db")).bench_cases(RUN_ID)

    assert read_back == [written[1], written[0]]


def test_a_declared_gap_reads_back_as_an_empty_set_and_not_a_set_holding_nothing(
    tmp_path: Path,
) -> None:
    """`""` is a real stored value: the class its generator declared nothing catches.

    Splitting it naively yields `frozenset({""})`, which is neither empty nor a `SignalKind`
    — the coverage matrix would then call a declared gap a disagreement, silently.
    """
    store = SqliteHealStore(connect(tmp_path / "bdheal.db"))
    store.save_bench_case(bench_case(run_id=RUN_ID, expected_signals=frozenset()))

    assert store.bench_cases(RUN_ID)[0].expected_signals == frozenset()


def test_the_runner_drives_a_real_loop_over_injected_ports(bench_clock: FixedClock) -> None:
    """(c) The whole benchmark, green, with both ports stubbed and nothing on the network.

    The mutated page comes from the mutation generator itself, so the coverage matrix reports what
    the two parsers actually agree on rather than what the declaration hoped for.
    """
    studio = StubStudioClient(bench_clock)
    studio.pages = {ORIGINAL_URL: ORIGINAL_HTML, MUTATED_URL: MUTATED_HTML}
    store = InMemoryHealStore()
    cases = [case_spec(1)]
    collector = cases[0].spec.collector_id
    studio.run_results = [
        run_result(collector_id=collector, rows=ROWS),
        run_result(
            collector_id=collector,
            errors=[row_error(0, field_errors={"title": "field required"})],
        ),
        run_result(collector_id=collector, rows=ROWS),
        run_result(collector_id=collector, rows=ROWS),
    ]

    outcomes = run_benchmark(
        RUN_ID, cases, Healer(studio, store, bench_clock), store, bench_clock
    )

    assert outcomes[0].caught_by is SignalKind.SKELETON
    assert outcomes[0].healed is True
    assert outcomes[0].field_accuracy == 1.0
    assert outcomes[0].non_regression_passed is True
    assert {call[0] for call in studio.calls} <= {"run", "fetch_html", "heal", "approve"}

    # The judged run carries a schema failure as well as the moved markup, and the failed
    # row leaves none behind, so three detectors fire where the generator declared one. That disagreement is the matrix's whole
    # purpose, and it stayed invisible while `as_declared` read only the credited kind:
    # `SIGNAL_PRECEDENCE` credits `skeleton` and `schema` was never counted against the
    # declaration. Confirmed against a live collector, where four of nine classes fired an
    # undeclared `row_count` and every one of them still reported "as declared".
    row = next(r for r in coverage(outcomes) if r.cases)
    assert row.caught_by == frozenset({SignalKind.SKELETON})
    assert row.fired_kinds == frozenset(
        {SignalKind.SKELETON, SignalKind.SCHEMA, SignalKind.ROW_COUNT}
    )
    assert row.as_declared is False


def test_the_runner_takes_the_loop_as_a_port_and_never_names_the_facade() -> None:
    """`bench/` reaches the loop through `HealLoop`, so it cannot know `healer.py` exists."""
    parameters = inspect.signature(run_benchmark).parameters

    assert parameters["loop"].annotation is HealLoop
    assert parameters["store"].annotation is HealStore
    assert parameters["clock"].annotation is Clock
    assert "healer" not in inspect.getsource(runner_module)


def test_the_benchmark_adds_no_command_line_surface() -> None:
    """(d) A callable Python API and nothing else — no CLI framework, no entry point."""
    source = inspect.getsource(runner_module)

    for name in ("argparse", "typer", "click", "__main__", "sys.argv"):
        assert name not in source, f"the runner grew a command line via {name}"


def test_a_resume_survives_the_store_being_reopened(
    tmp_path: Path, bench_clock: FixedClock
) -> None:
    """(b) A restart is a new process, so the case rows have to outlive the connection.

    The in-memory store cannot show this: resume exists precisely for the run that died,
    and a benchmark that re-ran every finished case on reopening would cost the hours it
    was built to save.
    """
    cases = [case_spec(number) for number in (1, 2, 3, 4)]
    db_path = tmp_path / "bdheal.db"
    store = SqliteHealStore(connect(db_path))
    with pytest.raises(RuntimeError):
        run_benchmark(
            RUN_ID,
            cases,
            loop_for(cases, store, bench_clock, crash_on=cases[2].spec.collector_id),
            store,
            bench_clock,
        )

    reopened = SqliteHealStore(connect(db_path))
    remaining = run_benchmark(
        RUN_ID, cases, loop_for(cases, reopened, bench_clock), reopened, bench_clock
    )

    assert [outcome.case_id for outcome in remaining] == ["case_3", "case_4"]
    assert sorted(reopened.completed_case_ids(RUN_ID)) == [
        "case_1",
        "case_2",
        "case_3",
        "case_4",
    ]


def test_one_run_never_reads_the_cases_of_another(tmp_path: Path) -> None:
    """Two benchmarks can share a store file, and neither may publish the other's numbers."""
    store = SqliteHealStore(connect(tmp_path / "bdheal.db"))
    store.save_bench_case(bench_case(run_id=RUN_ID, case_id="case_1"))
    store.save_bench_case(bench_case(run_id="run_bench_02", case_id="case_1", healed=False))

    assert [case.run_id for case in store.bench_cases(RUN_ID)] == [RUN_ID]
