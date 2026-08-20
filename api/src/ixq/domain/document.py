"""The document a product's label is published as."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Document:
    """A published label, content-addressed by the sha256 of its bytes.

    It names its product by the source's own identifier rather than a database id, so a
    document can be stored before or after the product it belongs to.
    """

    sha256: str
    source_id: str
    product_external_id: str
    source_url: str
    title: str | None = None

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex digest")
        if not self.source_id:
            raise ValueError("document source_id is required")
        if not self.product_external_id:
            raise ValueError("document product_external_id is required")
