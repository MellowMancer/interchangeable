"""The `StudioClient` adapter — the only code in this package that speaks to `bdata`.

Everything the CLI does oddly is contained here: `npx` invocation, realtime-to-batch
escalation, polling past the 600 s default, per-row `error_code` payloads that are data
rather than exceptions, and a failed `create` that leaves an undeletable half-built
collector behind.

Every argv element is appended, never formatted into a string: collector ids and heal
prompts are caller-supplied values, and this file is where they meet a process (G3).
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from bdheal.errors import CollectorCreateError, GateBusyError, StudioError, StudioResponseError
from bdheal.models import CollectorSpec, HealEvent, RowError, RunResult
from bdheal.ports import Clock, CommandRunner, ProcessResult
from bdheal.vocabulary import HealStatus

BDATA_ARGV: tuple[str, ...] = ("npx", "-p", "@brightdata/cli", "bdata")
DEFAULT_TIMEOUT_S = 900
BATCH_TIMEOUT_S = 3600

# The CLI owns the deadline; the process gets slightly longer so that a `bdata` timeout
# reports itself as JSON instead of being killed mid-sentence.
RUNNER_GRACE_S = 30

# Subcommand words, which double as the label in error messages so the two cannot drift.
CREATE = ("scraper", "create")
RUN = ("scraper", "run")
HEAL = ("scraper", "heal")
APPROVE = ("scraper", "approve")
SCRAPE = ("scrape",)

JSON_FLAG = "--json"
TIMEOUT_FLAG = "--timeout"

# `bdata scraper run --urls <list>` takes one comma-separated value, not a variadic
# (verified against v0.3.5 `--help`). A variadic would scrape only the first URL.
URL_SEPARATOR = ","

# `scrape` is a separate top-level Web Unlocker command, not a fifth `scraper` verb: it
# rejects `--timeout`, and it defaults to markdown, which would flatten the tag tree the
# skeleton hash reads — leaving the structural signal silently unable to fire.
HTML_FORMAT: tuple[str, ...] = ("--format", "html")

# Verbatim from a v0.3.5 run whose realtime page limit was exceeded.
NAME_FLAG = "--name"
CREATE_FAILED_STATUS = "ai_trigger_failed"
ERROR_KEY = "error"
ERROR_CODE_KEY = "error_code"
# A target error the CLI reported without naming a code. It is still target-side — the row
# came back as an error payload, not as data the extractor mis-read — and detect's whole
# discriminator is "an error carrying a code is target-side, one carrying none is an
# extraction fault". Leaving it None would make a failed page load fire the schema signal
# and buy a paid heal cycle for something healing cannot fix.
UNSPECIFIED_CODE = "unspecified"
COLLECTOR_ID_KEY = "collector_id"
EXCERPT_CHARS = 200
# How much beyond the excerpt is scanned for credentials. Redaction must see past the cut —
# a key straddling char 200 would otherwise leave its visible prefix behind, and a prefix of
# a credential is still a credential. But scanning the *whole* payload is unbounded work on
# a failure path: a batch `scraper run` returns megabytes, and one label pattern alone cost
# 2.5 s per megabyte, so a 10 MB failure took ~26 s to report. Every pattern anchors on a
# label and runs greedily rightward, so a credential beginning before the cut still matches
# inside this window.
STRADDLE_MARGIN = 4096

# How Bright Data says the collector is already occupied. Transcribed from a v0.3.5
# refusal on 2026-08-20, where a gate an earlier run had left parked blocked every heal
# on that collector for five hours. Either marker is enough: the sentence is the CLI's
# wording and the status is the HTTP conflict behind it, so a reworded message still
# recovers, and a false positive costs one rejection of a gate that was not there.
GATE_BUSY_MARKERS: tuple[str, ...] = (
    "another refactor job is still in progress",
    "status: 409",
)

# This package never reads a credential, but one can arrive *from* the subprocess: `npx`
# echoes the command line it wrapped when that process fails, and `bdata` relays upstream
# auth errors verbatim. Both land on stderr, become an exception message, and are written
# to a heal event's `error` column — a credential at rest, authored by nobody (G6).
# Redacted to a marker rather than dropped: the operator still has to know what failed.
REDACTED = "[redacted]"

# Shorter runs than this are collector ids and job ids, which are not secret and are the
# most useful thing in the message. Real keys and JWTs are far longer.
MIN_OPAQUE_CHARS = 24

# Applied in order, catch-all last, so a labelled credential keeps its label.
_CREDENTIAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # The whole header value, to end of line — not `\S+`, which matches only the scheme
    # word and leaves the credential after it. That bug shipped once: it rewrote
    # `Authorization: Bearer <token>` to `Authorization: [redacted] <token>` and, by
    # consuming the word `Bearer` first, stopped the pattern below from ever seeing it.
    # Tokens of 24+ characters were rescued by the catch-all, so the tests passed on a
    # long JWT while a short session token leaked verbatim into the persisted row.
    (re.compile(r"(?i)\b((?:proxy-)?authorization)\s*:[^\r\n]*"), rf"\1: {REDACTED}"),
    # Known and accepted: this is line-greedy, so diagnostic text sharing a line with the
    # header is redacted along with the credential. Every observed payload puts the status
    # on its own line, and over-redacting a message beats under-redacting a secret.
    (re.compile(r"(?i)\bbearer\s+\S+"), f"Bearer {REDACTED}"),
    (
        re.compile(r"(?i)([\w-]*(?:key|token|secret|password)[\w-]*)\s*[=:]\s*\S+"),
        rf"\1={REDACTED}",
    ),
    (re.compile(r"(?i)(--[\w-]*(?:key|token|secret|password))\s+\S+"), rf"\1 {REDACTED}"),
    (
        re.compile(rf"\b(?=[\w.-]*\d)(?=[\w.-]*[A-Za-z])[\w.-]{{{MIN_OPAQUE_CHARS},}}"),
        REDACTED,
    ),
)


class BdataStudioClient:
    """Bright Data Scraper Studio, driven through the `bdata` CLI.

    The runner is injected so tests never spawn `npx`; the clock is injected so
    `RunResult.fetched_at` is deterministic.
    """

    def __init__(
        self,
        runner: CommandRunner,
        clock: Clock,
        *,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        batch_timeout_s: int = BATCH_TIMEOUT_S,
    ) -> None:
        self._runner = runner
        self._clock = clock
        self._timeout_s = timeout_s
        self._batch_timeout_s = batch_timeout_s

    def create(self, url: str, description: str, name: str | None = None) -> str:
        """Build a collector and return its id.

        Raises `CollectorCreateError` naming the orphaned collector when the
        AI-generation trigger fails — Bright Data exposes no programmatic delete.

        `name` is passed straight through to `--name`. Since a failed or superseded
        collector can only be removed by hand, the difference between a caller-chosen name
        and the default `cli-scraper-<timestamp>` is whether that is possible at all.
        """
        named = [NAME_FLAG, name] if name else []
        argv = _argv(CREATE, url, description, *named, *self._flags(self._timeout_s))
        completed = self._call(argv, self._timeout_s)
        try:
            payload = _object(completed, CREATE)
        except StudioResponseError as exc:
            # A hard failure that printed no JSON still leaves a collector behind, and the
            # caller is catching `CollectorCreateError` precisely to be told about it. The
            # unparseable output becomes the reason rather than a different exception type.
            if completed.returncode != 0:
                raise CollectorCreateError(_create_failure(url, {}, completed)) from exc
            raise
        if completed.returncode != 0 or _create_failed(payload):
            raise CollectorCreateError(_create_failure(url, payload, completed))
        collector_id = payload.get(COLLECTOR_ID_KEY)
        if not collector_id:
            raise StudioResponseError(f"{_label(CREATE)} reported success without a collector id")
        return str(collector_id)

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Run the collector and return its rows. The CLI escalates to batch on its own."""
        completed = self._attempt(spec.collector_id, urls)
        _check(completed, RUN)
        return self._collate(spec, _array(completed, RUN))

    def heal(self, spec: CollectorSpec, prompt: str, *, auto_approve: bool = False) -> HealEvent:
        """Heal in place. `--url` is a next-step hint only and is not sent on this call.

        `--auto-save` is not optional. Without it the CLI previews the fix, accepts an
        approval and reports `done` while leaving the collector on its old template — a
        heal that silently does nothing. Verified against the live CLI on 2026-08-20:
        only with the flag does the run include a `save_new_template` step.
        """
        argv = _argv(HEAL, spec.collector_id, prompt, "--auto-save", *self._flags(self._timeout_s))
        if auto_approve:
            argv.append("--auto-approve")
        completed = self._call(argv, self._timeout_s)
        _check(completed, HEAL)
        return self._event(spec.collector_id, _object(completed, HEAL), HEAL, prompt=prompt)

    def approve(self, spec: CollectorSpec, url: str, *, reject: bool = False) -> HealEvent:
        """Promote or reject the pending heal. The anchor URL is required here."""
        argv = _argv(APPROVE, spec.collector_id, "--url", url, *self._flags(self._timeout_s))
        if reject:
            argv.append("--reject")
        completed = self._call(argv, self._timeout_s)
        _check(completed, APPROVE)
        return self._event(spec.collector_id, _object(completed, APPROVE), APPROVE)

    def fetch_html(self, url: str) -> str:
        """Fetch raw HTML through `bdata scrape`, for the skeleton hash."""
        completed = self._call(_argv(SCRAPE, url, *HTML_FORMAT), self._timeout_s)
        _check(completed, SCRAPE)
        return completed.stdout

    def _attempt(self, collector_id: str, urls: Sequence[str]) -> ProcessResult:
        """One call. The CLI escalates realtime to batch by itself and polls it to done.

        Verified live against v0.3.5: a run that exceeds the realtime page limit prints
        `switching to batch mode`, submits a batch job and polls it (`attempt 1/3600`) in
        the *same* invocation, returning the rows. Watching for that marker and issuing a
        second run therefore abandons a job already running and already paid for, and
        submits a duplicate — two minutes-long, rate-limited jobs for one answer.

        `--sync` does not prevent it either; the escalation above happened with the flag
        set. So there is one shape, for one URL or many, at the batch deadline, because
        any call may escalate.
        """
        return self._call(self._run_argv(collector_id, urls), self._batch_timeout_s)

    def _call(self, argv: list[str], timeout_s: int) -> ProcessResult:
        """Run one command, giving the process a little longer than the CLI's own deadline."""
        return self._runner(argv, timeout_s + RUNNER_GRACE_S)

    def _flags(self, timeout_s: int) -> list[str]:
        """The flags every JSON-returning subcommand carries."""
        return [JSON_FLAG, TIMEOUT_FLAG, str(timeout_s)]

    def _run_argv(self, collector_id: str, urls: Sequence[str]) -> list[str]:
        """argv for one run. The CLI picks realtime or batch itself; we set the deadline."""
        return _argv(RUN, collector_id, *_url_args(urls), *self._flags(self._batch_timeout_s))

    def _collate(self, spec: CollectorSpec, payload: list[Any]) -> RunResult:
        """Split the rows Bright Data returned into validated data and per-row failures."""
        rows = _rows_in(payload, spec.rows_key)
        parsed = [_row(index, item, spec.row_schema) for index, item in enumerate(rows)]
        errors = [item.error for item in parsed if item.error is not None]
        return RunResult(
            collector_id=spec.collector_id,
            fetched_at=self._clock.now(),
            rows=[item.row for item in parsed if item.row is not None],
            errors=errors,
            error_codes=_distinct_codes(errors),
        )

    def _event(
        self,
        collector_id: str,
        payload: dict[str, Any],
        command: tuple[str, ...],
        *,
        prompt: str | None = None,
    ) -> HealEvent:
        """Turn a heal or approve envelope into a `HealEvent`, or say why it could not be."""
        try:
            status = HealStatus(payload.get("status"))
            return HealEvent(
                collector_id=collector_id,
                status=status,
                created_at=self._clock.now(),
                prompt=prompt,
                preview_result=payload.get("preview_result"),
                error=_reported(payload),
            )
        except ValueError as exc:
            raise StudioResponseError(
                f"{_label(command)} returned an unusable envelope: {exc}"
            ) from exc


def _argv(command: tuple[str, ...], *values: str) -> list[str]:
    """argv for one `bdata` subcommand. Each value stays its own element (G3)."""
    return [*BDATA_ARGV, *command, *values]


def _url_args(urls: Sequence[str]) -> list[str]:
    """The URL arguments for a run: one is positional, several go through `--urls`.

    `--urls <list>` binds a single comma-separated value, so the batch is one argv
    element however many URLs it holds.
    """
    targets = list(urls)
    if len(targets) <= 1:
        return targets
    return ["--urls", URL_SEPARATOR.join(_separable(targets))]


def _separable(urls: list[str]) -> list[str]:
    """The URLs, refused if one carries the separator that would split the batch silently."""
    for url in urls:
        if URL_SEPARATOR in url:
            raise StudioError(
                f"{_label(RUN)} cannot batch {url}: a URL holding {URL_SEPARATOR!r} would "
                "split the --urls list. Percent-encode it, or run this URL on its own"
            )
    return urls


def _label(command: tuple[str, ...]) -> str:
    """How a subcommand is named in an error message. Never the full argv (G6)."""
    return " ".join(command)


def _redact(text: str) -> str:
    """Command output with every credential-shaped substring replaced by `REDACTED`."""
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _excerpt(text: str) -> str:
    """A bounded, scrubbed slice of command output, safe to put in a message.

    Scrubbed *before* truncating: a key straddling the cut would otherwise leave its
    first characters in the message, and a prefix of a credential is still a credential.
    """
    return _redact(text.strip()[: EXCERPT_CHARS + STRADDLE_MARGIN])[:EXCERPT_CHARS] or "no output"


def _reported(payload: dict[str, Any]) -> str | None:
    """The envelope's own error message, scrubbed — it is persisted onto the heal event."""
    reported = payload.get(ERROR_KEY)
    return _redact(str(reported)) if reported else None


def _check(completed: ProcessResult, command: tuple[str, ...]) -> None:
    """Turn a non-zero exit into a typed error carrying the reason `bdata` gave."""
    if completed.returncode == 0:
        return
    output = completed.stderr or completed.stdout
    message = f"{_label(command)} exited {completed.returncode}: {_excerpt(output)}"
    if _gate_is_busy(output):
        raise GateBusyError(message)
    raise StudioError(message)


def _gate_is_busy(output: str) -> bool:
    """Whether this refusal is Bright Data saying the collector already has a job open.

    Read from the raw output rather than the excerpt: the marker may sit past the 200
    characters a message carries, and a recoverable refusal must not become an
    unrecoverable one because the reason was truncated.
    """
    lowered = output.lower()
    return any(marker in lowered for marker in GATE_BUSY_MARKERS)


def _payload(completed: ProcessResult, command: tuple[str, ...]) -> Any:
    """Parse `--json` output, so a caller never has to catch a `JSONDecodeError`."""
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        # stderr is the fallback so a hard failure's reason is not lost to the parser.
        reason = _excerpt(completed.stdout or completed.stderr)
        raise StudioResponseError(f"{_label(command)} did not return JSON: {reason}") from exc


def _object(completed: ProcessResult, command: tuple[str, ...]) -> dict[str, Any]:
    """The parsed payload, asserted to be the documented JSON object."""
    payload = _payload(completed, command)
    if not isinstance(payload, dict):
        raise StudioResponseError(
            f"{_label(command)} returned {type(payload).__name__}, expected a JSON object"
        )
    return payload


def _array(completed: ProcessResult, command: tuple[str, ...]) -> list[Any]:
    """The parsed payload, asserted to be the documented JSON array of rows."""
    payload = _payload(completed, command)
    if not isinstance(payload, list):
        raise StudioResponseError(
            f"{_label(command)} returned {type(payload).__name__}, expected a JSON array"
        )
    return payload


def _create_failed(payload: dict[str, Any]) -> bool:
    """Whether a create envelope reports the AI-generation trigger having failed."""
    return bool(payload.get(ERROR_KEY)) or payload.get("status") == CREATE_FAILED_STATUS


def _create_failure(url: str, payload: dict[str, Any], completed: ProcessResult) -> str:
    """Why the create failed and, crucially, which half-built collector it left behind."""
    reason = _reported(payload) or _excerpt(completed.stderr)
    collector_id = payload.get(COLLECTOR_ID_KEY)
    leftover = (
        f"collector {collector_id} was left half-built and Bright Data exposes no "
        "programmatic delete, so remove it in the web UI"
        if collector_id
        else "no collector id was returned, so nothing was left behind"
    )
    return f"{_label(CREATE)} failed for {url}: {reason}; {leftover}"


def _rows_in(payload: list[Any], rows_key: str | None) -> list[Any]:
    """The rows inside a payload, descending through envelopes when the spec names one.

    A spec naming no key is taken at face value: the payload already is the rows.
    """
    if rows_key is None:
        return payload
    return [row for item in payload for row in _envelope_rows(item, rows_key)]


def _envelope_rows(item: Any, rows_key: str) -> list[Any]:
    """One envelope's rows, or the item untouched when it is not one.

    The fallback matters: a target-side refusal arrives as a bare `{"error": ...}` object
    with no envelope around it, and it has to reach `_row` to become the `RowError` whose
    code the detectors read. Unwrapping it away would turn a refusal into silence.
    """
    if isinstance(item, dict) and isinstance(item.get(rows_key), list):
        return item[rows_key]
    return [item]


@dataclass(frozen=True, slots=True)
class _Parsed:
    """One returned item as data, as the reason it failed, or as both.

    A schema failure is both: the record is kept with the offending fields nulled, and the
    complaint is kept so the schema signal still fires.
    """

    row: dict[str, Any] | None
    error: RowError | None


def _row(index: int, item: Any, row_schema: type[BaseModel]) -> _Parsed:
    """One returned row as validated data, as the reason it produced no record, or as both."""
    if not isinstance(item, dict):
        return _Parsed(
            row=None,
            error=RowError(index=index, message=f"expected an object, got {type(item).__name__}"),
        )
    if ERROR_KEY in item:
        return _Parsed(
            row=None,
            error=RowError(
                index=index,
                message=str(item[ERROR_KEY]),
                error_code=item.get(ERROR_CODE_KEY) or UNSPECIFIED_CODE,
            ),
        )
    try:
        return _Parsed(row=row_schema.model_validate(item).model_dump(), error=None)
    except ValidationError as exc:
        failed = _field_errors(exc)
        return _Parsed(
            row=_partial(item, row_schema, failed),
            error=RowError(
                index=index,
                message="row does not match the collector's row schema",
                field_errors=failed,
            ),
        )


def _partial(
    item: dict[str, Any], row_schema: type[BaseModel], failed: dict[str, str]
) -> dict[str, Any]:
    """The row with the fields that failed validation nulled and the rest as returned.

    A record is not worthless because one of its fields is. Discarding the whole row made a
    single bad field read as a vanished record, which cost three things at once: the
    null-rate detector never saw the hole, the volume detectors read a schema break as a
    collapse in row count, and field accuracy fell to zero where four fields in five were
    perfect. Measured against a live collector, exactly that happened on `date_format` and
    `url_pattern`.

    Surviving fields are carried through as returned rather than re-coerced: the model
    rejected this record, so its coercions cannot be trusted to have run.
    """
    return {name: None if name in failed else item.get(name) for name in row_schema.model_fields}


def _field_errors(exc: ValidationError) -> dict[str, str]:
    """Pydantic's per-field complaints, keyed by dotted field path."""
    return {".".join(str(part) for part in error["loc"]): error["msg"] for error in exc.errors()}


def _distinct_codes(errors: list[RowError]) -> list[str]:
    """The target-side error codes seen, first-seen order, each named once.

    `dict.fromkeys` is the stdlib's ordered de-duplication; spelling it as a loop invites
    the rule to be restated elsewhere, which is exactly what happened once already.
    """
    return list(dict.fromkeys(error.error_code for error in errors if error.error_code))


