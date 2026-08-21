"""The facade: the one object a caller wires, and where every branch decided upstream falls due.

Four branches, each settled by the verification that found it, so each gets its own test
rather than a happy path with flags on it. A gate call that failed is not promoted —
the row is written before the error is re-raised, so the catch is the branch. A
verification the target refused is retried, never rolled back — rolling it back would
discard a heal that was never tested and publish a non-regression failure nobody measured.
A report that came back false is rolled back. And ambiguous error codes are retried once
and become extraction evidence only if the same ones come back.

The loop tests run against a real SQLite file under `tmp_path` rather than the in-memory
store, because the facade is the first thing that writes a whole cycle's rows and reads
them back: a row that only round-trips through a dictionary proves nothing about the
schema that ships in the wheel.
"""

import inspect
import json
import types
from pathlib import Path

import pytest
from conftest import (
    STRANDED_GATE_STDERR,
    ForbiddenRunner,
    RecordingRunner,
    StubStudioClient,
    row_error,
    run_result,
)

import bdheal
from bdheal import healer as healer_module
from bdheal.errors import VerificationIncompleteError
from bdheal.healer import Healer
from bdheal.models import CollectorSpec, DetectVerdict, HealEvent, RunResult, Signal
from bdheal.ports import Clock, HealLoop, HealStore, ProcessResult
from bdheal.skeleton import skeleton_hash
from bdheal.store import SqliteHealStore, connect
from bdheal.studio import BdataStudioClient
from bdheal.vocabulary import HealStatus, SignalKind, SignalOutcome

ANCHOR = "https://example.test/list"
OLD_LAYOUT_URL = "https://example.test/old"

# The same records under two structures, so the skeleton hash moves and the text does not:
# a layout change is exactly what the loop is built to survive.
OLD_LAYOUT_HTML = "<table><tr class='row'><td class='title'>first</td></tr></table>"
NEW_LAYOUT_HTML = "<div class='card'><span class='title'>first</span></div>"

GOLDEN = [
    {"title": "first", "url": "https://example.test/1"},
    {"title": "second", "url": "https://example.test/2"},
]
ROWS = [record | {"published": "2026-01-01"} for record in GOLDEN]

# The ten names `bdheal` publishes, and nothing else (criterion (d)).
EXPORTS = [
    "Baseline",
    "BenchCase",
    "CollectorSpec",
    "DetectVerdict",
    "HealEvent",
    "Healer",
    "RowError",
    "RunResult",
    "Signal",
    "VerifyReport",
]

# The port names the facade must satisfy structurally, so `bench/runner.py` can take a
# `HealLoop` and never name its parent.
LOOP_METHODS = {"run", "detect", "heal", "verify"}

# What a `Healer` may hold at module level: types, functions, modules and immutable
# constants. Anything else is state the caller did not hand it (criterion (b)).
MODULE_LEVEL_ALLOWED = (
    type,
    types.FunctionType,
    types.ModuleType,
    str,
    int,
    float,
    bool,
    frozenset,
    tuple,
)

# The modules that can start a process or open a file. The facade importing any of them
# would give it a way to reach the network it was never handed (criterion (b)).
TRANSPORT_MODULES = ("bdheal.studio", "bdheal.store", "bdheal.process", "bdheal.clock")

# The three heal envelopes the gate can be driven through, and the refusal a collector
# still holding an earlier job answers with.
PENDING_ENVELOPE = json.dumps({"status": "awaiting_approval"})
DONE_ENVELOPE = json.dumps({"status": "done"})
REJECTED_ENVELOPE = json.dumps({"status": "rejected"})
GATE_BUSY_REFUSAL = ProcessResult(returncode=1, stdout="", stderr=STRANDED_GATE_STDERR)

BROKEN_VERDICT = DetectVerdict(
    broken=True,
    signals=[
        Signal(
            kind=SignalKind.SKELETON,
            outcome=SignalOutcome.FIRED,
            detail="the page's tag and class tree no longer hashes to the stored one",
        )
    ],
)


def ok(stdout: str) -> ProcessResult:
    """A successful command with its JSON envelope on stdout."""
    return ProcessResult(returncode=0, stdout=stdout, stderr="")


def sent(runner: RecordingRunner, subcommand: str) -> list[list[str]]:
    """Every argv the loop sent for one `bdata scraper` subcommand, in order."""
    return [argv for argv in runner.argvs if subcommand in argv]


def healthy_run() -> RunResult:
    """A run that returned every record whole."""
    return run_result(rows=ROWS)


def broken_run() -> RunResult:
    """A run whose rows came back and did not validate — extraction evidence, not a refusal."""
    return run_result(
        rows=[],
        errors=[row_error(0, message="title missing", field_errors={"title": "field required"})],
    )


def refused_run(code: str) -> RunResult:
    """A run one of whose inputs the target answered with `code` instead of a record."""
    return run_result(rows=ROWS, errors=[row_error(0, error_code=code)])


def empty_run() -> RunResult:
    """A run that recovered nothing at all."""
    return run_result(rows=[])


@pytest.fixture
def filed_store(tmp_path: Path) -> HealStore:
    """A `HealStore` on a real SQLite file, typed as the port (criterion (a))."""
    return SqliteHealStore(connect(tmp_path / "bdheal.db"))


@pytest.fixture
def healer(studio: StubStudioClient, filed_store: HealStore, clock: Clock) -> Healer:
    """The facade under test, both ports and the clock injected."""
    return Healer(studio, filed_store, clock)


def establish_baseline(healer: Healer, studio: StubStudioClient, spec: CollectorSpec) -> None:
    """One clean run, so the collector has a known-good shape to be judged against."""
    studio.pages[ANCHOR] = OLD_LAYOUT_HTML
    studio.run_results = [healthy_run()]
    healer.detect(spec, healer.run(spec, spec.anchor_urls))


def break_the_layout(
    healer: Healer, studio: StubStudioClient, spec: CollectorSpec
) -> DetectVerdict:
    """Rebuild the page under the collector and judge what comes back."""
    studio.pages[ANCHOR] = NEW_LAYOUT_HTML
    studio.run_results = [broken_run()]
    return healer.detect(spec, healer.run(spec, spec.anchor_urls))


def heal_a_break(healer: Healer, studio: StubStudioClient, spec: CollectorSpec) -> HealEvent:
    """Everything up to the gate settling: a baseline, a break, and a heal that reached done."""
    establish_baseline(healer, studio, spec)
    return healer.heal(spec, break_the_layout(healer, studio, spec))


def runs(studio: StubStudioClient) -> int:
    """How many times the collector was actually run."""
    return sum(1 for call in studio.calls if call[0] == "run")


def test_a_break_is_detected_healed_verified_and_promoted(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """(a) The whole loop over one collector, through the ports and a real store file."""
    establish_baseline(healer, studio, spec)

    verdict = break_the_layout(healer, studio, spec)
    assert verdict.broken is True
    assert SignalKind.SKELETON in verdict.fired_kinds

    event = healer.heal(spec, verdict)
    assert event.status is HealStatus.DONE
    assert event.promoted is True

    studio.run_results = [healthy_run(), healthy_run(), healthy_run()]
    report = healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    assert report.field_accuracy == 1.0
    assert report.non_regression_passed is True
    assert filed_store.heal_events(spec.collector_id)[-1].promoted is True


def test_a_refused_confirming_run_does_not_become_the_new_baseline(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """A promotion whose confirming run was half-refused must not move the known-good shape.

    `_judge` always guarded this; `_remember` did not, so the one path that runs *after* a
    successful heal could store a truncated sample as healthy. The volume detectors would
    then measure against the truncation and the next genuine break would not fire — the
    exact failure the guard exists to prevent, reached by the path that skipped it.
    """
    heal_a_break(healer, studio, spec)
    before = filed_store.baseline(spec.collector_id)

    # verify's two passes are whole; the confirming run that follows promotion is refused.
    studio.run_results = [healthy_run(), healthy_run(), refused_run("rate_limit")]
    healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    after = filed_store.baseline(spec.collector_id)
    assert after == before, "a truncated confirming run must leave the baseline alone"


def test_the_loop_reaches_bright_data_through_the_injected_port_and_nowhere_else(
    healer: Healer, studio: StubStudioClient, spec: CollectorSpec
) -> None:
    """(a) Every outward step is one of the port's four calls, recorded on the stub."""
    heal_a_break(healer, studio, spec)
    studio.run_results = [healthy_run(), healthy_run(), healthy_run()]
    healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    assert {call[0] for call in studio.calls} == {"run", "fetch_html", "heal", "approve"}


def test_no_loop_step_starts_a_process(
    forbidden_runner: ForbiddenRunner, filed_store: HealStore, clock: Clock, spec: CollectorSpec
) -> None:
    """(a) `CommandRunner` is the one door out of this package; nailed shut, none opens."""
    healer = Healer(BdataStudioClient(forbidden_runner, clock), filed_store, clock)

    with pytest.raises(AssertionError, match="must not start a process"):
        healer.run(spec, spec.anchor_urls)


def test_both_ports_and_the_clock_are_required_constructor_arguments() -> None:
    """(b) Nothing is defaulted, so a `Healer` cannot be built with a client nobody chose."""
    parameters = inspect.signature(Healer).parameters

    assert list(parameters) == ["studio", "store", "clock"]
    assert all(
        parameter.default is inspect.Parameter.empty for parameter in parameters.values()
    )


def test_the_facade_can_build_no_transport_of_its_own() -> None:
    """(b) It imports no adapter, so there is no implicit default that reaches the network."""
    source = inspect.getsource(healer_module)

    assert [name for name in TRANSPORT_MODULES if name in source] == []


def test_the_facade_module_holds_no_state() -> None:
    """(b) No module-level client and no global anything — only types, functions, constants."""
    held = {
        name: value
        for name, value in vars(healer_module).items()
        if not name.startswith("__") and not isinstance(value, MODULE_LEVEL_ALLOWED)
    }

    assert held == {}


def test_a_verification_that_failed_leaves_the_collector_unpromoted(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """(c) An overfit heal is rolled back, and the row says so."""
    heal_a_break(healer, studio, spec)
    studio.run_results = [healthy_run(), empty_run()]

    report = healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    assert report.non_regression_passed is False
    settled = filed_store.heal_events(spec.collector_id)[-1]
    assert settled.promoted is False
    assert settled.status is HealStatus.REJECTED


def test_a_rolled_back_heal_leaves_the_known_good_shape_where_it_was(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """(c) The baseline is this package's stand-in for a schema version, and a rollback leaves it."""
    heal_a_break(healer, studio, spec)
    before = filed_store.baseline(spec.collector_id)
    studio.run_results = [healthy_run(), empty_run()]

    healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    assert filed_store.baseline(spec.collector_id) == before


def test_a_heal_that_recovered_nothing_is_not_promoted_by_the_old_layout_alone(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """(c) A collector extracting nothing regresses nothing, so accuracy tells a repair from a no-op."""
    heal_a_break(healer, studio, spec)
    studio.run_results = [empty_run(), healthy_run()]

    report = healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    assert report.non_regression_passed is True
    assert report.field_accuracy == 0.0
    assert filed_store.heal_events(spec.collector_id)[-1].promoted is False


def test_a_promoted_heal_records_the_new_known_good_shape(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """The rollback's counterpart: promotion is what moves the baseline, so (c) is not vacuous."""
    heal_a_break(healer, studio, spec)
    before = filed_store.baseline(spec.collector_id)
    studio.run_results = [healthy_run(), healthy_run(), healthy_run()]

    healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    after = filed_store.baseline(spec.collector_id)
    assert after != before
    assert after.skeleton_hash == skeleton_hash(NEW_LAYOUT_HTML)


def test_a_promoted_collector_is_not_healed_again_on_the_next_run(
    healer: Healer, studio: StubStudioClient, spec: CollectorSpec
) -> None:
    """Why promotion records the new shape: a stale baseline re-fires forever, healing every run."""
    heal_a_break(healer, studio, spec)
    studio.run_results = [healthy_run(), healthy_run(), healthy_run()]
    healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    studio.run_results = [healthy_run()]
    verdict = healer.detect(spec, healer.run(spec, spec.anchor_urls))

    assert verdict.broken is False


def test_the_package_exports_exactly_ten_names() -> None:
    """(d) The public surface is a decision, not whatever happened to be importable."""
    assert bdheal.__all__ == EXPORTS


def test_every_exported_name_is_reachable_from_the_top_level() -> None:
    """(d) `from bdheal import Healer` and its nine siblings, with no submodule path."""
    assert [name for name in EXPORTS if not hasattr(bdheal, name)] == []
    assert bdheal.Healer is Healer


def test_a_gate_call_that_failed_is_not_promoted(
    recording_runner: RecordingRunner, filed_store: HealStore, clock: Clock, spec: CollectorSpec
) -> None:
    """Branch 1: the gate records its failure and re-raises, so the catch is the branch."""
    recording_runner.results.append(
        ProcessResult(returncode=2, stdout="", stderr="collector not found")
    )
    healer = Healer(BdataStudioClient(recording_runner, clock), filed_store, clock)

    event = healer.heal(spec, BROKEN_VERDICT)

    assert event.status is HealStatus.FAILED
    assert event.promoted is False
    assert filed_store.heal_events(spec.collector_id) == [event]


def test_a_heal_a_stranded_gate_refused_clears_that_gate_and_heals(
    recording_runner: RecordingRunner, filed_store: HealStore, clock: Clock, spec: CollectorSpec
) -> None:
    """The collector stranded on 2026-08-20 could have healed itself; instead it waited.

    Bright Data allows one open job per collector, so a gate an earlier process left
    parked refuses every heal after it — for five hours, in the incident, until a human
    sent `--reject`. Nothing was wrong with the collector, and nothing was wrong with the
    new heal: the loop simply had no way to say "clear the stale one and carry on". So it
    does that here, exactly once, and the second attempt is the one that heals.
    """
    recording_runner.results.extend(
        [GATE_BUSY_REFUSAL, ok(REJECTED_ENVELOPE), ok(PENDING_ENVELOPE), ok(DONE_ENVELOPE)]
    )
    healer = Healer(BdataStudioClient(recording_runner, clock), filed_store, clock)

    event = healer.heal(spec, BROKEN_VERDICT)

    assert event.status is HealStatus.DONE
    assert event.promoted is True
    assert "--reject" in sent(recording_runner, "approve")[0], "the stale gate was cleared first"
    assert len(sent(recording_runner, "heal")) == 2


def test_a_gate_that_will_not_clear_stops_the_loop_rather_than_cycling_it(
    recording_runner: RecordingRunner, filed_store: HealStore, clock: Clock, spec: CollectorSpec
) -> None:
    """Recovery is one attempt. A collector Bright Data keeps refusing is not a heal to retry.

    Every attempt is billable and each one is two calls — the rejection and the heal — so
    a loop that kept trying would spend a collector's budget on a job it cannot displace.
    The second refusal is reported as what it is: a heal that never ran, on a collector
    still occupied, which a later run may find free.
    """
    recording_runner.results.extend(
        [GATE_BUSY_REFUSAL, ok(REJECTED_ENVELOPE), GATE_BUSY_REFUSAL, ok(REJECTED_ENVELOPE)]
    )
    healer = Healer(BdataStudioClient(recording_runner, clock), filed_store, clock)

    event = healer.heal(spec, BROKEN_VERDICT)

    assert event.status is HealStatus.GATE_BUSY
    assert event.promoted is False
    assert len(sent(recording_runner, "heal")) == 2, "one recovery attempt, never a loop"


def test_a_gate_cycle_is_read_from_its_terminal_row_not_from_a_row_count(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """A gated heal writes two rows. The outcome is the last word, never the tally."""
    event = healer.heal(spec, BROKEN_VERDICT)

    rows = filed_store.heal_events(spec.collector_id)
    assert [row.status for row in rows] == [HealStatus.AWAITING_APPROVAL, HealStatus.DONE]
    assert event == rows[-1]


def test_the_settlement_row_carries_the_heal_it_settles(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """A row that does not say what it was settling cannot be read back as evidence."""
    healed = heal_a_break(healer, studio, spec)
    studio.run_results = [healthy_run(), empty_run()]

    healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    settled = filed_store.heal_events(spec.collector_id)[-1]
    assert settled.prompt == healed.prompt
    assert settled.template_id == healed.template_id
    assert settled.failure_class is healed.failure_class


def test_a_verification_the_target_refused_is_retried_rather_than_rolled_back(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """Branch 2: the heal was never tested, so a refusal buys a retry, not a rollback."""
    heal_a_break(healer, studio, spec)
    studio.run_results = [refused_run("blocked"), healthy_run(), healthy_run(), healthy_run()]

    report = healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    assert report.attempts == 2
    assert report.non_regression_passed is True
    assert filed_store.heal_events(spec.collector_id)[-1].promoted is True


def test_a_verification_the_target_keeps_refusing_reaches_the_caller_unscored(
    healer: Healer, studio: StubStudioClient, filed_store: HealStore, spec: CollectorSpec
) -> None:
    """Branch 2, exhausted: no measurement was taken, so none is published and none is settled."""
    heal_a_break(healer, studio, spec)
    settled_before = len(filed_store.heal_events(spec.collector_id))
    studio.run_results = [refused_run("blocked"), refused_run("blocked")]

    with pytest.raises(VerificationIncompleteError):
        healer.verify(spec, GOLDEN, OLD_LAYOUT_URL)

    assert len(filed_store.heal_events(spec.collector_id)) == settled_before


def test_an_ambiguous_code_that_clears_on_a_retry_is_not_a_break(
    healer: Healer, studio: StubStudioClient, spec: CollectorSpec
) -> None:
    """Branch 4: one run cannot tell a refused fetch from a collector asking wrongly."""
    establish_baseline(healer, studio, spec)
    studio.calls.clear()
    studio.run_results = [refused_run("dead_page"), healthy_run()]

    verdict = healer.detect(spec, healer.run(spec, spec.anchor_urls))

    assert verdict.broken is False
    assert verdict.ambiguous_codes == ()
    assert runs(studio) == 2


def test_ambiguous_codes_that_survive_a_retry_become_break_evidence(
    healer: Healer, studio: StubStudioClient, spec: CollectorSpec
) -> None:
    """Branch 4, escalated: a code that comes back twice is no longer plausibly transient."""
    establish_baseline(healer, studio, spec)
    studio.calls.clear()
    studio.run_results = [refused_run("dead_page"), refused_run("dead_page")]

    verdict = healer.detect(spec, healer.run(spec, spec.anchor_urls))

    assert verdict.broken is True
    assert verdict.retry_requested is False
    assert "dead_page" in verdict.reason
    assert runs(studio) == 2


def test_an_escalated_verdict_heals_under_the_generic_template(
    healer: Healer, studio: StubStudioClient, spec: CollectorSpec
) -> None:
    """No detector saw this, so no signal is fabricated: the generic prompt is the honest one."""
    establish_baseline(healer, studio, spec)
    studio.run_results = [refused_run("dead_page"), refused_run("dead_page")]
    verdict = healer.detect(spec, healer.run(spec, spec.anchor_urls))

    event = healer.heal(spec, verdict)

    assert event.template_id == "generic.v1"
    assert event.promoted is True


def test_healing_a_verdict_that_is_not_broken_is_refused(
    healer: Healer, studio: StubStudioClient, spec: CollectorSpec
) -> None:
    """A heal is a paid change to a live collector; nothing to fix means nothing to send."""
    with pytest.raises(ValueError, match="nothing to heal"):
        healer.heal(spec, DetectVerdict(broken=False))

    assert studio.calls == []


def test_healer_satisfies_the_heal_loop_port(healer: Healer) -> None:
    """The benchmark takes a `HealLoop`, so drift between the two must fail here, not there.

    Signatures are compared rather than merely annotated: `HealLoop` is not
    `runtime_checkable`, and an annotation alone is checked by nobody in a suite with no
    type checker in its dev dependencies.
    """
    loop: HealLoop = healer
    declared = {
        name
        for name, value in vars(HealLoop).items()
        if callable(value) and not name.startswith("_")
    }

    assert declared == LOOP_METHODS
    for name in sorted(declared):
        assert inspect.signature(getattr(type(loop), name)) == inspect.signature(
            getattr(HealLoop, name)
        ), name
