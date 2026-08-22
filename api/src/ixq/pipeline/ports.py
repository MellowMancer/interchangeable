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


@dataclass(frozen=True)
class ClauseCounts:
    """How many stored clauses the lexicon matched, and how many it did not.

    The recall gap as two numbers rather than a ratio. A percentage would read as a claim
    about how well the lexicon performs in general, which one substance cannot support.
    """

    classified: int
    unclassified: int


@dataclass(frozen=True)
class ConceptDivergence:
    """One concept the manufacturers of a substance do not place alike.

    Names and section codes only — no quotes and no section text, so the roster can
    preview what a comparison contains without reading the corpus to do it.

    `placements` carries `ABSENT` as a member when at least one product lacks the concept
    entirely, because that is what that product's cell reads. It is a placement in the
    comparison's vocabulary, never a section.
    """

    concept: str
    placements: tuple[str, ...]


class Repository(Protocol):
    """The pipeline's persistence boundary.

    One port rather than one-per-aggregate: there is a single backing store and a
    single reason to change. Nothing above this line may know that SQL exists.
    """

    def section_codes_for_substance(self, substance_id: str) -> dict[str, tuple[str, ...]]:
        """Per document sha, the section codes it holds — the codes alone.

        `compare` needs this to say what was scanned for each product. Asking for whole
        `Section` objects instead meant one query per document, each dragging the full
        label text back, to build a four-element set of codes.
        """
        ...

    def appearances_for_substance(self, substance_id: str) -> dict[str, str]:
        """Per document sha, its §3 text — the manufacturer's description of the product.

        Narrow on purpose rather than "any section's text for a substance". §3 runs to a
        line or two, while §4.4 runs to kilobytes, and a general method here would invite
        exactly the read-the-whole-corpus-per-navigation regression `counts_by_substance`
        exists to undo.

        Returns text, not a parsed `Appearance`: parsing is the domain's, and a port that
        returned entities would put a parser behind the storage boundary.

        Documents with no §3 stored are absent rather than empty-valued — a label nobody
        described is not a label describing nothing.
        """
        ...

    def clause_counts(self, substance_id: str) -> ClauseCounts:
        """Matched and unmatched clause counts for one substance, counted in storage."""
        ...

    def divergences_by_substance(self) -> dict[str, tuple[ConceptDivergence, ...]]:
        """Per substance, which concepts diverge and across which placements.

        Counted in storage alongside the roster's numbers, for the same reason: the index
        screen previews every substance at once, and building each comparison to name a
        few concepts would read the whole corpus on every navigation.
        """
        ...

    def indications_for_substance(self, substance_id: str) -> dict[str, str]:
        """Per document sha, its §4.1 text — what the label says the substance is for.

        Narrow for the same reason as `appearances_for_substance`: §4.1 is a line or two,
        and a general "any section's text" method here would invite reading §4.4 the same
        way, which is kilobytes per label on every navigation.
        """
        ...

    def value_sections_for_substance(
        self, substance_id: str
    ) -> dict[str, dict[str, str]]:
        """Per document sha, its §6.3 and §6.4 text, keyed by section code.

        Both codes in one method and one query because both are a single short line and a
        screen that shows one shows the other. Narrow for the same reason as the two
        methods above: a general "any section" reader here would invite pulling §4.4,
        which is kilobytes per label on every navigation.

        A document with neither section stored is absent rather than empty-valued, and a
        document with only one carries only that key — a label nobody collected a shelf
        life for has not stated it has none.
        """
        ...

    def substance_of(self, product_external_id: str) -> str | None:
        """Which substance a product belongs to, or None when no such product is stored.

        A product's own page is reached by its id alone, and everything else about it —
        its placements, its siblings, what it is compared against — is scoped to the
        substance. This is the one lookup that turns the id in a URL into that scope.
        """
        ...

    def labels_by_substance(self) -> dict[str, tuple[str, ...]]:
        """Per substance, the names a reader might search for: products and their holders.

        Counted alongside the roster's numbers rather than by building comparisons, for
        the same reason `counts_by_substance` exists: the index screen covers every
        substance, and reading each one's documents to list a few names would read the
        whole corpus on every navigation.

        Only current revisions, so a product renamed between revisions is searchable by
        the name its label carries now and not by one nobody would recognise.
        """
        ...

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

    def delete_occurrences(self, document_sha256: str) -> None:
        """Drop every occurrence of one document, so they can be derived again.

        Occurrences are addressed by their character span, so a change to how clauses are
        cut gives the same finding a different span. Re-deriving without this leaves both
        the old row and the new one, and a cell then shows two quotes for one claim.
        """
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

    def section_text(self, document_sha256: str, code: str) -> str | None:
        """One section's body, verbatim, or None when the document has no such section.

        Its own method rather than a filter over `sections_for_document`: showing a quote
        in its surroundings needs the one body it was sliced from, and that call returns
        every section of the label — whole SmPC sections, kilobytes each — to read one.

        `None` is "never stored for this document", which is not an empty section. A
        caller reporting an absence must say what was scanned, and a section that is not
        there was not scanned.
        """
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
