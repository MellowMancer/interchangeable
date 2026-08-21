"""What a label clause is about, and where it sits."""

from dataclasses import dataclass
from enum import StrEnum

from ixq.domain.section import prepared

UNCLASSIFIED = "unclassified"
"""Recorded for a clause no concept matched. A published recall gap, never a dropped row."""


class Placement(StrEnum):
    """Where a concept was found — the distinction the whole comparison rests on.

    `ABSENT` means *not found in any section that was scanned*, which is not the same as
    absent from the label. It is only meaningful alongside the set of sections actually
    scanned, so any caller reporting it must report that set too.
    """

    CONTRAINDICATION = "4.3"
    WARNING = "4.4"
    INTERACTION = "4.5"
    PREGNANCY = "4.6"
    EXCIPIENT = "6.1"
    """Composition, not a clinical judgement — and the whole point of comparing generics.

    Two products that agree on every clinical section can still differ on lactose, soya or
    an azo colourant, which is a real reason one is not interchangeable for one patient.
    It ranks last because §6.1 states what is *in* the product rather than who must avoid
    it: a concept named in both 4.3 and 6.1 is a contraindication that happens to have an
    ingredient, not an ingredient that happens to be contraindicated.
    """

    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class Concept:
    """A named clinical concept and the stems that identify it in prose.

    Patterns are stems rather than whole words, matched case-insensitively, so one entry
    covers a family of inflections. They are lowercased on construction because the
    comparison is, and a mixed-case pattern would silently never match.
    """

    name: str
    patterns: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("concept name is required")
        if self.name == UNCLASSIFIED:
            raise ValueError(f"{UNCLASSIFIED!r} is reserved for clauses nothing matched")
        if not self.patterns:
            raise ValueError(f"concept {self.name!r} needs at least one pattern")
        object.__setattr__(self, "patterns", tuple(p.lower() for p in self.patterns))

    def matches(self, text: str) -> bool:
        """Whether any pattern appears in `text`.

        Owns the whole matching contract — case folding *and* cross-reference removal.
        Splitting it left a caller able to pass raw text and get a different answer with
        no error, for a rule that is impossible to get right by accident.
        """
        text = prepared(text)
        return any(pattern in text for pattern in self.patterns)
