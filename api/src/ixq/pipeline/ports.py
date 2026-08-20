"""Interfaces the use cases depend on. Implementations live in the adapters layer."""

from typing import Protocol

from ixq.domain import Document, Occurrence, Product, Section, Source, Substance


class Repository(Protocol):
    """The pipeline's persistence boundary.

    One port rather than one-per-aggregate: there is a single backing store and a
    single reason to change. Nothing above this line may know that SQL exists.
    """

    def save_source(self, source: Source) -> None:
        """Insert or update a source."""
        ...

    def save_substance(self, substance: Substance) -> None:
        """Insert or update a substance."""
        ...

    def save_product(self, product: Product) -> Product:
        """Insert or update a product, returning it with its assigned id."""
        ...

    def save_document(self, document: Document) -> None:
        """Insert a document, keyed by content hash. Idempotent on re-fetch."""
        ...

    def save_section(self, document_sha256: str, section: Section) -> None:
        """Insert or replace one numbered section of a document."""
        ...

    def save_occurrence(self, occurrence: Occurrence) -> Occurrence:
        """Insert an occurrence, returning it with its assigned id."""
        ...

    def products_for_substance(self, substance_id: str) -> list[Product]:
        """Every product of a substance — the columns of the comparison."""
        ...

    def sections_for_document(self, document_sha256: str) -> list[Section]:
        """Every section stored for a document, in code order."""
        ...

    def occurrences_for_substance(self, substance_id: str) -> list[Occurrence]:
        """Every occurrence across every product of a substance. This is the matrix."""
        ...
