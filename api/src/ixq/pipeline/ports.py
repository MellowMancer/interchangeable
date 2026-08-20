"""Interfaces the use cases depend on. Implementations live in the adapters layer."""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Any, Protocol

from ixq.domain import (
    Collector,
    CollectorKind,
    Document,
    Occurrence,
    Product,
    Section,
    Source,
    Substance,
)


class Repository(Protocol):
    """The pipeline's persistence boundary.

    One port rather than one-per-aggregate: there is a single backing store and a
    single reason to change. Nothing above this line may know that SQL exists.
    """

    def save_source(self, source: Source) -> None:
        """Insert or update a source."""
        ...

    def save_collector(self, collector: Collector) -> None:
        """Insert or update a collector."""
        ...

    def collector_for(self, source_id: str, kind: CollectorKind) -> Collector | None:
        """The collector playing one role for one source, or None if not configured."""
        ...

    def save_substance(self, substance: Substance) -> None:
        """Insert or update a substance."""
        ...

    def transaction(self) -> AbstractContextManager[None]:
        """One unit of work. Saves are not durable until this exits."""
        ...

    def save_product(self, product: Product) -> None:
        """Insert or update a product."""
        ...

    def save_document(self, document: Document) -> None:
        """Insert a document, keyed by content hash. Idempotent on re-fetch."""
        ...

    def save_section(self, document_sha256: str, section: Section) -> None:
        """Insert or replace one numbered section of a document."""
        ...

    def save_occurrence(self, occurrence: Occurrence) -> None:
        """Insert an occurrence."""
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


class LabelSource(Protocol):
    """Where label rows come from.

    Deliberately narrower than the collector library underneath it: the use cases need
    rows, not a heal loop, so they take plain dictionaries and stay testable without any
    of the collection machinery present.
    """

    def rows(self, collector_id: str, urls: Sequence[str]) -> list[dict[str, Any]]:
        """Run one collector against one or more URLs and return its rows."""
        ...
