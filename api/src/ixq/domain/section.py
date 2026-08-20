"""One numbered section of a label."""

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
