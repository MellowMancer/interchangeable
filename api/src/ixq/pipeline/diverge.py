"""S5 — the comparison: where manufacturers of one substance disagree."""

from dataclasses import dataclass

from ixq.domain import Document, Placement, Product
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

    @property
    def diverges(self) -> bool:
        """Whether the manufacturers disagree about this concept."""
        return len(set(self.placements.values())) > 1


@dataclass(frozen=True, slots=True)
class Comparison:
    """Every concept across every product of one substance.

    `scanned` is not decoration. `Placement.ABSENT` means *not found in these sections*,
    so a reader cannot judge an absence without knowing what was looked at — and a claim
    of omission is only ever defensible against this set.
    """

    substance_id: str
    products: tuple[Product, ...]
    documents: tuple[Document, ...]
    scanned: tuple[str, ...]
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
    by_product = {d.product_external_id: d for d in documents}

    scanned: set[str] = set()
    placements: dict[str, dict[str, Placement]] = {}
    for external_id, document in by_product.items():
        scanned.update(s.code for s in repository.sections_for_document(document.sha256))

    for occurrence in repository.occurrences_for_substance(substance_id):
        document = _document_of(occurrence.document_sha256, by_product)
        if document is None:
            continue
        found = Placement(occurrence.section_code)
        seen = placements.setdefault(occurrence.concept, {})
        current = seen.get(document.product_external_id)
        if current is None or PRECEDENCE.index(found) < PRECEDENCE.index(current):
            seen[document.product_external_id] = found

    compared = [p for p in products if p.external_id in by_product]
    rows = tuple(
        ConceptRow(
            concept=concept,
            placements={
                p.external_id: per_product.get(p.external_id, Placement.ABSENT)
                for p in compared
            },
        )
        for concept, per_product in sorted(placements.items())
    )
    return Comparison(
        substance_id=substance_id,
        products=tuple(compared),
        documents=tuple(documents),
        scanned=tuple(sorted(scanned)),
        rows=rows,
    )


def _document_of(sha256: str, by_product: dict[str, Document]) -> Document | None:
    return next((d for d in by_product.values() if d.sha256 == sha256), None)
