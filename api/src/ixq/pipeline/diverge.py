"""S5 — the comparison: where manufacturers of one substance disagree."""

from dataclasses import dataclass

from ixq.domain import Document, Occurrence, Placement, Product
from ixq.pipeline.ports import Repository

PRECEDENCE = (
    Placement.CONTRAINDICATION,
    Placement.WARNING,
    Placement.INTERACTION,
    Placement.PREGNANCY,
)
"""Which placement to show when a concept appears in more than one section.

An absolute contraindication outranks a warning, which outranks the sections that qualify
rather than bar. Showing the weakest would understate what a label actually says.
"""


@dataclass(frozen=True, slots=True)
class ConceptRow:
    """One row of the matrix: where a concept sits in each product's label."""

    concept: str
    placements: dict[str, Placement]
    evidence: dict[str, Occurrence]
    """The occurrence that *set* each placement, keyed by product.

    Carried here rather than looked up again downstream. A second pass over storage can
    reach an occurrence belonging to a superseded revision of the label, and then a cell
    reads `ABSENT` from the current document while the quote under it comes from the old
    one — showing, as evidence for an absence, the very sentence the manufacturer removed.
    """

    @property
    def diverges(self) -> bool:
        """Whether the manufacturers disagree about this concept."""
        return len(set(self.placements.values())) > 1


@dataclass(frozen=True, slots=True)
class Comparison:
    """Every concept across every product of one substance.

    `scanned` is not decoration. `Placement.ABSENT` means *not found in these sections*,
    so a reader cannot judge an absence without knowing what was looked at — and a claim
    of omission is only ever defensible against that set.

    `documents` holds the **current** revision of each product's label, never the history.
    Everything here is derived from exactly those, so no consumer can pair a placement
    taken from one revision with a quote taken from another.
    """

    substance_id: str
    products: tuple[Product, ...]
    documents: tuple[Document, ...]
    scanned: dict[str, tuple[str, ...]]
    """Sections actually read, **per product**.

    A union across products would claim, of a product whose §4.5 came back empty, that
    4.5 was read for it — asserting a scope that was never scanned for that label. Since
    `ABSENT` is only defensible against the set actually scanned, that scope has to be
    the product's own.
    """

    rows: tuple[ConceptRow, ...]

    @property
    def divergent(self) -> tuple[ConceptRow, ...]:
        """The rows worth looking at first."""
        return tuple(row for row in self.rows if row.diverges)


def compare(substance_id: str, repository: Repository) -> Comparison:
    """Build the matrix for one substance from what has been stored.

    Computed on read rather than persisted: it is a pure function of the occurrences, so
    there is nothing to invalidate and it can never disagree with them.
    """
    products = repository.products_for_substance(substance_id)
    documents = repository.documents_for_substance(substance_id)

    # Oldest first per product, so the last write wins and the newest revision survives.
    # The query orders by `fetched_at` for exactly this: without a tiebreak, which
    # revision counted as current was whatever order SQLite happened to return.
    current = {d.product_external_id: d for d in documents}
    by_sha = {d.sha256: d for d in current.values()}

    scanned = {
        external_id: tuple(
            sorted(s.code for s in repository.sections_for_document(document.sha256))
        )
        for external_id, document in current.items()
    }

    placements: dict[str, dict[str, Placement]] = {}
    evidence: dict[str, dict[str, Occurrence]] = {}
    for occurrence in repository.occurrences_for_substance(substance_id):
        document = by_sha.get(occurrence.document_sha256)
        if document is None:
            continue  # an occurrence of a superseded revision
        found = Placement(occurrence.section_code)
        product_id = document.product_external_id
        seen = placements.setdefault(occurrence.concept, {})
        held = seen.get(product_id)
        if held is None or PRECEDENCE.index(found) < PRECEDENCE.index(held):
            seen[product_id] = found
            evidence.setdefault(occurrence.concept, {})[product_id] = occurrence

    compared = [p for p in products if p.external_id in current]
    rows = tuple(
        ConceptRow(
            concept=concept,
            placements={
                p.external_id: per_product.get(p.external_id, Placement.ABSENT)
                for p in compared
            },
            evidence=evidence.get(concept, {}),
        )
        for concept, per_product in sorted(placements.items())
    )
    return Comparison(
        substance_id=substance_id,
        products=tuple(compared),
        documents=tuple(current.values()),
        scanned=scanned,
        rows=rows,
    )
