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


STORED_ONLY: tuple[SectionSpec, ...] = (
    SectionSpec(
        field="section_3_pharmaceutical_form",
        code=appearance.SECTION_CODE,
        heading="Pharmaceutical form",
    ),
    SectionSpec(
        field="section_4_1_indications",
        code="4.1",
        heading="Therapeutic indications",
    ),
    SectionSpec(
        field="section_6_3_shelf_life",
        code="6.3",
        heading="Shelf life",
    ),
    SectionSpec(
        field="section_6_4_storage",
        code="6.4",
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
