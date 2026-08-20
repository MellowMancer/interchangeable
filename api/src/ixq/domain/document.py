"""The document a product's label is published as."""

import re
from dataclasses import dataclass

REVISION_DATE = re.compile(
    r"^\s*(?:revised|last\s+revised|updated)?[:\s]*("
    r"\d{4}-\d{2}-\d{2}"                    # 2026-07-14 — ISO, and what a heal may emit
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"      # 14/07/2026, 31-07-2024
    r"|\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}"     # 04 June 2021
    r"|[A-Za-z]{3,}\s+\d{1,2},\s*\d{4}"    # July 14, 2026
    r"|[A-Za-z]{3,}\s+\d{4}"                # November 2025
    r")",
    re.I,
)


def revision_date(raw: str | None) -> str | None:
    """The revision date at the start of `raw`, with any trailing page text dropped.

    Publishers print the date immediately before whatever section follows it, and the
    collector sometimes takes both — `31-07-2024 11. DOSIMETRY 12. INSTRUCTIONS FOR
    PREPARATION OF RADIOPHARMACEUTICALS`. Healing the collector fixes the layouts it was
    shown; this guarantees the rest, because the rule is the same everywhere and a
    deterministic function can be tested against layouts nobody has seen.

    ISO-8601 is accepted even though no current publisher emits it: `revised` is hashed
    into the document's content address, so a heal that normalises the date would return
    `None` here and silently fork every address in the corpus against its own occurrences.

    Returns None when there is no leading date. Storing an unparsed string would put page
    furniture in front of a reader as though it were a date.
    """
    found = REVISION_DATE.match(raw or "")
    return " ".join(found.group(1).split()) if found else None


@dataclass(frozen=True, slots=True)
class Document:
    """A published label, content-addressed by the sha256 of its bytes.

    It names its product by the source's own identifier rather than a database id, so a
    document can be stored before or after the product it belongs to.

    `last_updated` is a string, not a date: publishers state month precision
    ("November 2025"), and parsing it into a date would invent a day nobody published.
    It matters because a difference between two labels may be staleness rather than
    disagreement, and a comparison that cannot show revision dates cannot tell them apart.
    """

    sha256: str
    source_id: str
    product_external_id: str
    source_url: str
    title: str | None = None
    active_substance: str | None = None
    last_updated: str | None = None

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex digest")
        if not self.source_id:
            raise ValueError("document source_id is required")
        if not self.product_external_id:
            raise ValueError("document product_external_id is required")
