"""The approval gate: the first place this package proposes a real change to a live collector.

Three things are worth more than the rest here. The collector id must survive every path
byte-identical, because Bright Data heals in place and a changed id silently detaches
every baseline and every heal row keyed to the old one. The prompt is AI-generated free
text, so it is the realistic injection surface and must stay one argv element whatever it
contains (G3). And a row must reach the store on every terminal outcome, rejection and
failure included — a heal log holding only successes is not an audit trail.

The argv assertions drive the real `BdataStudioClient` over an injected runner: the gate
is what decides *when* to call heal and approve, and asserting the shape of what actually
leaves is the only way that decision is checked end to end without a process starting.
"""

import json
from dataclasses import replace

import pytest
from conftest import (
    ARRAY_PREVIEW_RESULT,
    FAKE_API_KEY,
    FAKE_BEARER_TOKEN,
    FAKE_SHORT_TOKEN,
    STRANDED_GATE_STDERR,
    RecordingRunner,
    SampleRow,
    StubStudioClient,
    heal_event,
)

from bdheal.diagnose import Diagnosis
from bdheal.errors import GateBusyError, NotPendingError, StudioError, StudioResponseError
from bdheal.heal import approve, heal
from bdheal.models import CollectorSpec, HealEvent
from bdheal.ports import Clock, HealStore, ProcessResult
from bdheal.studio import REDACTED, BdataStudioClient
from bdheal.vocabulary import FailureClass, HealStatus

ANCHOR = "https://example.test/list"

# What `npx` prints when the process it wrapped exits non-zero: the command line it ran,
# credential included. Nothing in this package builds that string — it arrives on stderr.
KEY_IN_ARGV_STDERR = (
    f"Command failed: npx -p @brightdata/cli bdata scraper heal --api-key {FAKE_API_KEY}\n"
    "Error: 401 Unauthorized"
)

# The same credential wearing the header the HTTP layer sends it in.
BEARER_HEADER_STDERR = (
    f"heal request rejected\nAuthorization: Bearer {FAKE_BEARER_TOKEN}\nError: 403 Forbidden"
)

# The id from a real v0.3.5 collector with a shell payload welded on. It is passed
# unchanged through the gate, so both the byte-identical check and the injection check
# read the same value.
HOSTILE_ID = 'c_msyrpgjw2g2fefflg1"; rm -rf / #'

DIAGNOSIS = Diagnosis(
    failure_class=FailureClass.STRUCTURE_CHANGED,
    template_id="structure_changed.v1",
    prompt="Re-locate the repeating row container and re-derive every selector.",
)

# Quotes, a newline, a command separator, a substitution and a background operator: a
# prompt is free text an AI wrote, and none of this may become a second argv element.
HOSTILE_PROMPT = (
    'The row container is now `<div class="row">`, not "<tr>".\n'
    "Re-derive every selector; rm -rf / # $(whoami) && echo done | tee /tmp/x\n"
)
HOSTILE_DIAGNOSIS = replace(DIAGNOSIS, prompt=HOSTILE_PROMPT)

PENDING_ENVELOPE = json.dumps(
    {"status": "awaiting_approval", "preview_result": {"title": "A Light in the Attic"}}
)
DONE_ENVELOPE = json.dumps({"status": "done"})


def ok(stdout: str) -> ProcessResult:
    """A successful command with its JSON envelope on stdout."""
    return ProcessResult(returncode=0, stdout=stdout, stderr="")


def failed(reason: str) -> ProcessResult:
    """A command `bdata` refused, with its reason on stderr."""
    return ProcessResult(returncode=2, stdout="", stderr=reason)


def adapter(runner: RecordingRunner, clock: Clock) -> BdataStudioClient:
    """The real argv-shaping adapter, wired to a runner that starts nothing."""
    return BdataStudioClient(runner, clock)


def spec_for(collector_id: str) -> CollectorSpec:
    """A generic spec for one collector id."""
    return CollectorSpec(
        collector_id=collector_id,
        name="stub collector",
        anchor_urls=[ANCHOR],
        row_schema=SampleRow,
    )


def every_gate_path(
    spec: CollectorSpec, studio: StubStudioClient, store: HealStore, clock: Clock
) -> list[HealEvent]:
    """Every outcome the gate can reach without the CLI failing: pending, done, rejected, unattended."""
    pending = heal(spec, DIAGNOSIS, studio, store, clock)
    approved = approve(spec, pending, studio, store, clock)
    rejected = approve(spec, pending, studio, store, clock, reject=True)
    unattended = heal(spec, DIAGNOSIS, studio, store, clock, auto_approve=True)
    return [pending, approved, rejected, unattended]


def test_the_gated_path_yields_a_pending_event_carrying_its_preview(
    studio: StubStudioClient, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """`preview_result` is the free pre-promotion check; a gate that drops it wastes it."""
    studio.heal_events.append(heal_event())

    event = heal(spec, DIAGNOSIS, studio, store, clock)

    assert event.status is HealStatus.AWAITING_APPROVAL
    assert event.preview_result == {"rows": [{"title": "a", "url": "https://example.test/a"}]}
    assert event.promoted is False


def test_approving_a_pending_heal_promotes_the_collector(
    studio: StubStudioClient, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The approve half of the gate: done, and promoted."""
    pending = heal(spec, DIAGNOSIS, studio, store, clock)

    event = approve(spec, pending, studio, store, clock)

    assert event.status is HealStatus.DONE
    assert event.promoted is True


def test_rejecting_a_pending_heal_leaves_it_unpromoted(
    studio: StubStudioClient, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """A rejected heal changes nothing on the collector, and says so in the row it writes."""
    pending = heal(spec, DIAGNOSIS, studio, store, clock)

    event = approve(spec, pending, studio, store, clock, reject=True)

    assert event.status is HealStatus.REJECTED
    assert event.promoted is False
    assert store.heal_events(spec.collector_id)[-1].status is HealStatus.REJECTED


def test_the_unattended_path_reaches_done_without_a_second_call(
    studio: StubStudioClient, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """`--auto-approve` skips the gate; issuing an approve as well would be a second paid call."""
    event = heal(spec, DIAGNOSIS, studio, store, clock, auto_approve=True)

    assert event.status is HealStatus.DONE
    assert event.promoted is True
    assert [call[0] for call in studio.calls] == ["heal"]


def test_the_collector_id_is_byte_identical_through_every_path(
    store: HealStore, clock: Clock
) -> None:
    """Heal is in place. A reshaped id detaches every baseline and heal row keyed to the old one."""
    spec = spec_for(HOSTILE_ID)

    events = every_gate_path(spec, StubStudioClient(clock), store, clock)

    assert [event.collector_id for event in events] == [HOSTILE_ID] * len(events)
    assert [row.collector_id for row in store.heal_events(HOSTILE_ID)] == [HOSTILE_ID] * len(events)


def test_every_outcome_writes_exactly_one_event(
    studio: StubStudioClient, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """One gate call, one row — including the rejection."""
    every_gate_path(spec, studio, store, clock)

    assert [row.status for row in store.heal_events(spec.collector_id)] == [
        HealStatus.AWAITING_APPROVAL,
        HealStatus.DONE,
        HealStatus.REJECTED,
        HealStatus.DONE,
    ]


def test_the_diagnosis_travels_onto_the_persisted_event(
    studio: StubStudioClient, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """A row that does not say what it was healing for cannot be read back as evidence."""
    pending = heal(spec, DIAGNOSIS, studio, store, clock)
    approve(spec, pending, studio, store, clock, reject=True)

    for row in store.heal_events(spec.collector_id):
        assert row.failure_class is DIAGNOSIS.failure_class
        assert row.template_id == DIAGNOSIS.template_id
        assert row.prompt == DIAGNOSIS.prompt


@pytest.mark.parametrize(
    ("status", "claimed_by_the_adapter", "promoted"),
    [
        (HealStatus.DONE, False, True),
        (HealStatus.AWAITING_APPROVAL, True, False),
        (HealStatus.REJECTED, True, False),
        (HealStatus.FAILED, True, False),
    ],
)
def test_the_gate_decides_promotion_not_the_adapter(
    status: HealStatus,
    claimed_by_the_adapter: bool,
    promoted: bool,
    studio: StubStudioClient,
    store: HealStore,
    spec: CollectorSpec,
    clock: Clock,
) -> None:
    """What counts as promoted is the gate's call: the CLI reports a status, not a promotion."""
    studio.heal_events.append(heal_event(status=status, promoted=claimed_by_the_adapter))

    event = heal(spec, DIAGNOSIS, studio, store, clock)

    assert event.promoted is promoted
    assert store.heal_events(spec.collector_id)[-1].promoted is promoted


def test_the_heal_argv_carries_no_url_and_the_approve_argv_does(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """`--url` is a next-step hint on heal but the anchor on approve (verified against the CLI surface)."""
    recording_runner.results.extend([ok(PENDING_ENVELOPE), ok(DONE_ENVELOPE)])
    studio = adapter(recording_runner, clock)

    pending = heal(spec, DIAGNOSIS, studio, store, clock)
    approve(spec, pending, studio, store, clock)

    heal_argv, approve_argv = recording_runner.argvs
    assert "--url" not in heal_argv
    assert ANCHOR not in heal_argv
    assert approve_argv[approve_argv.index("--url") + 1] == ANCHOR


def test_the_unattended_path_puts_auto_approve_in_the_argv(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The flag is what makes the path unattended; without it the collector waits forever."""
    recording_runner.results.append(ok(DONE_ENVELOPE))

    heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock, auto_approve=True)

    assert "--auto-approve" in recording_runner.argvs[0]
    assert len(recording_runner.argvs) == 1


def test_the_gated_path_leaves_auto_approve_out_of_the_argv(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The gate exists to be waited on: an unasked-for auto-approve promotes without review."""
    recording_runner.results.append(ok(PENDING_ENVELOPE))

    heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    assert "--auto-approve" not in recording_runner.argvs[0]


def test_a_hostile_prompt_stays_one_argv_element(
    recording_runner: RecordingRunner, store: HealStore, clock: Clock
) -> None:
    """Quotes, newlines and shell metacharacters are content, never syntax (G3)."""
    recording_runner.results.append(ok(PENDING_ENVELOPE))
    spec = spec_for(HOSTILE_ID)

    heal(spec, HOSTILE_DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    argv = recording_runner.argvs[0]
    assert argv.count(HOSTILE_PROMPT) == 1
    assert argv.count(HOSTILE_ID) == 1
    assert all(isinstance(element, str) for element in argv)
    assert [element for element in argv if "rm -rf" in element] == [HOSTILE_ID, HOSTILE_PROMPT]


def test_a_heal_that_raised_on_its_way_out_rejects_the_gate_it_would_have_stranded(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The whole incident of 2026-08-20, in one path: the raise came *after* the repair.

    Bright Data ran the refactor, saved it and parked at the approval gate. Only then did
    the envelope fail to parse here, so the exception left the collector waiting for an
    answer no code would ever send. Bright Data allows one open job per collector, so the
    collector stayed occupied for five hours and every heal after it was refused outright
    — until a human sent `--reject` by hand and it worked immediately. The parse bug is
    fixed; the next unforeseen raise on this path must not cost another five hours.
    """
    recording_runner.results.append(ok(json.dumps(ARRAY_PREVIEW_RESULT)))

    with pytest.raises(StudioResponseError):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    released = recording_runner.argvs[-1]
    assert len(recording_runner.argvs) == 2, "the failed heal, then the rejection that frees it"
    assert "--reject" in released
    assert released[released.index("--url") + 1] == ANCHOR


def test_a_gate_release_that_fails_never_replaces_the_error_the_caller_must_see(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The cleanup is best-effort: it may fail, and it may not become the failure reported.

    A rejection that itself errors would otherwise surface in place of the parse error
    that caused the mess, and the operator would spend the outage debugging the wrong
    call. It is attached to the original rather than dropped, so nothing is swallowed.
    """
    recording_runner.results.extend(
        [ok(json.dumps(ARRAY_PREVIEW_RESULT)), failed("no job pending")]
    )

    with pytest.raises(StudioResponseError) as raised:
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    assert "expected a JSON object" in str(raised.value)
    assert any("no job pending" in note for note in getattr(raised.value, "__notes__", []))


def test_a_gate_that_settled_is_never_asked_to_release_itself(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """A call that was never made is not a flag violation, so nothing else can catch this.

    Every trip through the gate is billable, and the cleanup exists for the path where
    something raised. Firing it on a heal that settled normally would pay a second time on
    every cycle, and a `--reject` after an approval could only ever be refused anyway.
    """
    recording_runner.results.extend([ok(PENDING_ENVELOPE), ok(DONE_ENVELOPE)])
    studio = adapter(recording_runner, clock)

    pending = heal(spec, DIAGNOSIS, studio, store, clock)
    approve(spec, pending, studio, store, clock)

    assert len(recording_runner.argvs) == 2, "one heal, one approve, and nothing else"
    assert [argv for argv in recording_runner.argvs if "--reject" in argv] == []


def test_a_failed_approval_releases_the_gate_it_could_not_settle(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The gate's second half strands a collector exactly as expensively as its first.

    An approval that raised leaves the heal parked, and the next heal on that collector is
    refused for as long as it stays there. The rejection is sent even though the approval
    may in fact have landed: a reject with nothing pending is refused harmlessly, while a
    gate nobody closed costs the collector's availability.
    """
    recording_runner.results.extend([ok(PENDING_ENVELOPE), failed("approval expired")])
    studio = adapter(recording_runner, clock)

    pending = heal(spec, DIAGNOSIS, studio, store, clock)
    with pytest.raises(StudioError, match="approval expired"):
        approve(spec, pending, studio, store, clock)

    assert "--reject" in recording_runner.argvs[-1]
    assert len(recording_runner.argvs) == 3, "the heal, the approval that failed, the release"


def test_a_heal_an_occupied_collector_refused_is_recorded_as_busy_not_failed(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """`failed` cannot mean both "Bright Data refused to start" and "the repair was no good".

    The row for a collector still holding an earlier job is the one row that says *try
    again*: nothing was diagnosed wrongly and nothing was rejected on its merits — the
    heal never ran. Recorded as `failed` it reads as a heal that was attempted and lost,
    and the benchmark counts it against the loop's success rate for a call the loop was
    never allowed to make.
    """
    recording_runner.results.append(failed(STRANDED_GATE_STDERR))

    with pytest.raises(GateBusyError):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    (row,) = store.heal_events(spec.collector_id)
    assert row.status is HealStatus.GATE_BUSY
    assert row.promoted is False
    assert "Another refactor job is still in progress" in row.error


def test_a_failed_heal_is_recorded_before_the_error_reaches_the_caller(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """A heal that failed is exactly the row you want when reading the log later."""
    recording_runner.results.append(failed("collector not found"))

    with pytest.raises(StudioError, match="collector not found"):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    (row,) = store.heal_events(spec.collector_id)
    assert row.status is HealStatus.FAILED
    assert row.promoted is False
    assert "collector not found" in row.error
    assert row.prompt == DIAGNOSIS.prompt
    assert row.failure_class is DIAGNOSIS.failure_class


def test_a_failed_approval_is_recorded_before_the_error_reaches_the_caller(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The gate's second half fails the same way, and leaves the same evidence."""
    recording_runner.results.extend([ok(PENDING_ENVELOPE), failed("approval expired")])
    studio = adapter(recording_runner, clock)

    pending = heal(spec, DIAGNOSIS, studio, store, clock)
    with pytest.raises(StudioError, match="approval expired"):
        approve(spec, pending, studio, store, clock)

    row = store.heal_events(spec.collector_id)[-1]
    assert row.status is HealStatus.FAILED
    assert row.promoted is False
    assert row.template_id == DIAGNOSIS.template_id


def test_a_failed_gate_call_records_the_reason_without_the_argv(
    recording_runner: RecordingRunner, store: HealStore, clock: Clock
) -> None:
    """G6: the persisted row explains the failure and names neither the command nor its values."""
    recording_runner.results.append(failed("collector not found"))
    spec = spec_for(HOSTILE_ID)

    with pytest.raises(StudioError):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    (row,) = store.heal_events(HOSTILE_ID)
    assert "npx" not in row.error
    assert HOSTILE_ID not in row.error


def test_a_credential_echoed_by_the_cli_never_reaches_the_persisted_row(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """G6, from the other direction: the leak the package does not author but does persist.

    `npx` prints the command line it ran when the wrapped process fails, so an auth
    failure arrives on stderr with the key in it. That excerpt becomes the exception
    message, which the gate writes to `bdheal_heal_events.error` — a credential at rest
    in the application's database, put there by a package that never read one.
    """
    recording_runner.results.append(failed(KEY_IN_ARGV_STDERR))

    with pytest.raises(StudioError):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    (row,) = store.heal_events(spec.collector_id)
    assert FAKE_API_KEY not in row.error
    assert REDACTED in row.error, "redacted, not dropped: the operator still needs the failure"
    assert "401" in row.error


def test_an_authorization_header_echoed_by_the_cli_never_reaches_the_persisted_row(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The same leak wearing a header: a bearer token is a credential however it is spelled."""
    recording_runner.results.append(failed(BEARER_HEADER_STDERR))

    with pytest.raises(StudioError):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    (row,) = store.heal_events(spec.collector_id)
    assert FAKE_BEARER_TOKEN not in row.error
    assert REDACTED in row.error
    assert "403" in row.error


def test_a_short_bearer_token_is_redacted_like_a_long_one(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """A credential is a credential at any length, and the short one is the regression.

    The `Authorization:` pattern once matched only the scheme word, rewriting
    `Authorization: Bearer <token>` to `Authorization: [redacted] <token>` and consuming
    the word `Bearer` so the bearer pattern never fired. Tokens of 24+ characters were
    still caught by the opaque-run catch-all — so the suite's long JWT passed while a
    short session token leaked verbatim into this row. Pinning the short case means the
    catch-all can never mask that pattern being wrong again.
    """
    stderr = f"heal rejected\nAuthorization: Bearer {FAKE_SHORT_TOKEN}\nError: 403 Forbidden"
    recording_runner.results.append(failed(stderr))

    with pytest.raises(StudioError):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    (row,) = store.heal_events(spec.collector_id)
    assert FAKE_SHORT_TOKEN not in row.error
    assert REDACTED in row.error
    assert "403" in row.error, "redaction must not take the diagnosis with it"


def test_the_store_assigns_the_event_its_id(
    studio: StubStudioClient, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """The gate returns what was persisted, so a caller can refer to the row it just wrote."""
    event = heal(spec, DIAGNOSIS, studio, store, clock)

    assert event.id is not None
    assert store.heal_events(spec.collector_id) == [event]


def test_the_gate_uses_the_injected_clock_when_the_cli_never_answered(
    recording_runner: RecordingRunner, store: HealStore, spec: CollectorSpec, clock: Clock
) -> None:
    """A failure has no envelope, so its timestamp comes from the clock rather than nowhere."""
    recording_runner.results.append(failed("collector not found"))

    with pytest.raises(StudioError):
        heal(spec, DIAGNOSIS, adapter(recording_runner, clock), store, clock)

    (row,) = store.heal_events(spec.collector_id)
    assert row.created_at == clock.now()


def test_approving_a_settled_heal_is_refused_before_it_costs_anything(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec, store: HealStore
) -> None:
    """A second approve on a decided heal is a paid call that decides nothing.

    The CLI would accept it, so the gate has to refuse it — and refuse it before the
    runner is touched, not after the money is spent.
    """
    settled = heal_event(status=HealStatus.DONE, promoted=True)
    before = len(recording_runner.argvs)

    with pytest.raises(NotPendingError, match="not awaiting approval"):
        approve(spec, settled, adapter(recording_runner, clock), store, clock)

    assert len(recording_runner.argvs) == before, "the refusal must precede the call"
