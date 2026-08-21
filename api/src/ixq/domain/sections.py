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
from enum import StrEnum

from ixq.domain import appearance


class SectionKind(StrEnum):
    """How a stored section may be read.

    `DESCRIPTION` sections describe the product or the substance and are shown, never
    diffed. `VALUE` sections state one short thing — a shelf life, a storage condition —
    that is worth setting side by side across manufacturers.

    The distinction is not decorative: it decides whether a difference between two labels
    is reportable at all. Diffing a description manufactures a finding out of wording.
    """

    DESCRIPTION = "description"
    VALUE = "value"


@dataclass(frozen=True, slots=True)
class SectionSpec:
    """One section the collector returns that the comparison must not read.

    `exhaustive` records whether the section is a closed list. §4.1 states every authorised
    indication, so something absent from it is genuinely not stated; §4.3 is not exhaustive,
    because a warning missing there may sit in §4.4. That is the difference between an
    absence that means something and one that does not, and it is why `ABSENT` may never be
    reported for these sections the way it is for a placement.
    """

    field: str
    code: str
    heading: str
    kind: SectionKind
    exhaustive: bool

    def __post_init__(self) -> None:
        if not self.field or not self.code:
            raise ValueError("a section spec needs a collector field and a section code")


STORED_ONLY: tuple[SectionSpec, ...] = (
    SectionSpec(
        field="section_3_pharmaceutical_form",
        code=appearance.SECTION_CODE,
        heading="Pharmaceutical form",
        kind=SectionKind.DESCRIPTION,
        exhaustive=True,
    ),
    SectionSpec(
        field="section_4_1_indications",
        code="4.1",
        heading="Therapeutic indications",
        kind=SectionKind.DESCRIPTION,
        exhaustive=True,
    ),
    SectionSpec(
        field="section_6_3_shelf_life",
        code="6.3",
        heading="Shelf life",
        kind=SectionKind.VALUE,
        exhaustive=True,
    ),
    SectionSpec(
        field="section_6_4_storage",
        code="6.4",
        heading="Special precautions for storage",
        kind=SectionKind.VALUE,
        exhaustive=True,
    ),
)
"""Every section stored without being comparable, in the order the publisher numbers them.

Deliberately not merged into `fetch.SECTIONS`: that mapping is keyed by `Placement` and
`CLINICAL` is derived from it, so a shelf life added there would join the guard that
decides whether the collector moved — and a row carrying nothing but a shelf life would
then read as a healthy label.
"""

CODES: frozenset[str] = frozenset(spec.code for spec in STORED_ONLY)
"""Derived, so it cannot drift from the specs above."""
