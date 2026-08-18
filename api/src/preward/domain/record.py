"""The thing signals accumulate about."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Record:
    """A subject tracked across documents and over time.

    `designation` is any identifier the source itself assigns. Where one exists it is
    the highest-precision anchor for resolution; where it does not, resolution falls
    back to fuzzy name matching.
    """

    source_id: str
    name: str
    designation: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("record name is required")
