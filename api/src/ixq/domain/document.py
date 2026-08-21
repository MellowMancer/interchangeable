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

    Everything below `last_updated` is what the source's *record* said at the moment of
    the fetch, not what the label text says. It lives on the document rather than the
    product because a product row is written by a different collector at a different
    time, and merging two collectors' answers into one row makes the fresher one
    unattributable.
    """

    sha256: str
    source_id: str
    product_external_id: str
    source_url: str
    title: str | None = None
    active_substance: str | None = None
    last_updated: str | None = None
    """The publisher's own revision date, from the label's section 10."""

    listing_updated: str | None = None
    """When the *source* last touched its record — a different question from `last_updated`.

    The two disagree routinely and by years: one product reads "18 Apr 2023" against a
    section 10 of "05/05/2021". Storing one and calling it "revised" makes the UI's
    staleness caveat answer a question the reader did not ask, so both are kept and each
    is labelled for what it is.
    """

    holder_id: int | None = None
    """The source's own id for the authorisation holder — the canonical identity.

    `Product.ma_holder` is free text, so two spellings of one company become two columns
    and every concept between them reads as a divergence. An id cannot be misspelt.
    """

    ingredient_id: int | None = None
    """The source's own id for the active ingredient. A check on our grouping, not a key.

    Deliberately not called `substance_id`: `Product.substance_id` is a slug we assigned,
    and two fields one word apart meaning different things is a bug waiting to be typed.
    This is the publisher asserting that two products share an ingredient — where it
    disagrees with our grouping, the comparison is comparing the wrong things.
    """

    atc_code: str | None = None
    """The WHO classification, as a labelled field rather than dug out of section 5.1."""

    legal_status: str | None = None
    ma_number: str | None = None
    """The marketing authorisation number — the regulatory identity.

    `product_external_id` is the source's internal surrogate; this is the number the
    regulator issued, and the only id that means anything outside this one website.
    """

    discontinued: bool | None = None
    """Whether the source marked the product discontinued at this fetch.

    `None` is not `False`: it means the fetch predates this field, so nothing is known.
    Collapsing them would assert every historical label was actively marketed.
    """

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character hex digest")
        if not self.source_id:
            raise ValueError("document source_id is required")
        if not self.product_external_id:
            raise ValueError("document product_external_id is required")
