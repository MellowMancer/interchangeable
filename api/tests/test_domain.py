"""Domain invariants. A signal that cannot be traced back to its source is not a signal."""

import pytest

from preward.domain import Document, ExtractionMethod, Page, Signal, Tier


def _signal(**overrides) -> Signal:
    defaults = dict(
        record_id=1,
        document_sha256="a" * 64,
        page_no=1,
        tier=Tier.MENTION,
        confidence=0.5,
        quote="a verbatim span of page text",
        char_start=0,
        char_end=27,
        extraction_method=ExtractionMethod.NATIVE,
    )
    return Signal(**{**defaults, **overrides})


def test_signal_requires_a_verbatim_quote() -> None:
    with pytest.raises(ValueError, match="provenance"):
        _signal(quote="")


def test_signal_rejects_inverted_char_span() -> None:
    with pytest.raises(ValueError, match="char_end"):
        _signal(char_start=30, char_end=10)


def test_signal_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _signal(confidence=1.5)


def test_tiers_above_mention_must_explain_themselves() -> None:
    with pytest.raises(ValueError, match="cues"):
        _signal(tier=Tier.EXECUTION, fired_cues=())


def test_mention_tier_needs_no_cues() -> None:
    assert _signal(tier=Tier.MENTION).fired_cues == ()


def test_document_rejects_non_sha256_key() -> None:
    with pytest.raises(ValueError, match="sha256"):
        Document(sha256="deadbeef", source_id="example-source", source_url="https://example.test")


def test_pages_are_one_indexed() -> None:
    with pytest.raises(ValueError, match="1-indexed"):
        Page(page_no=0, text="", extraction_method=ExtractionMethod.NATIVE)
