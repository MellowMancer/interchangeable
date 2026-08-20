"""One authorised product — a column in the comparison."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Product:
    """A single authorised product of one substance, as one publisher lists it.

    `external_id` is whatever the source calls it. Products of the same substance from
    different holders are the thing this project exists to compare, so the holder is a
    first-class field rather than a detail of the name.
    """

    source_id: str
    external_id: str
    substance_id: str
    name: str
    ma_holder: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("product source_id is required")
        if not self.external_id:
            raise ValueError("product external_id is required")
        if not self.substance_id:
            raise ValueError("product substance_id is required")
        if not self.name:
            raise ValueError("product name is required")
