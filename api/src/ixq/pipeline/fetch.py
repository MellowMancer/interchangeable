"""S2 — fetch one product's label and store its sections verbatim."""

import hashlib
import json
from typing import Any

from ixq.domain import Document, Placement, Product, Section, Source
from ixq.pipeline.ports import LabelSource, Repository

SECTIONS: dict[str, tuple[Placement, str]] = {
    "section_4_3_contraindications": (Placement.CONTRAINDICATION, "Contraindications"),
    "section_4_4_warnings": (Placement.WARNING, "Special warnings and precautions for use"),
    "section_4_6_pregnancy_lactation": (Placement.PREGNANCY, "Fertility, pregnancy and lactation"),
}
"""Collector field -> (section code, heading).

The field names are the generator's, not ours: asked for `section_4_3`, it produced
`section_4_3_contraindications`. If a heal renames them this mapping goes stale, and the
schema signal is what catches that — a run returning none of these keys is a break, not
an empty label.
"""


def digest(title: str | None, sections: list[Section]) -> str:
    """Content address for a label, over the content actually persisted.

    Keyed on section codes and text rather than the collector's field names: a heal that
    renames a field leaves the label byte-identical, and hashing the field names would
    change every address in the corpus, fork it against the existing occurrences, and
    defeat the idempotence this address exists to provide.
    """
    content = {"title": title} | {s.code: s.text for s in sections}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def fetch(
    product: Product,
    source: Source,
    collector_id: str,
    labels: LabelSource,
    repository: Repository,
) -> Document | None:
    """Fetch one product's label, storing the document and its sections.

    Returns None when the collector yields nothing for this product — an empty result is
    reported to the caller rather than persisted as a document with no sections.

    The caller owns the transaction boundary, as in `collect`: a document, its sections
    and its occurrences are one unit of work, and half of them is worse than none.
    """
    url = source.product_at(product.external_id)
    rows = labels.rows(collector_id, [url])
    if not rows:
        return None

    row = rows[0]
    if not any(field in row for field in SECTIONS):
        raise ValueError(
            "collector returned no section fields — expected one of "
            f"{sorted(SECTIONS)}, got {sorted(row)}. A renamed field is a break, "
            "not a label without contraindications."
        )
    title = row.get("product_name") or None
    sections = [
        Section(code=placement.value, heading=heading, text=row[field])
        for field, (placement, heading) in SECTIONS.items()
        if row.get(field)
    ]
    document = Document(
        sha256=digest(title, sections),
        source_id=source.id,
        product_external_id=product.external_id,
        source_url=url,
        title=title,
    )

    repository.save_document(document)
    for section in sections:
        repository.save_section(document.sha256, section)

    return document
