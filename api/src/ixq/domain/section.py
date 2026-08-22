"""One numbered section of a label, and the clauses it asserts."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Section:
    """A numbered section, verbatim.

    `code` is the publisher's own numbering, kept as a string because it is an identifier
    rather than a quantity. `text` is the section as published: every quote this project
    shows is a slice of it, so normalising it destroys the provenance built on top.
    """

    code: str
    heading: str
    text: str

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("section code is required")


@dataclass(frozen=True, slots=True)
class Clause:
    """One statement within a section, addressed by its span in the section's own text.

    `text` is the exact slice at `[start, end)` — never a cleaned copy. Cleaning happens
    for matching only, because a quote that has been tidied can no longer be checked
    against the source it claims to come from.
    """

    start: int
    end: int
    text: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("clause end must be greater than start")
        if not self.text:
            raise ValueError("a clause with no text has nothing to classify")


HEADER = re.compile(r"\s*\d+\.\d+\s+[A-Za-z][A-Za-z, ]*")
"""A section heading: a number, then words. Matched with `fullmatch`, deliberately.

A prefix match would eat real clauses — `2.5 mg/5 ml oral solution` and `1.5 g daily in
renal impairment` both open with `d.d` and are contraindications, not headings.
"""

BULLET_GLYPHS = "•▪▫●○‣⁃∙"
"""Characters with no use but a list marker. Always a boundary, attached or not.

Attachment cannot be required of these. One label writes its §4.3 as
`... section 6.1• cardiogenic shock• uncontrolled heart failure• ...` — every bullet glued
to the word before it — so a rule that demanded whitespace in front collapsed ten
contraindications into three clauses."""

AMBIGUOUS_GLYPHS = "*◦·"
"""Characters that are a list marker *or* typography, decided by what precedes them.

`◦` is U+25E6 WHITE BULLET and is also how one label writes a degree sign, so
`Store below 25◦ C` split into `Store below 25` and a `C` that was then dropped for
carrying no word — a storage temperature severed from its unit and half-lost. `*` is a
bullet and also a trademark mark, so `Bedranol* SR` shed its suffix the same way. `·` is a
bullet and also a decimal point in British usage.

All three are unambiguous when they open an item, because a list marker never attaches to
the token before it. That is the whole rule, and it is why these three are separated from
the glyphs above rather than treated alike."""

MARK_GLYPHS = BULLET_GLYPHS + AMBIGUOUS_GLYPHS

FREE_GLYPHS = "\u2003"
"""Whitespace that marks a list item. Always a boundary, because splitting on whitespace
can strand nothing: it belongs to neither side."""

SPLITTING_GLYPHS = MARK_GLYPHS + FREE_GLYPHS
"""Markers unambiguous enough to end a clause mid-line.

Shared by `BULLET` and `SEGMENT` on purpose. They diverged once — `BULLET` knew `*`, `–`
and `—` while `SEGMENT` knew only `•` and `·` — so a publisher bulleting inline with `*`
had its markers trimmed at line start but never split, rebuilding exactly the
single-clause section this module was fixed to prevent. Nothing would have caught it:
no text is dropped, the clause is merely the wrong size.

`\u2003` (EM SPACE) is the same failure with a different character. Three publishers
bullet one shared passage three ways: `\n\n- `, `\n\n • `, and — Zentiva — `\u2003- `,
with no newline at all. The first two split on the newline and the third did not, so
Zentiva's §4.4 held one 730-character clause spanning eight bullets and every concept in
it quoted all eight. Measured across the corpus before adding it: all seven em spaces
introduce a list marker and none occurs mid-sentence, so it cannot cut a sentence in half
and strand a pattern across the join. It is whitespace, so consuming it drops no content
— unlike a hyphen, which carries meaning inside words. A hyphen does now open a clause,
but only where an item begins; see `SEGMENT`.
"""

BULLET = re.compile(rf"^[\s ]*(?:[{re.escape(SPLITTING_GLYPHS)}\-–—]|o(?=\s))[\s ]*")
"""A bullet marker. `o` only counts when whitespace follows it.

EMC nests sub-bullets as a literal `o`, but stripping `o` as a character would turn
`obstruction` into `bstruction` — killing the concept match and corrupting the quote
shown to the user.
"""

CROSS_REFERENCE = re.compile(r"\(\s*see (?:also )?sections?[^)]*\)?", re.I)
WHITESPACE = re.compile(r"\s+")
HAS_CONTENT = re.compile(r"[0-9A-Za-z]")
"""A fragment asserts something if it carries any letter or digit at all.

This was a three-letter floor, which is right for prose and wrong for the specification
sections added later. §3 and §6.1 state alternatives as a bare `OR`, strengths as `80` and
`2 mg:`, and a specification as `pH: 4.0 – 8.0` — none of which contains a three-letter run,
so each was dropped whole. Measured across the corpus, the lower floor admits exactly those
six fragments and loses nothing: it is not a loosening that lets noise in, it is the removal
of an assumption that only ever held for the four sections this parser started with.

A marker or punctuation on its own still carries nothing and is still dropped."""

LEAD_IN = re.compile(
    r"^general contraindications(?:\s*\([^)]*\))?:?\s*$|^contraindicat\w*$", re.I
)
"""A restatement of the section's own heading, asserting nothing the heading did not.

**A trailing colon is deliberately not a lead-in.** It was, and it destroyed content: EMC
writes interaction entries as `<subjects>: <consequence>` on one line, so `Antihypertensive
agents (e.g. diuretics) and other substances that may decrease blood pressure (e.g.
nitrates, ... acute alcohol intake, baclofen, ...):` was dropped whole. Measured across the
ramipril corpus that rule discarded 24 lines and 2,659 characters — every character of loss
in the pipeline — and manufactured two false divergences, because manufacturers whose text
was dropped read as ABSENT on concepts they in fact state.

What it was solving (lead-ins inflating the unclassified count) is a metric concern.
Dropping them is a correctness one: an unclassified clause is a visible gap, a dropped
clause is an invisible false absence.
"""

SEGMENT = re.compile(
    rf"[\n{re.escape(FREE_GLYPHS + BULLET_GLYPHS)}]"
    rf"|(?<![0-9A-Za-z])[{re.escape(AMBIGUOUS_GLYPHS)}]"
    rf"|(?:(?<=[.;:)])\s|^)-(?=\s+[A-Za-z])"
)
"""Newline, a bullet glyph opening an item, or a hyphen being used as one.

**An *ambiguous* glyph attached to the preceding token is not a bullet.** A list marker
never attaches to the token before it, so `25◦ C` and `Bedranol* SR` are a degree sign and
a trademark mark — and cutting there severed a temperature from its unit and a product name
from its suffix, each remainder then dropped for carrying no word.

The lookbehind applies **only** to `AMBIGUOUS_GLYPHS`. Requiring it of every glyph was
tried and was wrong: one publisher writes `shock• uncontrolled heart failure•` with no
space before any bullet, and the universal rule collapsed ten contraindications into three
clauses. `\u2003` is exempt for a different reason — it is whitespace, so it cannot attach
to anything, and Zentiva writes `in:\u2003- patients` with no space in front.

The hyphen arm was added 2026-08-21 after §4.1 tripped
`test_no_section_collapses_into_a_single_clause`: EMC writes top-level indications as
`- Treatment of hypertension. - Cardiovascular prevention: ...` on a single line, with
sub-bullets in EM SPACE glyphs beneath. Without it those merge, and the same style was
found in five comparable §4.4 sections carrying 29 such bullets — so this was mis-splitting
real safety content, not only the new section that exposed it.

It is deliberately narrow, and was narrowed again after review. A hyphen splits only
where an item *opens* — after sentence-ending punctuation, or at the very start — so the
compounds and ranges these labels are full of are untouched: `2-8°C`, `6-17`,
`non-diabetic`, `cardio-protective`. An earlier form split on any spaced hyphen and broke
prose dashes apart, turning `hepatic impairment - including cirrhosis - or biliary
obstruction` into three fragments and stranding the negation."""


def prepared(text: str) -> str:
    """Text reduced for *matching only*. Never stored, never quoted.

    Case-folds and drops cross-references in one place: their section numbers would
    otherwise read as content, and a caller preparing input half-way gets a different
    answer with no error.
    """
    return WHITESPACE.sub(" ", CROSS_REFERENCE.sub(" ", text)).strip().lower()


def clauses(section: Section) -> list[Clause]:
    """Every clause in a section, each addressed by its exact span in the section text.

    Offsets are into the untouched text, so a quote built from one can always be checked
    against the stored section.

    The only things dropped are headings, list lead-ins, and fragments carrying no word
    at all. There is no length filter: `Porphyria.` is a real contraindication at ten
    characters, and a 466-character paragraph is a real one too. Dropping either would be
    a silent loss, which is the failure this pipeline exists to avoid.
    """
    text = section.text
    found: list[Clause] = []
    cut = 0
    for boundary in SEGMENT.finditer(text):
        _emit(text, cut, boundary.start(), found)
        cut = boundary.end()
    _emit(text, cut, len(text), found)
    return found


def _emit(text: str, lo: int, hi: int, found: list[Clause]) -> None:
    """Append the segment at `[lo, hi)` as a clause, unless it asserts nothing."""
    start, end = _trim(text, lo, hi)
    if end <= start:
        return
    body = text[start:end]
    if not HAS_CONTENT.search(body) or HEADER.fullmatch(body) or LEAD_IN.search(body):
        return
    found.append(Clause(start=start, end=end, text=body))


def _trim(text: str, lo: int, hi: int) -> tuple[int, int]:
    """The span of `text[lo:hi]` with its bullet and surrounding whitespace removed."""
    segment = text[lo:hi]
    lead = BULLET.match(segment)
    start = lo + (lead.end() if lead else len(segment) - len(segment.lstrip()))
    return start, lo + len(segment.rstrip())
