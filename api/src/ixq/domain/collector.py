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

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("collector id is required")
        if not self.source_id:
            raise ValueError("collector source_id is required")
