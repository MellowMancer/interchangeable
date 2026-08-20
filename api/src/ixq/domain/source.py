"""A site whose documents are collected."""

import re
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

    def external_id_from(self, url: str) -> str | None:
        """The publisher's product id, read back out of one of its product URLs.

        Derived from the same `product_url` template used to build them, so a publisher
        whose ids are not numeric — or whose path is not `/product/` — needs no code
        change, only its own template.
        """
        if not self.product_url:
            raise ValueError(f"source {self.id!r} has no product_url template")
        pattern = "".join(
            r"(?P<external_id>[^/?#]+)" if part == "{external_id}" else re.escape(part)
            for part in re.split(r"(\{external_id\})", self.product_url)
        )
        found = re.search(pattern, url or "")
        return found.group("external_id") if found else None

    def product_at(self, external_id: str) -> str:
        """The canonical URL of one product page."""
        if not self.product_url:
            raise ValueError(f"source {self.id!r} has no product_url template")
        return self.product_url.format(external_id=external_id)
