"""S4 — say what each clause is about, or record that nothing matched."""

from collections.abc import Sequence

from ixq.domain import UNCLASSIFIED, Concept, Occurrence, Section, clauses, found_in
from ixq.pipeline.ports import Repository


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


def classify_document(
    document_sha256: str, repository: Repository, concepts: Sequence[Concept]
) -> int:
    """Derive and store every occurrence of one stored document. Returns how many.

    The one path from stored sections to stored occurrences, used both after a fetch and
    when re-deriving without one. Occurrences are cleared first, which is what makes it
    safe to run twice: they are keyed by character span, so a change to how clauses are
    cut gives the same finding a new span, and inserting without clearing leaves the old
    row beside it. On a document that has none — the fetch path — the clear does nothing.

    The caller owns the transaction, as everywhere else in the pipeline. It has to: a
    failure between the clear and the last insert would otherwise leave a document whose
    sections are intact and whose findings are gone.
    """
    repository.delete_occurrences(document_sha256)
    stored = 0
    for section in repository.sections_for_document(document_sha256):
        for occurrence in classify(section, document_sha256, concepts):
            repository.save_occurrence(occurrence)
            stored += 1
    return stored
