"""M1 exit criterion: a Signal round-trips through the Repository port intact."""

from datetime import date

from preward.domain import ExtractionMethod, Record, Signal, Tier
from preward.pipeline.ports import Repository


def test_record_save_assigns_id(seeded_record: Record) -> None:
    assert seeded_record.id is not None
    assert seeded_record.designation == "REC-2024-01"


def test_signal_round_trips_with_provenance_intact(
    repository: Repository, seeded_record: Record
) -> None:
    quote = "awarded to Example Contractors in the amount of $15,200,000"
    saved = repository.save_signal(
        Signal(
            record_id=seeded_record.id,
            document_sha256="a" * 64,
            page_no=12,
            tier=Tier.EXECUTION,
            confidence=0.92,
            quote=quote,
            char_start=1040,
            char_end=1040 + len(quote),
            amount_cents=1_520_000_000,
            event_date=date(2025, 1, 6),
            fired_cues=("awarded", "org_and_money_same_sentence"),
            extraction_method=ExtractionMethod.NATIVE,
        )
    )

    assert saved.id is not None

    (loaded,) = repository.signals_for_record(seeded_record.id)

    assert loaded.quote == quote
    assert loaded.char_start == 1040
    assert loaded.char_end == 1040 + len(quote)
    assert loaded.tier is Tier.EXECUTION
    assert loaded.amount_cents == 1_520_000_000
    assert loaded.event_date == date(2025, 1, 6)
    assert loaded.fired_cues == ("awarded", "org_and_money_same_sentence")
    assert loaded.extraction_method is ExtractionMethod.NATIVE


def test_signals_for_record_returns_the_ladder_chronologically(
    repository: Repository, seeded_record: Record
) -> None:
    for event_date, tier, cue in [
        (date(2025, 1, 6), Tier.EXECUTION, "awarded"),
        (date(2023, 6, 1), Tier.EXPLORATION, "feasibility study"),
        (date(2024, 5, 14), Tier.COMMITMENT, "budgeted line item"),
    ]:
        repository.save_signal(
            Signal(
                record_id=seeded_record.id,
                document_sha256="a" * 64,
                page_no=1,
                tier=tier,
                confidence=0.8,
                quote=f"quote for {cue}",
                char_start=0,
                char_end=10,
                event_date=event_date,
                fired_cues=(cue,),
                extraction_method=ExtractionMethod.OCR,
            )
        )

    ladder = repository.signals_for_record(seeded_record.id)

    assert [signal.event_date for signal in ladder] == [
        date(2023, 6, 1),
        date(2024, 5, 14),
        date(2025, 1, 6),
    ]
