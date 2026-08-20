"""A Scraper Studio collector, addressed by the id Bright Data assigns it."""

from dataclasses import dataclass
from enum import StrEnum


class CollectorKind(StrEnum):
    """What a collector is for. One per role, not one per target page."""

    PRODUCT = "product"
    SEARCH = "search"
    SITEMAP = "sitemap"
    DISCOVERY = "discovery"


@dataclass(frozen=True, slots=True)
class Collector:
    """One collector's identity.

    The id survives healing — that is the whole point of the platform's repair model — so
    it is a stable reference the pipeline can hold onto across layout changes.
    """

    id: str
    source_id: str
    kind: CollectorKind
    anchor_url: str | None = None
    """One stable page drift is judged against.

    Must not vary per call. The baseline is keyed on the collector id alone and the
    structural signal hashes this page, so passing whichever product is being fetched
    would rewrite one baseline with a different page every time and report the collector
    broken on essentially every run — while spending a billable fetch per product.
    """

    old_layout_url: str | None = None
    """A publicly hosted snapshot of a previous layout, for the non-regression check.

    Optional because production has no such snapshot: Scraper Studio runs in Bright
    Data's cloud and cannot reach a local file. Without it a heal is promoted *unverified*,
    which is recorded rather than hidden — a fix that repairs today's layout by breaking
    yesterday's has not healed anything.
    """

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("collector id is required")
        if not self.source_id:
            raise ValueError("collector source_id is required")
