"""S3 and S4. The invariant under test is that a quote can always be re-checked."""

import re
from pathlib import Path

import pytest

from ixq.adapters.config import load_concepts
from ixq.domain import UNCLASSIFIED, Concept, Section, clauses, prepared
from ixq.domain.section import BULLET, HEADER, LEAD_IN, SPLITTING_GLYPHS
from ixq.pipeline.classify import classify

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


@pytest.fixture
def concepts(shipped_config_dir: Path) -> list[Concept]:
    """The shipped lexicon, so these run against the real thing."""
    return load_concepts(shipped_config_dir / "concepts.yaml")


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


def test_a_restatement_of_the_heading_is_dropped() -> None:
    """It asserts nothing the heading did not, so it can only add noise."""
    section = Section(
        code="4.3",
        heading="Contraindications",
        text="\n".join(
            [
                "General contraindications (all indications)",
                "Contraindications",
                "Severe renal failure (GFR < 30 mL/min).",
            ]
        ),
    )

    assert [c.text for c in clauses(section)] == ["Severe renal failure (GFR < 30 mL/min)."]


def test_a_colon_line_carrying_content_is_kept() -> None:
    """The regression that manufactured two false divergences across the ramipril corpus.

    Treating any trailing colon as a lead-in discarded this line whole — 239 characters
    naming the interacting substances — so the manufacturers whose §4.5 is written this
    way reported ABSENT on concepts their labels do state. An unclassified clause is a
    visible gap; a dropped one is an invisible false absence.
    """
    interaction = (
        "Antihypertensive agents (e.g. diuretics) and other substances that may decrease "
        "blood pressure (e.g. nitrates, tricyclic antidepressants, anaesthetics, acute "
        "alcohol intake, baclofen, alfuzosin, doxazosin, prazosin, tamsulosin):"
    )
    section = Section(code="4.5", heading="Interactions", text=interaction)

    assert [c.text for c in clauses(section)] == [interaction]


def test_inline_bullets_split_even_without_newlines() -> None:
    """Zentiva's §4.3 arrives as one line of eight bullets.

    Splitting on newlines alone made the whole section a single clause, so every concept
    in it quoted the entire section as evidence and a concept from one bullet was reported
    against another's placement.
    """
    section = Section(
        code="4.3",
        heading="Contraindications",
        text="• Hypersensitivity to the active substance. • History of angioedema. • Pregnancy.",
    )

    assert [c.text for c in clauses(section)] == [
        "Hypersensitivity to the active substance.",
        "History of angioedema.",
        "Pregnancy.",
    ]


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


def test_cross_references_are_removed_for_matching_but_not_from_the_quote(
    concepts: list[Concept],
) -> None:
    raw = "Severe renal failure (see section 4.4) and dehydration."

    assert "see section" not in prepared(raw)
    assert prepared(raw) == "severe renal failure and dehydration."

    section = Section(code="4.3", heading="C", text=raw)
    occurrence = classify(section, SHA, concepts)[0]
    assert "see section" in occurrence.quote  # the quote stays verbatim


def test_every_occurrence_quote_matches_its_stored_offsets(concepts: list[Concept]) -> None:
    for occurrence in classify(METFORMIN_43, SHA, concepts):
        assert (
            METFORMIN_43.text[occurrence.char_start : occurrence.char_end] == occurrence.quote
        )


def test_a_clause_carrying_two_concepts_yields_two_occurrences(
    concepts: list[Concept],
) -> None:
    section = Section(
        code="4.3", heading="C", text="Hepatic insufficiency, acute alcohol intoxication."
    )

    assert {o.concept for o in classify(section, SHA, concepts)} == {"hepatic", "alcohol"}


def test_an_unmatched_clause_is_recorded_not_dropped() -> None:
    """A dropped clause is a blind spot: no concept means no row, so no divergence is seen."""
    section = Section(code="4.3", heading="C", text="Wearing an unusually large hat indoors.")

    occurrences = classify(section, SHA, [])

    assert [o.concept for o in occurrences] == [UNCLASSIFIED]
    assert occurrences[0].quote == "Wearing an unusually large hat indoors."


def test_classifying_the_real_section_finds_its_known_concepts(
    concepts: list[Concept],
) -> None:
    names = {o.concept for o in classify(METFORMIN_43, SHA, concepts)}

    assert {"hypersensitivity", "metabolic_acidosis", "glycaemic_emergency", "renal"} <= names
    assert UNCLASSIFIED not in names

WORD_CHARACTER = re.compile(r"[A-Za-z0-9]")

SHAPES = {
    "newline separated": "Shock.\nPorphyria.\nPregnancy.",
    "inline bullets": "• Hypersensitivity. • History of angioedema. • Pregnancy.",
    "newline bullets": "- Severe renal failure.\n- Hypotension.\n",
    "nested o bullets": "Renal impairment:\no obstruction of the renal artery\no dialysis",
    "colon then content": "Agents that lower blood pressure (e.g. nitrates, alcohol, baclofen):",
    "heading then clause": "4.3 Contraindications\nSevere hepatic impairment.",
    "ragged whitespace": "   Shock.   \n\n\n   Porphyria.   \n",
    "no trailing newline": "Hypersensitivity to the active substance",
}


@pytest.mark.parametrize("shape", SHAPES)
def test_every_dropped_word_is_attributable_to_a_named_rule(shape: str) -> None:
    """The invariant that keeps an absence honest.

    A word the splitter drops is never offered to a concept, so the label reads as silent
    on something it states — a false `ABSENT`, the one error this project must not make.

    Drops are not forbidden: a bullet marker and a repeated heading are not content. What
    is forbidden is dropping text *no rule claims*. Asserted per span rather than as a
    coverage percentage, because a threshold lets the next formatting variant lose a
    little text quietly — which is exactly how `:$` cost 2,659 characters unnoticed.
    """
    text = SHAPES[shape]
    section = Section(code="4.3", heading="Contraindications", text=text)

    dropped = _unexplained_drops(section)

    assert not dropped, f"{dropped!r} was dropped from {text!r} by no named rule"


def _orphan_spans(text: str, covered: set[int]) -> list[tuple[int, int]]:
    """Runs of word characters that no clause covers."""
    spans: list[tuple[int, int]] = []
    for index, character in enumerate(text):
        if not WORD_CHARACTER.match(character) or index in covered:
            continue
        if spans and spans[-1][1] == index:
            spans[-1] = (spans[-1][0], index + 1)
        else:
            spans.append((index, index + 1))
    return spans


def _line_around(text: str, index: int) -> str:
    """The whole line containing `index` — a heading is only recognisable in full."""
    return text[text.rfind("\n", 0, index) + 1 :].split("\n")[0].strip()


def _explained(dropped: str, line: str) -> bool:
    """Whether a named rule accounts for this text: a bullet marker, or a heading line."""
    if BULLET.match(f"{dropped} "):
        return True
    return bool(HEADER.fullmatch(line) or LEAD_IN.search(line))


def test_every_clause_quote_is_a_slice_of_the_section() -> None:
    """`Clause.text` must be the exact span, never a cleaned copy — offsets are the proof."""
    for text in SHAPES.values():
        section = Section(code="4.3", heading="C", text=text)
        for clause in clauses(section):
            assert section.text[clause.start : clause.end] == clause.text


@pytest.mark.corpus
def test_no_word_in_the_real_corpus_falls_outside_a_clause(
    corpus_sections: list[Section],
) -> None:
    """The synthetic shapes above are ones we thought of; this is what actually shipped.

    This is the check that would have caught the `:$` rule, which passed every unit test
    while discarding 2,659 characters of real label text.
    """
    orphaned = [
        (section.code, dropped)
        for section in corpus_sections
        for dropped in _unexplained_drops(section)
    ]

    assert not orphaned, f"{len(orphaned)} unexplained drops, e.g. {orphaned[:5]}"


@pytest.mark.corpus
def test_no_section_collapses_into_a_single_clause(
    corpus_sections: list[Section],
) -> None:
    """Coverage cannot catch this, which is why it is asserted separately.

    Zentiva's §4.3 — eight bullets on one line — scored ~100% coverage as a single
    912-character clause. Every word reached the classifier and the result was still
    wrong: one blob matches every concept anywhere in it, so a concept from one bullet was
    reported against another's placement, and each quoted the whole section as evidence.
    """
    blobs = [
        (section.code, markers, len(clauses(section)))
        for section in corpus_sections
        if (markers := sum(section.text.count(g) for g in SPLITTING_GLYPHS)) >= 3
        and len(clauses(section)) < markers
    ]

    assert not blobs, f"sections with bullets that did not split: {blobs}"


def _unexplained_drops(section: Section) -> list[str]:
    """Text no named rule accounts for. Empty is the invariant."""
    covered: set[int] = set()
    for clause in clauses(section):
        covered.update(range(clause.start, clause.end))
    return [
        section.text[start:end]
        for start, end in _orphan_spans(section.text, covered)
        if not _explained(section.text[start:end], _line_around(section.text, start))
    ]
