"""The provenance-carrying unit of output."""

from dataclasses import dataclass, field
from datetime import date

from preward.domain.tier import ExtractionMethod, Tier


@dataclass(frozen=True, slots=True)
class Signal:
    """A tiered, sourced claim about a record, anchored to an exact span of page text.

    Every field below is either rendered in the UI or used to link back to the source.
    `quote` must be byte-identical to `page.text[char_start:char_end]`; `fired_cues` is
    the explanation shown to the user, not a debug aid.
    """

    record_id: int
    document_sha256: str
    page_no: int
    tier: Tier
    confidence: float
    quote: str
    char_start: int
    char_end: int
    extraction_method: ExtractionMethod
    fired_cues: tuple[str, ...] = field(default_factory=tuple)
    amount_cents: int | None = None
    event_date: date | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.quote:
            raise ValueError("a signal without a verbatim quote has no provenance")
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within 0.0..1.0")
        if self.tier > Tier.MENTION and not self.fired_cues:
            raise ValueError("tiers above MENTION must record the cues that fired")
