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

BULLET = re.compile(r"^[\s ]*(?:[•·\-–—*]|o(?=\s))[\s ]*")
"""A bullet marker. `o` only counts when whitespace follows it.

EMC nests sub-bullets as a literal `o`, but stripping `o` as a character would turn
`obstruction` into `bstruction` — killing the concept match and corrupting the quote
shown to the user.
"""

CROSS_REFERENCE = re.compile(r"\(\s*see (?:also )?sections?[^)]*\)?", re.I)
WHITESPACE = re.compile(r"\s+")
HAS_WORD = re.compile(r"[A-Za-z]{3,}")

LEAD_IN = re.compile(
    r":$"                           # anything that merely introduces a list
    r"|^general contraindications"
    r"|^contraindicat\w*$",
    re.I,
)
"""A clause ending in a colon introduces the real clauses; it asserts nothing itself.

Measured: lead-ins were 12% of apparent classification misses — `Tamoxifen should not be
used in:`, `General contraindications (all indications)`.
"""


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
    offset = 0
    for line in text.split("\n"):
        start, end = _trim(line, offset)
        offset += len(line) + 1
        if end <= start:
            continue
        body = text[start:end]
        if not HAS_WORD.search(body) or HEADER.fullmatch(body) or LEAD_IN.search(body):
            continue
        found.append(Clause(start=start, end=end, text=body))
    return found


def _trim(line: str, offset: int) -> tuple[int, int]:
    """The span of `line` with its bullet and surrounding whitespace removed."""
    lead = BULLET.match(line)
    start = offset + (lead.end() if lead else len(line) - len(line.lstrip()))
    return start, offset + len(line.rstrip())
