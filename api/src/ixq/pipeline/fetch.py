"""S2 — fetch one product's label and store its sections verbatim."""

import hashlib
import json
from typing import Any

from ixq.domain import Document, Product, Section, Source
from ixq.pipeline.ports import LabelSource, Repository

SECTIONS: dict[str, tuple[str, str]] = {
    "section_4_3_contraindications": ("4.3", "Contraindications"),
    "section_4_4_warnings": ("4.4", "Special warnings and precautions for use"),
    "section_4_6_pregnancy_lactation": ("4.6", "Fertility, pregnancy and lactation"),
}
"""Collector field -> (section code, heading).

The field names are the generator's, not ours: asked for `section_4_3`, it produced
`section_4_3_contraindications`. If a heal renames them this mapping goes stale, and the
schema signal is what catches that — a run returning none of these keys is a break, not
an empty label.
"""


def digest(row: dict[str, Any]) -> str:
    """Content address for a fetched row, stable across key ordering."""
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
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
    """
    url = source.product_at(product.external_id)
    rows = labels.rows(collector_id, [url])
    if not rows:
        return None

    row = rows[0]
    document = Document(
        sha256=digest(row),
        source_id=source.id,
        product_external_id=product.external_id,
        source_url=url,
        title=(row.get("product_name") or None),
    )
    repository.save_document(document)

    for field, (code, heading) in SECTIONS.items():
        text = row.get(field)
        if not text:
            continue
        repository.save_section(document.sha256, Section(code=code, heading=heading, text=text))

    return document
