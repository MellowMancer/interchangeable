"""Domain invariants. A claim that cannot be traced back to its source is not a claim."""

import pytest

from ixq.domain import (
    Document,
    Occurrence,
    Placement,
    Product,
    Section,
    Substance,
    found_in,
    revision_date,
)
from conftest import DOC_SHA, SECTION


def _occurrence(**overrides) -> Occurrence:
    defaults = dict(
        document_sha256=DOC_SHA,
        section_code="4.3",
        concept="renal",
        quote="Severe renal impairment",
        char_start=42,
        char_end=65,
    )
    return Occurrence(**{**defaults, **overrides})


def test_occurrence_requires_a_verbatim_quote() -> None:
    with pytest.raises(ValueError, match="provenance"):
        _occurrence(quote="")


def test_occurrence_rejects_inverted_char_span() -> None:
    with pytest.raises(ValueError, match="char_end"):
        _occurrence(char_start=30, char_end=10)


def test_occurrence_requires_a_section_and_a_concept() -> None:
    with pytest.raises(ValueError, match="section_code"):
        _occurrence(section_code="")
    with pytest.raises(ValueError, match="concept"):
        _occurrence(concept="")


def test_found_in_slices_the_quote_from_the_section() -> None:
    """The provenance guarantee: the quote cannot disagree with its own offsets."""
    occurrence = found_in(SECTION, DOC_SHA, "renal", 42, 65)

    assert occurrence.quote == SECTION.text[42:65]
    assert occurrence.quote == "Severe renal impairment"
    assert occurrence.section_code == "4.3"


def test_found_in_refuses_offsets_past_the_section() -> None:
    with pytest.raises(ValueError, match="past the end"):
        found_in(SECTION, DOC_SHA, "renal", 0, len(SECTION.text) + 1)


def test_document_rejects_a_short_hash() -> None:
    with pytest.raises(ValueError, match="64-character"):
        Document(
            sha256="abc",
            source_id="emc",
            product_external_id="987",
            source_url="https://example.test/product/987",
        )


def test_section_requires_a_code() -> None:
    with pytest.raises(ValueError, match="section code"):
        Section(code="", heading="Contraindications", text="...")


def test_product_requires_its_identifying_fields() -> None:
    with pytest.raises(ValueError, match="external_id"):
        Product(source_id="emc", external_id="", substance_id="ramipril", name="X")
    with pytest.raises(ValueError, match="substance_id"):
        Product(source_id="emc", external_id="987", substance_id="", name="X")


def test_substance_requires_an_id_and_a_name() -> None:
    with pytest.raises(ValueError, match="substance id"):
        Substance(id="", name="Ramipril")


def test_placement_absent_is_distinct_from_a_section() -> None:
    """Absent means 'not in any scanned section' — never the same as appearing in one."""
    assert Placement.ABSENT != Placement.WARNING
    assert Placement.CONTRAINDICATION == "4.3"
    assert Placement.ABSENT == "absent"


# Every string here came back from the live collector. The last two are what the
# extractor produced before it was healed — kept because a heal fixes the layouts it was
# shown, and the next publisher layout is one nobody has seen.
REVISION_DATES = [
    ("14/07/2026", "14/07/2026"),
    ("31-07-2024", "31-07-2024"),
    ("November 2025", "November 2025"),
    ("04 June 2021", "04 June 2021"),
    ("31-07-2024 11. DOSIMETRY 12. INSTRUCTIONS FOR PREPARATION", "31-07-2024"),
    ("04 June 2021 LEGAL STATUS POM", "04 June 2021"),
]


@pytest.mark.parametrize("raw,expected", REVISION_DATES)
def test_revision_date_keeps_the_date_and_drops_the_page_furniture(
    raw: str, expected: str
) -> None:
    assert revision_date(raw) == expected


@pytest.mark.parametrize("raw", ["LEGAL STATUS POM", "", None, "see section 4.4"])
def test_a_string_with_no_leading_date_yields_nothing(raw) -> None:
    """Storing the raw string would put page furniture in front of a reader as a date."""
    assert revision_date(raw) is None
