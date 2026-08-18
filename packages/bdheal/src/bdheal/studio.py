"""The `StudioClient` adapter — the only code in this package that speaks to `bdata`.

Everything the CLI does oddly is contained here: `npx` invocation, realtime-to-batch
escalation, polling past the 600 s default, per-row `error_code` payloads that are data
rather than exceptions, and a failed `create` that leaves an undeletable half-built
collector behind.

Every argv element is appended, never formatted into a string: collector ids and heal
prompts are caller-supplied values, and this file is where they meet a process (G3).
"""

from collections.abc import Sequence

from bdheal.models import CollectorSpec, HealEvent, RunResult
from bdheal.ports import Clock, CommandRunner

BDATA_ARGV: tuple[str, ...] = ("npx", "-p", "@brightdata/cli", "bdata")
DEFAULT_TIMEOUT_S = 900
BATCH_TIMEOUT_S = 3600


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
        raise NotImplementedError

    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        """Run the collector, escalating to batch mode and polling when the sync path says so."""
        raise NotImplementedError

    def heal(self, spec: CollectorSpec, prompt: str, *, auto_approve: bool = False) -> HealEvent:
        """Heal in place. `--url` is a next-step hint only and is not sent on this call."""
        raise NotImplementedError

    def approve(self, spec: CollectorSpec, url: str, *, reject: bool = False) -> HealEvent:
        """Promote or reject the pending heal. The anchor URL is required here."""
        raise NotImplementedError

    def fetch_html(self, url: str) -> str:
        """Fetch raw HTML through `bdata scrape`, for the skeleton hash."""
        raise NotImplementedError
