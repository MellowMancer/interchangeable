"""Interfaces the use cases depend on. Implementations live in the adapters layer."""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class SubstanceCounts:
    """How much of one substance is collected, and how much of it disagrees.

    A separate question from `compare`, asked by the roster screen. Answering it by
    building the full comparison meant reading every section's text and every quote for
    every substance to produce three integers, then discarding all of it.
    """

    products: int
    concepts: int
    divergent: int


class Repository(Protocol):
    """The pipeline's persistence boundary.

    One port rather than one-per-aggregate: there is a single backing store and a
    single reason to change. Nothing above this line may know that SQL exists.
    """

    def counts_by_substance(self) -> dict[str, SubstanceCounts]:
        """Per substance, the three numbers the roster shows. Counted in storage.

        Substances with nothing collected are absent rather than zero-valued: the caller
        holds the roster and knows which ids it asked about.
        """
        ...

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

    def documents_for_substance(self, substance_id: str) -> list[Document]:
        """Every stored label across every product of a substance."""
        ...

    def sections_for_document(self, document_sha256: str) -> list[Section]:
        """Every section stored for a document, in code order."""
        ...

    def occurrences_for_substance(self, substance_id: str) -> list[Occurrence]:
        """Every occurrence across every product of a substance. This is the matrix."""
        ...


@dataclass(frozen=True, slots=True)
class CollectorCheck:
    """What one health check concluded, in terms the caller can report.

    `promoted_unverified` is deliberately separate from `healed`: a heal that was accepted
    without the non-regression pass may have fixed today's layout by breaking yesterday's,
    and reporting it as a clean repair would hide that.
    """

    collector_id: str
    broken: bool
    healed: bool = False
    promoted_unverified: bool = False
    reason: str | None = None


class CollectorMaintainer(Protocol):
    """Keeps a collector fit to run. Separate from `LabelSource` on purpose.

    Fetching rows and repairing a collector are different jobs with different costs: the
    check spends one billable fetch against a stable anchor, per collector per run, while
    rows are fetched once per product. Folding them together would multiply the first by
    the second.
    """

    def ensure_healthy(self, collector_id: str) -> CollectorCheck:
        """Judge the collector against its anchor and repair it in place if it has moved."""
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
