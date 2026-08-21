"""Sections that are stored but are not places a concept can be filed.

`Placement` doubles as the vocabulary of comparable section codes: `compare()` calls
`Placement(occurrence.section_code)` and `PRECEDENCE.index(...)` on the result, so a code
that is not a member raises. That conflation is deliberate — it is what stops a section
entering the comparison by accident — but it leaves no way to say "store this, and read it
some other way".

This module is that way. Nothing here is a `Placement`, so `classify_document`'s
`COMPARABLE` guard and `compare()`'s `scanned` derivation both exclude these sections
already, with no change to either.
"""

from dataclasses import dataclass

from ixq.domain import appearance


@dataclass(frozen=True, slots=True)
class SectionSpec:
    """One section the collector returns that the comparison must not read."""

    field: str
    code: str
    heading: str

    def __post_init__(self) -> None:
        if not self.field or not self.code:
            raise ValueError("a section spec needs a collector field and a section code")


SHELF_LIFE_CODE = "6.3"
STORAGE_CODE = "6.4"

INDICATIONS_CODE = "4.1"
"""§4.1, the section that says what the substance is authorised to treat.

Named because two callers address it: the fetch mapping below, and the reader that shows
it under a substance. A literal in both would be a code the corpus depends on with nobody
owning it.
"""

STORED_ONLY: tuple[SectionSpec, ...] = (
    SectionSpec(
        field="section_3_pharmaceutical_form",
        code=appearance.SECTION_CODE,
        heading="Pharmaceutical form",
    ),
    SectionSpec(
        field="section_4_1_indications",
        code=INDICATIONS_CODE,
        heading="Therapeutic indications",
    ),
    SectionSpec(
        field="section_6_3_shelf_life",
        code=SHELF_LIFE_CODE,
        heading="Shelf life",
    ),
    SectionSpec(
        field="section_6_4_storage",
        code=STORAGE_CODE,
        heading="Special precautions for storage",
    ),
)
"""Every section stored without being comparable, in the order the publisher numbers them.

Deliberately not merged into `fetch.SECTIONS`: that mapping is keyed by `Placement` and
`CLINICAL` is derived from it, so a shelf life added there would join the guard that
decides whether the collector moved — and a row carrying nothing but a shelf life would
then read as a healthy label.
"""

# Not yet recorded here, because nothing reads it yet: these sections differ in whether
# they are closed lists. §4.1 states every authorised indication, so an absence from it
# means something, where an absence from §4.3 does not — a warning missing there may sit
# in §4.4. Whatever compares them will need that distinction; it belongs on this spec when
# it has a consumer, not before.


VALUE_SECTIONS: tuple[SectionSpec, ...] = tuple(
    spec for spec in STORED_ONLY if spec.code in (SHELF_LIFE_CODE, STORAGE_CODE)
)
"""The stored sections that state one value rather than file a concept.

A label states its shelf life once and its storage conditions once, so these are read by
grouping the labels that word them the same way — never by asking which section a concept
landed in. Derived from `STORED_ONLY` rather than listed again, so a section cannot be
declared in one place and forgotten in the other.
"""

VALUE_CODES: tuple[str, ...] = tuple(spec.code for spec in VALUE_SECTIONS)
"""The codes of `VALUE_SECTIONS`, for the one query that reads them together."""
