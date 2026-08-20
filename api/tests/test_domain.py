"""Domain invariants. A claim that cannot be traced back to its source is not a claim."""

import pytest

from ixq.domain import Document, Occurrence, Placement, Product, Section, Substance, found_in

SECTION = Section(
    code="4.3",
    heading="Contraindications",
    text="Hypersensitivity to the active substance. Severe renal impairment.",
)


def _occurrence(**overrides) -> Occurrence:
    defaults = dict(
        document_sha256="a" * 64,
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
    occurrence = found_in(SECTION, "a" * 64, "renal", 42, 65)

    assert occurrence.quote == SECTION.text[42:65]
    assert occurrence.quote == "Severe renal impairment"
    assert occurrence.section_code == "4.3"


def test_found_in_refuses_offsets_past_the_section() -> None:
    with pytest.raises(ValueError, match="past the end"):
        found_in(SECTION, "a" * 64, "renal", 0, len(SECTION.text) + 1)


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
