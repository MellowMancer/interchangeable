"""S2 — fetch one product's label and store its sections verbatim."""

import hashlib
import json
from typing import Any

from ixq.domain import Document, Placement, Product, Section, Source, appearance, revision_date
from ixq.pipeline.ports import LabelSource, Repository

APPEARANCE = ("section_3_pharmaceutical_form", appearance.SECTION_CODE, "Pharmaceutical form")
"""Collector field, section code and heading for §3 — stored, and deliberately not in
`SECTIONS`.

`SECTIONS` is keyed by `Placement`, and §3 is not one: it describes the object rather
than naming a section a safety concept can be filed in. Kept apart so it cannot be
iterated into the comparison by a later change, and left out of the missing-content guard
below so a row carrying an appearance but no §4.x still reads as the break it is.
"""

SECTIONS: dict[str, tuple[Placement, str]] = {
    "section_4_3_contraindications": (Placement.CONTRAINDICATION, "Contraindications"),
    "section_4_4_warnings": (Placement.WARNING, "Special warnings and precautions for use"),
    "section_4_5_interactions": (Placement.INTERACTION, "Interaction with other medicinal products"),
    "section_4_6_pregnancy_lactation": (Placement.PREGNANCY, "Fertility, pregnancy and lactation"),
    "section_6_1_excipients": (Placement.EXCIPIENT, "List of excipients"),
}
"""Collector field -> (section code, heading).

The field names are the generator's, not ours: asked for `section_4_3`, it produced
`section_4_3_contraindications`. If a heal renames them this mapping goes stale, and the
schema signal is what catches that — a run returning none of these keys is a break, not
an empty label.
"""

CLINICAL = tuple(
    field for field, (placement, _) in SECTIONS.items() if placement is not Placement.EXCIPIENT
)
"""The sections whose absence, as a set, means the collector moved rather than the label.

§6.1 is excluded deliberately. A row carrying excipients and no clinical section is not a
comparable label under any reading, so letting §6.1 alone satisfy the guard would turn a
break into a document with nothing in it.
"""


def digest(
    source_id: str,
    product_external_id: str,
    title: str | None,
    revised: str | None,
    sections: list[Section],
) -> str:
    """Content address for a label, over the content actually persisted.

    Keyed on section codes and text rather than the collector's field names: a heal that
    renames a field leaves the label byte-identical, and hashing the field names would
    change every address in the corpus, fork it against the existing occurrences, and
    defeat the idempotence this address exists to provide.

    **The source's record is deliberately not part of the address.** Legal status, the
    discontinued badge and the company id describe the *listing*, not the label, and a
    listing has only one current state — there is nothing to compare across revisions. In
    the address they would fork every stored document the first time any of them was
    observed, manufacturing a revision from a badge. They are updated in place instead;
    `save_document` owns that.

    **Identity is part of the address.** Without it two manufacturers whose labels happen
    to be byte-identical — routine for generics built by one contract manufacturer —
    collide on `documents.sha256`, and `ON CONFLICT DO NOTHING` silently discards the
    second. The dropped product then disappears from the comparison entirely, which reads
    as a manufacturer having no opinion rather than as data loss.
    """
    content = {
        "source": source_id,
        "product": product_external_id,
        "title": title,
        "revised": revised,
    } | {s.code: s.text for s in sections}
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
    if not any(row.get(field) for field in CLINICAL):
        raise ValueError(
            "collector returned no clinical section content — expected one of "
            f"{sorted(CLINICAL)}, got {sorted(row)}. A renamed field is a break, "
            "not a label without contraindications."
        )
    title = row.get("product_name") or None
    revised = revision_date(row.get("last_updated"))
    sections = [
        Section(code=placement.value, heading=heading, text=row[field])
        for field, (placement, heading) in SECTIONS.items()
        if row.get(field)
    ]
    field, code, heading = APPEARANCE
    if row.get(field):
        sections.append(Section(code=code, heading=heading, text=row[field]))
    document = Document(
        sha256=digest(source.id, product.external_id, title, revised, sections),
        source_id=source.id,
        product_external_id=product.external_id,
        source_url=url,
        title=title,
        active_substance=row.get("active_substance") or None,
        last_updated=revised,
        listing_updated=revision_date(row.get("emc_last_updated")),
        holder_id=_as_int(row.get("company_id")),
        ingredient_id=_as_int(row.get("ingredient_id")),
        atc_code=row.get("atc_code") or None,
        legal_status=row.get("legal_status") or None,
        ma_number=row.get("section_8_ma_number") or None,
        discontinued=_as_bool(row.get("discontinued")),
    )

    repository.save_document(document)
    for section in sections:
        repository.save_section(document.sha256, section)

    return document


def _as_int(value: Any) -> int | None:
    """The collector's id fields, which arrive as JSON numbers but need not.

    A generator that starts quoting them — or a heal that does — would otherwise store a
    string in an integer column, and SQLite would accept it without complaint. Returns
    None for anything that is not a whole number, because a half-parsed id is worse than
    a missing one.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    """The discontinued flag, which is a badge's presence rather than a stated value.

    `None` is preserved as "the fetch did not report it", distinct from `False` meaning
    "the page carried no badge". The string forms are accepted because the collector's
    generator is free to emit `"false"`, and treating that as truthy would mark every
    live product discontinued.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "discontinued", "1"}
    return None
