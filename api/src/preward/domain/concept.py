"""Where a concept sits in a label."""

from enum import StrEnum


class Placement(StrEnum):
    """Where a concept was found — the distinction the whole comparison rests on.

    `ABSENT` means *not found in any section that was scanned*, which is not the same as
    absent from the label. It is only meaningful alongside the set of sections actually
    scanned, so any caller reporting it must report that set too.
    """

    CONTRAINDICATION = "4.3"
    WARNING = "4.4"
    PREGNANCY = "4.6"
    ABSENT = "absent"
