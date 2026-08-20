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
    id: int | None = None

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
