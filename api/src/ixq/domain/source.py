"""A site whose documents are collected."""

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True, slots=True)
class Source:
    """A publisher of documents, keyed by slug.

    `variant` names the collector's layout family (HTML structure), not anything
    about the subject matter.

    The two URL templates keep a publisher's URL shape in configuration rather than in a
    use case, so pointing at a second publisher stays a config change.
    """

    id: str
    name: str
    base_url: str
    variant: str | None = None
    search_url: str | None = None
    product_url: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("source id is required")

    def search_for(self, query: str) -> str:
        """The search URL for one query. Carries the publisher's own paging limit.

        The query is percent-encoded: a multi-word substance would otherwise put a raw
        space in the URL, and an `&` in a name would truncate it at that point.
        """
        if not self.search_url:
            raise ValueError(f"source {self.id!r} has no search_url template")
        return self.search_url.format(query=quote_plus(query))

    def product_at(self, external_id: str) -> str:
        """The canonical URL of one product page."""
        if not self.product_url:
            raise ValueError(f"source {self.id!r} has no product_url template")
        return self.product_url.format(external_id=external_id)
