"""One authorised product — a column in the comparison."""

import re
from dataclasses import dataclass

STRENGTH = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|g)\b(?:\s*/\s*(\d+(?:[.,]\d+)?)\s*(ml|l)\b)?", re.I
)
FORM = re.compile(r"\b(oral solution|solution|capsules?|tablets?|sachets?|granules)\b", re.I)


def variant(name: str) -> str | None:
    """The strength and form that distinguish one product from its stablemates.

    Derived from the stored name rather than collected. Asking the scraper for it would
    spend Bright Data quota on something already in hand, add a field that can drift when
    a page moves, and put a judgement into the collector — where this project keeps none.
    Parsing here is deterministic and testable against names no collector has returned.

    Returns `None` when the name does not carry both, so the caller can fall back to the
    full name. A manufacturer selling several strengths otherwise gets columns that are
    identical to read, which is the failure this exists to prevent.
    """
    strength, form = STRENGTH.search(name), FORM.search(name)
    if not strength or not form:
        return None
    amount = f"{strength.group(1).replace(',', '.')}{strength.group(2).lower()}"
    if strength.group(3):
        amount += f"/{strength.group(3).replace(',', '.')}{strength.group(4).lower()}"
    return f"{amount} {form.group(1).title()}"


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
