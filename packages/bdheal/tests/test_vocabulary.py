"""The closed vocabularies, pinned as sets rather than as four hand-kept copies.

Nothing here exercises behaviour — these are the statements the rest of the package
assumes and no single feature owns. Each one was, until now, either restated in two
modules or implied by a complement nobody checked, which is the same defect twice: a
fifth member arrives and only one of the readers learns about it.
"""

from bdheal.vocabulary import (
    AMBIGUOUS_CODES,
    COLLECTOR_FAULT_CODES,
    SIGNAL_PRECEDENCE,
    TARGET_REFUSAL_CODES,
    TERMINAL_STATUSES,
    HealStatus,
    SignalKind,
)


def test_the_terminal_statuses_are_every_status_but_the_one_at_the_gate() -> None:
    """The set is derived from `HealStatus`, so a fifth member cannot be forgotten.

    `awaiting_approval` is the only non-terminal state: it records that a heal was
    proposed, not that anything was kept. Both the facade's promote/rollback decision and
    the benchmark's `healed` count read this set, and they disagreeing silently is the
    drift that made it one set instead of two.
    """
    assert TERMINAL_STATUSES == set(HealStatus) - {HealStatus.AWAITING_APPROVAL}


def test_the_signal_precedence_ranks_every_detector_exactly_once() -> None:
    """A detector missing from the order is one no classification and no credit can reach.

    `diagnose` maps this order onto failure classes and the benchmark credits a detector
    by it. A fifth `SignalKind` added without a rank would silently classify as `UNKNOWN`
    and publish as a coverage gap — twice, in two modules, from one omission.
    """
    assert set(SIGNAL_PRECEDENCE) == set(SignalKind)
    assert len(SIGNAL_PRECEDENCE) == len(SignalKind)


def test_the_error_code_classes_are_a_partition() -> None:
    """No code is both the target's fault and the scraper's. One code, one verdict.

    `detect` implements the rule as a complement — a code that is neither a refusal nor
    ambiguous is extraction evidence — so a code landing in two classes would make the
    named set and the running rule disagree about the same payload, which is precisely the
    ambiguity the classification exists to remove.
    """
    classes = (TARGET_REFUSAL_CODES, AMBIGUOUS_CODES, COLLECTOR_FAULT_CODES)

    assert sum(len(codes) for codes in classes) == len(set().union(*classes))
