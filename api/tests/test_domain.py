"""Domain invariants. A claim that cannot be traced back to its source is not a claim."""

import pytest

from ixq.domain import (
    COMPARABLE,
    Document,
    Occurrence,
    Placement,
    Product,
    Section,
    Shape,
    Substance,
    appearance,
    described_in,
    found_in,
    in_context,
    revision_date,
    variant,
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


PADDING = "Other clinical text that is not the quote. " * 20
"""Long enough on both sides that a 10-character window has to clip at each end."""


def _padded_section(quote: str) -> tuple[str, Occurrence]:
    """A section with `quote` buried in the middle of it, and the occurrence for that quote."""
    text = PADDING + quote + PADDING
    section = Section(code="4.3", heading="Contraindications", text=text)
    return text, found_in(section, DOC_SHA, "washout", len(PADDING), len(PADDING) + len(quote))


def test_a_context_window_holds_the_quote_at_the_offsets_it_reports() -> None:
    """The provenance guarantee restated one level down: no re-searching the window."""
    quote = "Washout of the previous therapy is required."
    text, occurrence = _padded_section(quote)

    found = in_context(text, occurrence, radius=100)

    assert found.text[found.quote_start : found.quote_end] == quote
    assert found.text[found.quote_start : found.quote_end] == occurrence.quote


def test_a_context_window_says_which_ends_it_cut() -> None:
    """A window that stops mid-sentence must not read as a section that ends there."""
    text, occurrence = _padded_section("Washout is required.")

    found = in_context(text, occurrence, radius=100)

    assert (found.truncated_start, found.truncated_end) == (True, True)
    assert len(found.text) < len(text)


def test_a_window_wider_than_its_section_is_the_section_and_says_it_cut_nothing() -> None:
    """Clipping to the stored bounds, so no window claims text the section does not have."""
    occurrence = found_in(SECTION, DOC_SHA, "renal", 42, 65)

    found = in_context(SECTION.text, occurrence, radius=len(SECTION.text))

    assert found.text == SECTION.text
    assert (found.quote_start, found.quote_end) == (42, 65)
    assert (found.truncated_start, found.truncated_end) == (False, False)


def test_a_quote_at_the_start_of_a_section_is_not_reported_as_cut() -> None:
    """`max(0, ...)` is not cosmetic: a negative window start would shift every offset."""
    occurrence = found_in(SECTION, DOC_SHA, "hypersensitivity", 0, 16)

    found = in_context(SECTION.text, occurrence, radius=100)

    assert (found.quote_start, found.quote_end) == (0, 16)
    assert found.truncated_start is False


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


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ramipril 2.5mg Capsule", "2.5mg Capsule"),
        ("Ramipril 1.25mg Hard Capsules", "1.25mg Capsules"),
        ("Ramipril 10 mg/5 ml Oral solution", "10mg/5ml Oral Solution"),
        ("Tritace 5mg Tablets", "5mg Tablets"),
        ("Ramipril Aurobindo 10 mg Tablets", "10mg Tablets"),
        ("Something With No Strength", None),
    ],
)
def test_a_variant_distinguishes_two_products_of_one_manufacturer(
    name: str, expected: str | None
) -> None:
    """Derived from the stored name — the collector is never asked for it.

    Scraping it would spend quota on data already held and add a field that drifts when a
    page moves. `None` on an unparseable name lets the caller fall back to the full name
    rather than render a blank column heading.
    """
    assert variant(name) == expected


AURO = (
    "Orange/White size '4' hard gelatin capsules imprinted with 'D' on orange cap "
    "and '41' on white body with black edible ink"
)
WOCK = "Red opaque body and red opaque cap. The body has 'RP 5' printed in black."
ZENT = (
    "Tablets mg 5mg Pale red oblong tablet with dimensions of 8 x 4 mm with score-line. "
    "Upper stamp: 5 & logo. Lower stamp: HMP & 5"
)
"""The three §3 descriptions this corpus actually carries, verbatim.

Captured strings rather than invented ones, for the same reason the §4.3 golden test uses
one: the prose is company-authored and dirty — note the leading `Tablets mg 5mg` — and a
parser tested against tidy examples is tested against a corpus that does not exist.
"""


def test_a_two_tone_capsule_is_read_cap_first_from_the_labels_own_binding() -> None:
    """`Orange/White` and `orange cap … white body` agree here; only the binding is read.

    Reading the leading pair by position would draw the next label inside out: 14717 opens
    with its *body* colour, so position means opposite things on the two labels.
    """
    found = described_in(AURO)

    assert found.shape is Shape.CAPSULE
    assert found.colours == ("orange", "white")
    assert found.imprints == ("D", "41")
    assert found.unparsed == () and found.drawable


def test_a_capsule_shell_size_is_not_an_imprint() -> None:
    """`size '4'` is quoted exactly like an imprint and is printed on nothing."""
    assert "4" not in described_in(AURO).imprints


def test_the_colour_of_the_printing_is_not_the_colour_of_the_product() -> None:
    """Both labels name their ink. Read as product colour they draw a black capsule."""
    assert "black" not in described_in(AURO).colours
    assert "black" not in described_in(WOCK).colours


def test_a_capsule_named_only_by_its_two_halves_is_still_a_capsule() -> None:
    """14717 never says "capsule". `cap` and `body` are the halves of one, and a tablet
    has neither — so this is reading the label's vocabulary, not inferring a form."""
    found = described_in(WOCK)

    assert found.shape is Shape.CAPSULE
    assert found.colours == ("red",), "one colour stated twice is one colour"
    assert found.imprints == ("RP 5",)
    assert found.drawable


def test_dirty_company_prose_still_yields_what_it_states() -> None:
    """8066 opens `Tablets mg 5mg`, which is representative of the corpus, not an outlier."""
    found = described_in(ZENT)

    assert found.shape is Shape.OBLONG
    assert found.colours == ("pale red",)
    assert (found.length_mm, found.width_mm) == (8.0, 4.0)
    assert found.drawable


def test_a_label_stating_no_dimensions_reports_none_rather_than_a_borrowed_size() -> None:
    """Two of the three state no size. Unknown is unknown; a drawn size would be ours."""
    assert described_in(AURO).length_mm is None
    assert described_in(WOCK).width_mm is None


def test_an_unstated_outline_is_published_not_guessed() -> None:
    """"Tablet" names a form but no outline. A circle would be this parser's invention."""
    found = described_in("White film-coated tablet.")

    assert found.shape is None
    assert found.unparsed == ("shape",)
    assert not found.drawable
    assert found.source_text == "White film-coated tablet.", "the prose is still published"


def test_a_description_yielding_nothing_names_everything_it_could_not_read() -> None:
    found = described_in("A clear, colourless solution for injection.")

    assert found.unparsed == ("shape", "colour")
    assert not found.drawable


def test_a_capsule_shaped_tablet_is_an_oblong_not_a_capsule() -> None:
    """The specific phrase contains the general word, so word order in `SHAPE_WORDS` is
    load-bearing rather than incidental."""
    assert described_in("Yellow capsule-shaped tablet.").shape is Shape.OBLONG


def test_the_appearance_section_is_not_a_placement() -> None:
    """The whole comparison rests on this. §3 describes the object, and a safety concept
    cannot be filed in a description of a capsule's colour."""
    assert appearance.SECTION_CODE not in COMPARABLE
    assert appearance.SECTION_CODE not in {p.value for p in Placement}
