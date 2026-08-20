"""The document a product's label is published as."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Document:
    """A published label, content-addressed by the sha256 of its bytes.

    It names its product by the source's own identifier rather than a database id, so a
    document can be stored before or after the product it belongs to.

    `last_updated` is a string, not a date: publishers state month precision
    ("November 2025"), and parsing it into a date would invent a day nobody published.
    It matters because a difference between two labels may be staleness rather than
    disagreement, and a comparison that cannot show revision dates cannot tell them apart.
    """

    sha256: str
    source_id: str
    product_external_id: str
    source_url: str
    title: str | None = None
    active_substance: str | None = None
    last_updated: str | None = None

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex digest")
        if not self.source_id:
            raise ValueError("document source_id is required")
        if not self.product_external_id:
            raise ValueError("document product_external_id is required")
