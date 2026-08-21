"""The provenance-carrying unit of output."""

from dataclasses import dataclass

from ixq.domain.section import Section


@dataclass(frozen=True, slots=True)
class Occurrence:
    """A concept found in one section of one document, anchored to exact source text.

    `quote` must be byte-identical to `section.text[char_start:char_end]`. Build these
    through `found_in` rather than by hand: a quote assembled separately from the offsets
    can drift from them, and then every claim resting on it is unverifiable.
    """

    document_sha256: str
    section_code: str
    concept: str
    quote: str
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if not self.quote:
            raise ValueError("an occurrence without a verbatim quote has no provenance")
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if not self.section_code:
            raise ValueError("occurrence section_code is required")
        if not self.concept:
            raise ValueError("occurrence concept is required")


def found_in(
    section: Section, document_sha256: str, concept: str, char_start: int, char_end: int
) -> Occurrence:
    """An occurrence whose quote is sliced from the section, so the two cannot disagree."""
    if char_end > len(section.text):
        raise ValueError("char_end runs past the end of the section text")
    return Occurrence(
        document_sha256=document_sha256,
        section_code=section.code,
        concept=concept,
        quote=section.text[char_start:char_end],
        char_start=char_start,
        char_end=char_end,
    )


@dataclass(frozen=True, slots=True)
class Context:
    """A quote's surroundings, with the quote's own span inside them.

    `text` is a slice of the stored section, never a cleaned copy, so `text[quote_start:
    quote_end]` is byte-identical to the occurrence's quote — the same guarantee the
    offsets carry, held one level down.

    `truncated_start` and `truncated_end` say which ends were cut. Without them a window
    that stops mid-sentence is indistinguishable from a section that ends there, and the
    reader is invited to conclude the label says nothing further.
    """

    text: str
    quote_start: int
    quote_end: int
    truncated_start: bool
    truncated_end: bool
    # The whole section's length, which the window alone cannot imply. Without it a
    # reader can see the quote's surroundings but not where in the section it falls, and
    # a clause near the end is indistinguishable from one near the start.
    section_length: int


def in_context(section_text: str, occurrence: Occurrence, radius: int) -> Context:
    """The section text `radius` characters either side of an occurrence's quote.

    Takes the text rather than a `Section` because the caller reads one section's body by
    document and code; demanding the whole entity would make it fetch a heading and a
    code it already holds.

    Offsets come back relative to the window so the caller highlights by slicing. Locating
    the quote by searching the window instead lands on the wrong instance wherever a
    clause repeats within a section, and the highlight then marks a sentence the
    occurrence does not claim.
    """
    start = max(0, occurrence.char_start - radius)
    end = min(len(section_text), occurrence.char_end + radius)
    return Context(
        text=section_text[start:end],
        quote_start=occurrence.char_start - start,
        quote_end=occurrence.char_end - start,
        truncated_start=start > 0,
        truncated_end=end < len(section_text),
        section_length=len(section_text),
    )
