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
