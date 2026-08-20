"""A site whose documents are collected."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Source:
    """A publisher of documents, keyed by slug.

    `variant` names the collector's layout family (HTML structure), not anything
    about the subject matter.
    """

    id: str
    name: str
    base_url: str
    variant: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("source id is required")
