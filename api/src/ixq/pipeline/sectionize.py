"""S3 — split a section into the clauses a label actually asserts."""

import re

from ixq.domain import Clause, Section

HEADER = re.compile(r"^\s*\d+\.\d+\s*[a-z, ]*\s*", re.I)
CROSS_REFERENCE = re.compile(r"\(\s*see (also )?sections?[^)]*\)?", re.I)
WHITESPACE = re.compile(r"\s+")

LEAD_IN = re.compile(
    r":\s*$"                        # anything that merely introduces a list
    r"|^general contraindications"
    r"|^contraindicat\w*$",
    re.I,
)
"""A clause ending in a colon introduces the real clauses; it asserts nothing itself.

Measured: lead-ins were 12% of apparent classification misses — `Tamoxifen should not be
used in:`, `General contraindications (all indications)`. Counting them as unclassified
overstates the lexicon's gaps and hides the real ones.
"""

MIN_LENGTH = 12
MAX_LENGTH = 400
BULLET_CHARS = " \t•·-–—o"


def normalise(text: str) -> str:
    """A clause reduced for *matching only*. Never stored, never quoted.

    Cross-references carry no clinical meaning and their section numbers would otherwise
    look like content, so they come out before matching.
    """
    return WHITESPACE.sub(" ", CROSS_REFERENCE.sub(" ", text)).strip()


def clauses(section: Section) -> list[Clause]:
    """Every clause in a section, each addressed by its exact span in the section text.

    Offsets are into the untouched text, so a quote built from one can always be checked
    against the stored section.
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
        if HEADER.match(body) and len(body) < 60:
            continue
        if not MIN_LENGTH < len(body) < MAX_LENGTH:
            continue
        if LEAD_IN.search(body):
            continue
        found.append(Clause(start=start, end=end, text=body))
    return found


def _trim(line: str, offset: int) -> tuple[int, int]:
    """The span of `line` with bullets and whitespace removed, in section coordinates."""
    stripped = line.lstrip(BULLET_CHARS)
    start = offset + (len(line) - len(stripped))
    return start, start + len(stripped.rstrip())
