"""The active ingredient products are compared across."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Substance:
    """An active ingredient, and the key that groups products for comparison.

    `id` is a slug the roster assigns, not an identifier any source owns: the same
    ingredient is named differently by every publisher, so the join key has to be ours.
    """

    id: str
    name: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("substance id is required")
        if not self.name:
            raise ValueError("substance name is required")
