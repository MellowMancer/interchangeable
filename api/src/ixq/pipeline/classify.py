"""S4 — say what each clause is about, or record that nothing matched."""

from collections.abc import Sequence

from ixq.domain import UNCLASSIFIED, Concept, Occurrence, Section, clauses, found_in


def classify(
    section: Section, document_sha256: str, concepts: Sequence[Concept]
) -> list[Occurrence]:
    """Every concept found in every clause of a section.

    A clause matching no concept yields one `unclassified` occurrence rather than nothing.
    Dropping it would make the gap invisible, and an invisible gap is a blind spot in the
    comparison: concepts are the rows, so a clause with no concept has no row, and a
    divergence in it can never be seen. Held-out coverage runs ~75-80%, so this is the
    normal case, not an error path.
    """
    occurrences: list[Occurrence] = []
    for clause in clauses(section):
        names = [c.name for c in concepts if c.matches(clause.text)] or [UNCLASSIFIED]
        occurrences.extend(
            found_in(section, document_sha256, name, clause.start, clause.end)
            for name in names
        )
    return occurrences
