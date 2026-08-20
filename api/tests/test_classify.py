"""S3 and S4. The invariant under test is that a quote can always be re-checked."""

from pathlib import Path

from ixq.adapters.config import load_concepts
from ixq.domain import UNCLASSIFIED, Concept, Section
from ixq.pipeline.classify import classify
from ixq.pipeline.sectionize import clauses, normalise

# Verbatim from Glucophage 500 mg, EMC product 987 — the real thing, bullets and all.
METFORMIN_43 = Section(
    code="4.3",
    heading="Contraindications",
    text="""4.3 Contraindications
• Hypersensitivity to metformin or to any of the excipients listed in section 6.1.
• Any type of acute metabolic acidosis (such as lactic acidosis, diabetic ketoacidosis).
• Diabetic pre-coma.
• Severe renal failure (GFR < 30 mL/min).
• Acute conditions with the potential to alter renal function such as: dehydration, severe infection, shock.
• Hepatic insufficiency, acute alcohol intoxication, alcoholism.""",
)
SHA = "a" * 64


def _concepts() -> list[Concept]:
    return load_concepts(Path(__file__).resolve().parent.parent / "config" / "concepts.yaml")


def test_clauses_are_exact_slices_of_the_section() -> None:
    """The whole provenance chain rests on this: offsets address the untouched text."""
    for clause in clauses(METFORMIN_43):
        assert METFORMIN_43.text[clause.start : clause.end] == clause.text


def test_section_header_is_not_a_clause() -> None:
    assert all(not c.text.startswith("4.3") for c in clauses(METFORMIN_43))


def test_bullets_are_stripped_without_shifting_the_span() -> None:
    first = clauses(METFORMIN_43)[0]
    assert first.text.startswith("Hypersensitivity")
    assert METFORMIN_43.text[first.start] == "H"


def test_metformin_section_splits_to_its_six_contraindications() -> None:
    assert len(clauses(METFORMIN_43)) == 6


def test_lead_ins_are_dropped_in_every_phrasing_seen() -> None:
    """Measured as 12% of apparent misses. A colon introduces clauses; it asserts nothing."""
    section = Section(
        code="4.3",
        heading="Contraindications",
        text="\n".join(
            [
                "Tamoxifen should not be used in:",
                "Nolvadex should not be used in the following:",
                "General contraindications (all indications)",
                "Atorvastatin is contraindicated in patients:",
                "Severe renal failure (GFR < 30 mL/min).",
            ]
        ),
    )

    assert [c.text for c in clauses(section)] == ["Severe renal failure (GFR < 30 mL/min)."]


def test_short_clauses_are_kept_because_they_are_real_contraindications() -> None:
    """`Porphyria.` is ten characters and absolute. A length filter would silently lose it."""
    section = Section(code="4.3", heading="C", text="Shock.\nPorphyria.\nPregnancy.")

    assert [c.text for c in clauses(section)] == ["Shock.", "Porphyria.", "Pregnancy."]


def test_a_leading_o_bullet_does_not_eat_the_first_letter() -> None:
    """EMC nests sub-bullets as a literal `o`; stripping it as a character breaks words."""
    section = Section(
        code="4.3",
        heading="C",
        text="o Concurrent anastrozole therapy.\nobstruction of the outflow tract.",
    )

    assert [c.text for c in clauses(section)] == [
        "Concurrent anastrozole therapy.",
        "obstruction of the outflow tract.",
    ]


def test_a_clause_opening_with_a_dose_is_not_mistaken_for_a_heading() -> None:
    """`2.5 mg/5 ml ...` starts like a section number and is a contraindication."""
    section = Section(code="4.3", heading="C", text="2.5 mg/5 ml oral solution in children.")

    assert [c.text for c in clauses(section)] == ["2.5 mg/5 ml oral solution in children."]


def test_cross_references_are_removed_for_matching_but_not_from_the_quote() -> None:
    raw = "Severe renal failure (see section 4.4) and dehydration."

    assert "see section" not in normalise(raw)
    assert normalise(raw) == "Severe renal failure and dehydration."

    section = Section(code="4.3", heading="C", text=raw)
    occurrence = classify(section, SHA, _concepts())[0]
    assert "see section" in occurrence.quote  # the quote stays verbatim


def test_every_occurrence_quote_matches_its_stored_offsets() -> None:
    for occurrence in classify(METFORMIN_43, SHA, _concepts()):
        assert (
            METFORMIN_43.text[occurrence.char_start : occurrence.char_end] == occurrence.quote
        )


def test_a_clause_carrying_two_concepts_yields_two_occurrences() -> None:
    section = Section(
        code="4.3", heading="C", text="Hepatic insufficiency, acute alcohol intoxication."
    )

    assert {o.concept for o in classify(section, SHA, _concepts())} == {"hepatic", "alcohol"}


def test_an_unmatched_clause_is_recorded_not_dropped() -> None:
    """A dropped clause is a blind spot: no concept means no row, so no divergence is seen."""
    section = Section(code="4.3", heading="C", text="Wearing an unusually large hat indoors.")

    occurrences = classify(section, SHA, [])

    assert [o.concept for o in occurrences] == [UNCLASSIFIED]
    assert occurrences[0].quote == "Wearing an unusually large hat indoors."


def test_classifying_the_real_section_finds_its_known_concepts() -> None:
    names = {o.concept for o in classify(METFORMIN_43, SHA, _concepts())}

    assert {"hypersensitivity", "metabolic_acidosis", "glycaemic_emergency", "renal"} <= names
    assert UNCLASSIFIED not in names
