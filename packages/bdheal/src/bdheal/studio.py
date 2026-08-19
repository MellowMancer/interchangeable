"""The `StudioClient` adapter — the only code in this package that speaks to `bdata`.

Everything the CLI does oddly is contained here: `npx` invocation, realtime-to-batch
escalation, polling past the 600 s default, per-row `error_code` payloads that are data
rather than exceptions, and a failed `create` that leaves an undeletable half-built
collector behind.

Every argv element is appended, never formatted into a string: collector ids and heal
prompts are caller-supplied values, and this file is where they meet a process (G3).
"""

import json
from collections.abc import Sequence
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError

from bdheal.errors import CollectorCreateError, StudioError, StudioResponseError
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

log = structlog.get_logger(__name__)


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

    def create(self, url: str, description: str) -> str:
        """Build a collector and return its id.

        Raises `CollectorCreateError` naming the orphaned collector when the
        AI-generation trigger fails — Bright Data exposes no programmatic delete.
        """
        argv = _argv(CREATE, url, description, *self._flags(self._timeout_s))
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
        """Heal in place. `--url` is a next-step hint only and is not sent on this call."""
        argv = _argv(HEAL, spec.collector_id, prompt, *self._flags(self._timeout_s))
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
        parsed = [_row(index, item, spec.row_schema) for index, item in enumerate(payload)]
        errors = [item for item in parsed if isinstance(item, RowError)]
        return RunResult(
            collector_id=spec.collector_id,
            fetched_at=self._clock.now(),
            rows=[item for item in parsed if not isinstance(item, RowError)],
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
                error=payload.get(ERROR_KEY),
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


def _excerpt(text: str) -> str:
    """A bounded, stripped slice of command output, safe to put in a message."""
    return text.strip()[:EXCERPT_CHARS] or "no output"


def _check(completed: ProcessResult, command: tuple[str, ...]) -> None:
    """Turn a non-zero exit into a typed error carrying the reason `bdata` gave."""
    if completed.returncode == 0:
        return
    reason = _excerpt(completed.stderr or completed.stdout)
    raise StudioError(f"{_label(command)} exited {completed.returncode}: {reason}")


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
    reason = payload.get(ERROR_KEY) or _excerpt(completed.stderr)
    collector_id = payload.get(COLLECTOR_ID_KEY)
    leftover = (
        f"collector {collector_id} was left half-built and Bright Data exposes no "
        "programmatic delete, so remove it in the web UI"
        if collector_id
        else "no collector id was returned, so nothing was left behind"
    )
    return f"{_label(CREATE)} failed for {url}: {reason}; {leftover}"


def _row(index: int, item: Any, row_schema: type[BaseModel]) -> dict[str, Any] | RowError:
    """One returned row as validated data, or as the reason it produced no record."""
    if not isinstance(item, dict):
        return RowError(index=index, message=f"expected an object, got {type(item).__name__}")
    if ERROR_KEY in item:
        return RowError(
            index=index,
            message=str(item[ERROR_KEY]),
            error_code=item.get(ERROR_CODE_KEY) or UNSPECIFIED_CODE,
        )
    try:
        return row_schema.model_validate(item).model_dump()
    except ValidationError as exc:
        return RowError(
            index=index,
            message="row does not match the collector's row schema",
            field_errors=_field_errors(exc),
        )


def _field_errors(exc: ValidationError) -> dict[str, str]:
    """Pydantic's per-field complaints, keyed by dotted field path."""
    return {".".join(str(part) for part in error["loc"]): error["msg"] for error in exc.errors()}


def _distinct_codes(errors: list[RowError]) -> list[str]:
    """The target-side error codes seen, first-seen order, each named once.

    `dict.fromkeys` is the stdlib's ordered de-duplication; spelling it as a loop invites
    the rule to be restated elsewhere, which is exactly what happened once already.
    """
    return list(dict.fromkeys(error.error_code for error in errors if error.error_code))


