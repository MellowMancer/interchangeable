"""The `bdata` boundary: argv shaping, JSON parsing, and error rows that stay data.

Every payload here is copied from a real v0.3.5 run, so a change in the CLI's shape
fails a test rather than a production job. No process starts: the runner is injected,
and the standing check that no call passes `shell` lives in `test_architecture.py`.
"""

import json

import pytest
from conftest import STUB_COLLECTOR_ID, RecordingRunner, SampleRow

from bdheal.errors import CollectorCreateError, StudioError, StudioResponseError
from bdheal.models import CollectorSpec
from bdheal.ports import Clock, ProcessResult
from bdheal.studio import (
    APPROVE,
    BATCH_TIMEOUT_S,
    BDATA_ARGV,
    CREATE,
    DEFAULT_TIMEOUT_S,
    HEAL,
    RUN,
    SCRAPE,
    BdataStudioClient,
)
from bdheal.vocabulary import HealStatus

CLI_DEFAULT_TIMEOUT_S = 600
HOSTILE_ID = 'c_msyrpgjw2g2fefflg1"; rm -rf / #'
ORPHANED_ID = "c_msyrpgjw2g2fefflg1"
BATCH_URLS = ["u1", "u2", "u3"]

# Hand-recorded from `bdata <subcommand> --help` on v0.3.5. A stubbed runner cannot
# reject a flag the CLI has never heard of, so the flag set is asserted here instead.
# `scrape` is a separate top-level Web Unlocker command, not a fifth `scraper` verb: it
# has no `--timeout`, and it defaults to markdown.
ALLOWED_FLAGS: dict[tuple[str, ...], frozenset[str]] = {
    CREATE: frozenset({"--json", "--pretty", "-o", "--timeout", "--max-retries", "--no-retry"}),
    RUN: frozenset({"--json", "--pretty", "-o", "--timeout", "--urls", "--input-file", "--sync"}),
    HEAL: frozenset(
        {
            "--json",
            "--pretty",
            "-o",
            "--timeout",
            "--max-retries",
            "--no-retry",
            "--auto-approve",
            "--auto-save",
            "--url",
        }
    ),
    APPROVE: frozenset({"--json", "--pretty", "-o", "--timeout", "--reject", "--url"}),
    SCRAPE: frozenset(
        {
            "-f",
            "--format",
            "--country",
            "--zone",
            "--mobile",
            "--async",
            "-o",
            "--output",
            "--json",
            "--pretty",
            "--timing",
        }
    ),
}
# `--sync` drives /dca/crawl, which accepts exactly one URL; the batch flags drive
# /dca/trigger. The CLI rejects the combination outright.
EXCLUSIVE_FLAGS = [("--sync", "--urls"), ("--sync", "--input-file")]

TWO_ROWS_ONE_THROTTLED = json.dumps(
    [
        {
            "title": "A Light in the Attic",
            "price": {"value": 51.77, "currency": "GBP"},
            "availability": "In stock (22 available)",
            "url": "https://books.example.test/1",
        },
        {
            "input": {"url": "https://books.example.test/2"},
            "error": "Crawler error: Navigation failed for "
            "https://books.example.test/2: too many requests",
            "error_code": "rate_limit",
        },
        {
            "title": "Tipping the Velvet",
            "price": {"value": 53.74, "currency": "GBP"},
            "availability": "In stock (20 available)",
            "url": "https://books.example.test/3",
        },
    ]
)
ESCALATION_STDOUT = (
    "Realtime page limit exceeded - switching to batch mode...\n"
    "Submitting batch job...\n"
    "Batch job: j_msys99kf83xt17v8m\n"
)
BLOCKED_CREATE_STDOUT = json.dumps(
    {
        "collector_id": ORPHANED_ID,
        "name": "blocked collector",
        "status": "ai_trigger_failed",
        "error": "Domain not allowed",
        "status_code": 400,
    }
)


def ok(stdout: str) -> ProcessResult:
    """A successful command with `stdout` on its standard output."""
    return ProcessResult(returncode=0, stdout=stdout, stderr="")


def client(runner: RecordingRunner, clock: Clock) -> BdataStudioClient:
    """The adapter under test, wired to a runner that starts nothing."""
    return BdataStudioClient(runner, clock)


def every_argv(runner: RecordingRunner, clock: Clock, spec: CollectorSpec) -> list[list[str]]:
    """Every argv the adapter can build: all five subcommands and both run shapes."""
    runner.results.extend(
        [
            ok(json.dumps({"collector_id": ORPHANED_ID, "status": "ready"})),
            ok("[]"),
            ok("[]"),
            ok(ESCALATION_STDOUT),
            ok("[]"),
            ok(json.dumps({"status": "done"})),
            ok(json.dumps({"status": "rejected"})),
            ok("<html></html>"),
        ]
    )
    api = client(runner, clock)
    api.create("https://example.test", "rows")
    api.run(spec, ["u1"])
    api.run(spec, BATCH_URLS)
    api.run(spec, ["u1"])
    api.heal(spec, "restore the title field", auto_approve=True)
    api.approve(spec, "https://example.test/list", reject=True)
    api.fetch_html("https://example.test/list")
    return runner.argvs


def subcommand_of(argv: list[str]) -> tuple[str, ...]:
    """Which `bdata` subcommand an argv invokes."""
    tail = tuple(argv[len(BDATA_ARGV) :])
    for command in ALLOWED_FLAGS:
        if tail[: len(command)] == command:
            return command
    raise AssertionError(f"argv invokes an unknown subcommand: {tail[:2]}")


def flags_in(argv: list[str], command: tuple[str, ...]) -> set[str]:
    """Every option the argv passes to `bdata` itself — the `npx` prefix is not its business."""
    return {
        element
        for element in argv[len(BDATA_ARGV) + len(command) :]
        if element.startswith("-")
    }


def test_per_row_errors_are_data_not_exceptions(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """A throttled row among good ones yields a RowError and an error code, never a raise."""
    recording_runner.results.append(ok(TWO_ROWS_ONE_THROTTLED))

    result = client(recording_runner, clock).run(spec, spec.anchor_urls)

    assert len(result.rows) == 2
    assert [row["title"] for row in result.rows] == ["A Light in the Attic", "Tipping the Velvet"]
    assert len(result.errors) == 1
    assert result.errors[0].index == 1
    assert "too many requests" in result.errors[0].message
    assert result.error_codes == ["rate_limit"]
    assert result.collector_id == spec.collector_id
    assert result.fetched_at == clock.now()


def test_a_schema_failure_is_a_row_error_with_field_detail(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """The caller's schema rejecting a row is per-field evidence, not a stack trace."""
    recording_runner.results.append(ok(json.dumps([{"title": "no url here"}])))

    result = client(recording_runner, clock).run(spec, spec.anchor_urls)

    assert result.rows == []
    assert result.errors[0].field_errors["url"]
    assert result.errors[0].error_code is None
    assert result.error_codes == []


def test_a_hostile_collector_id_stays_one_argv_element(
    recording_runner: RecordingRunner, clock: Clock
) -> None:
    """Collector ids are interpolated values, so this is the injection boundary (G3)."""
    hostile = CollectorSpec(
        collector_id=HOSTILE_ID,
        name="hostile",
        anchor_urls=["https://example.test/list"],
        row_schema=SampleRow,
    )
    recording_runner.results.append(ok("[]"))

    client(recording_runner, clock).run(hostile, hostile.anchor_urls)

    argv = recording_runner.argvs[0]
    assert isinstance(argv, list)
    assert all(isinstance(element, str) for element in argv)
    assert argv.count(HOSTILE_ID) == 1
    assert not any("rm -rf" in element for element in argv if element != HOSTILE_ID)


def test_several_urls_become_one_comma_separated_argument(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """`--urls <list>` binds a single value, so a variadic would scrape only the first URL."""
    recording_runner.results.append(ok("[]"))

    client(recording_runner, clock).run(spec, BATCH_URLS)

    argv = recording_runner.argvs[0]
    start = argv.index("--urls")
    assert argv[start : start + 2] == ["--urls", "u1,u2,u3"]
    assert sum(1 for element in argv if any(url in element for url in BATCH_URLS)) == 1


def test_several_urls_never_reach_the_realtime_path(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """`--sync` and `--urls` are mutually exclusive, so a batch must not try realtime first."""
    recording_runner.results.append(ok("[]"))

    client(recording_runner, clock).run(spec, BATCH_URLS)

    assert len(recording_runner.argvs) == 1
    argv = recording_runner.argvs[0]
    assert "--sync" not in argv
    assert argv[argv.index("--timeout") + 1] == str(BATCH_TIMEOUT_S)


def test_a_url_containing_a_comma_is_refused(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """The comma is the separator, so a comma inside a URL would silently split the batch."""
    with pytest.raises(StudioError, match="u1,with-comma"):
        client(recording_runner, clock).run(spec, ["u1,with-comma", "u2"])

    assert recording_runner.argvs == []


def test_realtime_escalates_to_batch_with_a_timeout_above_the_cli_default(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """Batch polling runs to 3600 attempts, so the 600 s default would kill a healthy job."""
    recording_runner.results.extend([ok(ESCALATION_STDOUT), ok(TWO_ROWS_ONE_THROTTLED)])

    result = client(recording_runner, clock).run(spec, spec.anchor_urls)

    sync_argv, batch_argv = recording_runner.argvs
    assert "--sync" in sync_argv
    assert sync_argv[sync_argv.index("--timeout") + 1] == str(DEFAULT_TIMEOUT_S)
    assert "--sync" not in batch_argv
    assert batch_argv[batch_argv.index("--timeout") + 1] == str(BATCH_TIMEOUT_S)
    assert BATCH_TIMEOUT_S > CLI_DEFAULT_TIMEOUT_S
    assert recording_runner.timeouts[1] > recording_runner.timeouts[0]
    assert len(result.rows) == 2


def test_a_blocked_create_names_the_collector_it_left_behind(
    recording_runner: RecordingRunner, clock: Clock
) -> None:
    """Bright Data cannot delete the half-built collector, so a human must be told its id."""
    recording_runner.results.append(
        ProcessResult(returncode=1, stdout=BLOCKED_CREATE_STDOUT, stderr="")
    )

    with pytest.raises(CollectorCreateError) as raised:
        client(recording_runner, clock).create("https://blocked.example.test", "rows")

    assert ORPHANED_ID in str(raised.value)
    assert "Domain not allowed" in str(raised.value)


def test_create_returns_the_new_collector_id(
    recording_runner: RecordingRunner, clock: Clock
) -> None:
    """The happy path hands back the id every later step reuses."""
    recording_runner.results.append(
        ok(json.dumps({"collector_id": ORPHANED_ID, "name": "books", "status": "ready"}))
    )

    assert client(recording_runner, clock).create("https://example.test", "rows") == ORPHANED_ID


def test_non_json_stdout_raises_a_typed_error(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """A caller guards on `StudioResponseError`; a `JSONDecodeError` would leak the parser."""
    recording_runner.results.append(ok("<html>upstream proxy error</html>"))

    with pytest.raises(StudioResponseError) as raised:
        client(recording_runner, clock).run(spec, spec.anchor_urls)

    assert not isinstance(raised.value, json.JSONDecodeError)
    assert isinstance(raised.value.__cause__, json.JSONDecodeError)


def test_a_non_zero_exit_raises_a_studio_error(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """A failed command is reported with its reason, never swallowed."""
    recording_runner.results.append(
        ProcessResult(returncode=2, stdout="", stderr="collector not found")
    )

    with pytest.raises(StudioError, match="collector not found"):
        client(recording_runner, clock).run(spec, spec.anchor_urls)


def test_a_heal_envelope_becomes_a_pending_heal_event(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """The gate's `awaiting_approval` envelope carries the preview to verify against."""
    recording_runner.results.append(
        ok(
            json.dumps(
                {
                    "status": "awaiting_approval",
                    "preview_result": {"title": "A Light in the Attic"},
                }
            )
        )
    )

    event = client(recording_runner, clock).heal(spec, "restore the title field")

    assert event.status == HealStatus.AWAITING_APPROVAL
    assert event.preview_result == {"title": "A Light in the Attic"}
    assert event.promoted is False
    assert event.collector_id == STUB_COLLECTOR_ID
    assert event.prompt == "restore the title field"


def test_an_unrecognised_status_raises_a_typed_error(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """An envelope we cannot map is a response error, not a half-built event."""
    recording_runner.results.append(ok(json.dumps({"status": "thinking_about_it"})))

    with pytest.raises(StudioResponseError):
        client(recording_runner, clock).heal(spec, "restore the title field")


def test_fetch_html_asks_for_html_and_gets_the_page_source(
    recording_runner: RecordingRunner, clock: Clock
) -> None:
    """`bdata scrape` defaults to markdown, which would flatten the tree the skeleton hashes."""
    recording_runner.results.append(ok("<html><body><p>hi</p></body></html>"))

    html = client(recording_runner, clock).fetch_html("https://example.test/list")

    argv = recording_runner.argvs[0]
    assert html == "<html><body><p>hi</p></body></html>"
    assert argv[argv.index("--format") + 1] == "html"
    assert "--json" not in argv
    assert "--timeout" not in argv


def test_every_flag_emitted_exists_on_the_subcommand_that_receives_it(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """A stubbed runner accepts any flag; the real CLI does not. This is that check."""
    for argv in every_argv(recording_runner, clock, spec):
        command = subcommand_of(argv)
        unknown = flags_in(argv, command) - ALLOWED_FLAGS[command]
        assert not unknown, f"{' '.join(command)} does not accept {sorted(unknown)}"


def test_no_mutually_exclusive_flags_are_ever_emitted_together(
    recording_runner: RecordingRunner, clock: Clock, spec: CollectorSpec
) -> None:
    """One argv cannot ask for both the realtime and the batch endpoint."""
    for argv in every_argv(recording_runner, clock, spec):
        for left, right in EXCLUSIVE_FLAGS:
            assert not (left in argv and right in argv), f"{left} was sent with {right}"
