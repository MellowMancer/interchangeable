"""Source documents and their pages."""

from dataclasses import dataclass
from datetime import date

from preward.domain.tier import ExtractionMethod


@dataclass(frozen=True, slots=True)
class Page:
    """One page of extracted text, tagged with how the text was obtained."""

    page_no: int
    text: str
    extraction_method: ExtractionMethod

    def __post_init__(self) -> None:
        if self.page_no < 1:
            raise ValueError("page_no is 1-indexed")


@dataclass(frozen=True, slots=True)
class Document:
    """A published document, content-addressed by the sha256 of its bytes."""

    sha256: str
    source_id: str
    source_url: str
    title: str | None = None
    published_date: date | None = None
    category: str | None = None
    page_count: int | None = None

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex digest")
