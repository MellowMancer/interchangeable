"""The boundary types and the invariants they refuse to be constructed without.

Every violation here raises `ValueError` — pydantic's `ValidationError` subclasses it —
so a caller may guard the whole surface with one `except` and never import pydantic.
"""

import pytest
from conftest import FIXED_NOW, STUB_COLLECTOR_ID, SampleRow
from pydantic import BaseModel

import bdheal
from bdheal.models import (
    Baseline,
    BenchCase,
    CollectorSpec,
    DetectVerdict,
    HealEvent,
    RowError,
    RunResult,
    Signal,
    VerifyReport,
    latest_settled,
)
from bdheal.vocabulary import (
    HealStatus,
    MutationClass,
    SignalKind,
    SignalOutcome,
)

BLANK_STRINGS = ["", "   ", "\t\n"]

PUBLIC_MODELS = [
    CollectorSpec,
    RunResult,
    RowError,
    DetectVerdict,
    Signal,
    HealEvent,
    VerifyReport,
]

# One valid construction per model; every test below names the one field it spoils.
SPEC_FIELDS = {
    "collector_id": STUB_COLLECTOR_ID,
    "name": "stub collector",
    "anchor_urls": ["https://example.test/list"],
    "row_schema": SampleRow,
}
RUN_RESULT_FIELDS = {"collector_id": STUB_COLLECTOR_ID, "fetched_at": FIXED_NOW}
HEAL_EVENT_FIELDS = {
    "collector_id": STUB_COLLECTOR_ID,
    "status": HealStatus.DONE,
    "created_at": FIXED_NOW,
}
VERIFY_REPORT_FIELDS = {
    "field_accuracy": 1.0,
    "non_regression_passed": True,
    "attempts": 1,
    "elapsed_s": 1.0,
}
BASELINE_FIELDS = {
    "collector_id": STUB_COLLECTOR_ID,
    "captured_at": FIXED_NOW,
    "row_count": 1,
}
BENCH_CASE_FIELDS = {
    "run_id": "bench-1",
    "case_id": "case-1",
    "mutation": MutationClass.CLASS_RENAME,
    "expected_signals": frozenset({SignalKind.SKELETON}),
}

# Every model keyed by a caller-supplied collector id.
COLLECTOR_ID_BEARERS = [
    (CollectorSpec, SPEC_FIELDS),
    (RunResult, RUN_RESULT_FIELDS),
    (HealEvent, HEAL_EVENT_FIELDS),
    (Baseline, BASELINE_FIELDS),
]

# Fields carrying a fraction of a whole.
RATIO_FIELDS = [
    (VerifyReport, "field_accuracy", VERIFY_REPORT_FIELDS),
    (BenchCase, "field_accuracy", BENCH_CASE_FIELDS),
]

# Counters and durations that cannot run backwards.
NON_NEGATIVE_FIELDS = [
    (HealEvent, "attempts", HEAL_EVENT_FIELDS),
    (VerifyReport, "attempts", VERIFY_REPORT_FIELDS),
    (VerifyReport, "elapsed_s", VERIFY_REPORT_FIELDS),
    (Baseline, "row_count", BASELINE_FIELDS),
]


def _ids(cases: list[tuple]) -> list[str]:
    """Readable parametrisation ids: `Model`, or `Model.field` where a field is named."""
    return [".".join([model.__name__, *rest[:-1]]) for model, *rest in cases]


def test_the_public_surface_is_exported_and_documented() -> None:
    """Every boundary type is reachable from the top level, in `__all__`, and documented."""
    for model in PUBLIC_MODELS:
        assert getattr(bdheal, model.__name__, None) is model
        assert model.__name__ in bdheal.__all__
        assert (model.__doc__ or "").strip(), f"{model.__name__} has no docstring"


@pytest.mark.parametrize("blank", BLANK_STRINGS)
@pytest.mark.parametrize("model, fields", COLLECTOR_ID_BEARERS, ids=_ids(COLLECTOR_ID_BEARERS))
def test_a_blank_collector_id_is_rejected(
    model: type[BaseModel], fields: dict, blank: str
) -> None:
    """A collector id that is empty or only whitespace names no collector."""
    with pytest.raises(ValueError):
        model(**{**fields, "collector_id": blank})


def test_a_collector_id_is_stored_without_surrounding_whitespace() -> None:
    """Ids key persisted rows, so `" c1 "` and `"c1"` must not become two collectors."""
    spec = CollectorSpec(**{**SPEC_FIELDS, "collector_id": f"  {STUB_COLLECTOR_ID}\n"})
    assert spec.collector_id == STUB_COLLECTOR_ID


@pytest.mark.parametrize("anchor_urls", [[], ["  "]])
def test_a_spec_without_a_usable_anchor_url_is_rejected(anchor_urls: list[str]) -> None:
    """There is nothing to run, heal or verify against without at least one real anchor."""
    with pytest.raises(ValueError):
        CollectorSpec(**{**SPEC_FIELDS, "anchor_urls": anchor_urls})


@pytest.mark.parametrize("row_schema", [str, dict, SampleRow(title="t", url="u"), None])
def test_a_row_schema_that_is_not_a_basemodel_subclass_is_rejected(row_schema: object) -> None:
    """The schema is the schema-break detector: no pydantic validation, no signal."""
    with pytest.raises(ValueError):
        CollectorSpec(**{**SPEC_FIELDS, "row_schema": row_schema})


def test_error_codes_defaults_to_an_empty_list() -> None:
    """Callers iterate `error_codes` unguarded, so it is a list on every run — never `None`."""
    result = RunResult(**RUN_RESULT_FIELDS)
    assert result.error_codes == []
    assert result.rows == []
    assert result.errors == []


def test_error_codes_cannot_be_set_to_none() -> None:
    """The default is not a courtesy that an explicit `None` may override."""
    with pytest.raises(ValueError):
        RunResult(**{**RUN_RESULT_FIELDS, "error_codes": None})


def test_a_run_result_round_trips_through_model_dump() -> None:
    """Runs are persisted and compared, so dumping and re-validating must change nothing."""
    result = RunResult(
        **RUN_RESULT_FIELDS,
        rows=[{"title": "a", "url": "https://example.test/a", "published": None}],
        errors=[
            RowError(index=1, message="too many requests", error_code="rate_limit"),
            RowError(index=2, message="row rejected", field_errors={"title": "field required"}),
        ],
        error_codes=["rate_limit"],
    )
    assert RunResult.model_validate(result.model_dump()) == result


@pytest.mark.parametrize("ratio", [-0.01, 1.01, 2.0])
@pytest.mark.parametrize("model, field, fields", RATIO_FIELDS, ids=_ids(RATIO_FIELDS))
def test_an_accuracy_outside_the_unit_interval_is_rejected(
    model: type[BaseModel], field: str, fields: dict, ratio: float
) -> None:
    """An accuracy is a fraction of fields matched; outside `0.0..1.0` it is a bug upstream."""
    with pytest.raises(ValueError):
        model(**{**fields, field: ratio})


@pytest.mark.parametrize("ratio", [0.0, 0.75, 1.0])
def test_the_unit_interval_endpoints_are_accepted(ratio: float) -> None:
    """Nothing correct is refused: a total miss and a perfect match are both legal readings."""
    report = VerifyReport(**{**VERIFY_REPORT_FIELDS, "field_accuracy": ratio})
    assert report.field_accuracy == ratio


def test_a_null_rate_outside_the_unit_interval_is_rejected() -> None:
    """Null rates are fractions too, and detect compares them against a threshold."""
    with pytest.raises(ValueError):
        Baseline(**{**BASELINE_FIELDS, "null_rates": {"title": 1.5}})


@pytest.mark.parametrize(
    "model, field, fields", NON_NEGATIVE_FIELDS, ids=_ids(NON_NEGATIVE_FIELDS)
)
def test_a_negative_count_or_duration_is_rejected(
    model: type[BaseModel], field: str, fields: dict
) -> None:
    """Attempts, rows and elapsed seconds only ever move forward."""
    with pytest.raises(ValueError):
        model(**{**fields, field: -1})


@pytest.mark.parametrize("status", ["promoted", "pending", "", "DONE"])
def test_a_heal_status_outside_the_vocabulary_is_rejected(status: str) -> None:
    """`HealStatus` is the whole state machine; an unnamed state is an unhandled state."""
    with pytest.raises(ValueError):
        HealEvent(**{**HEAL_EVENT_FIELDS, "status": status})


@pytest.mark.parametrize("status", list(HealStatus))
def test_every_documented_heal_status_is_accepted(status: HealStatus) -> None:
    """The vocabulary is the contract in both directions: every named state constructs."""
    event = HealEvent(**{**HEAL_EVENT_FIELDS, "status": status})
    assert event.status == status
    assert event.promoted is False


@pytest.mark.parametrize("kind", ["latency", "captcha"])
def test_a_signal_kind_outside_the_vocabulary_is_rejected(kind: str) -> None:
    """The four detectors are closed; a fifth kind arrives in `vocabulary.py` or not at all."""
    with pytest.raises(ValueError):
        Signal(kind=kind, outcome=SignalOutcome.FIRED, detail="unknown detector")


def test_a_verdict_defaults_to_no_signals_and_no_throttling() -> None:
    """A healthy verdict carries an empty signal list, not `None`, and requests no retry."""
    verdict = DetectVerdict(broken=False)
    assert verdict.signals == []
    assert verdict.incomplete is False
    assert verdict.retry_requested is False
    assert verdict.reason is None


def test_a_verdict_round_trips_through_model_dump() -> None:
    """Verdicts cross the facade and the benchmark, so their enums must survive a dump."""
    verdict = DetectVerdict(
        broken=True,
        signals=[
            Signal(kind=SignalKind.SCHEMA, outcome=SignalOutcome.FIRED, detail="2 rows failed"),
            Signal(
                kind=SignalKind.ROW_COUNT,
                outcome=SignalOutcome.INCONCLUSIVE,
                detail="sample truncated by throttling",
            ),
        ],
        incomplete=True,
        retry_requested=True,
        reason="schema break with an incomplete sample",
    )
    assert DetectVerdict.model_validate(verdict.model_dump()) == verdict


def test_the_latest_settled_event_is_the_terminal_most_row() -> None:
    """A gate cycle writes two rows, so a cycle's outcome is the last settled one, not the last."""
    events = [
        HealEvent(collector_id=STUB_COLLECTOR_ID, status=HealStatus.DONE, created_at=FIXED_NOW),
        HealEvent(
            collector_id=STUB_COLLECTOR_ID, status=HealStatus.REJECTED, created_at=FIXED_NOW
        ),
        HealEvent(
            collector_id=STUB_COLLECTOR_ID,
            status=HealStatus.AWAITING_APPROVAL,
            created_at=FIXED_NOW,
        ),
    ]

    settled = latest_settled(events)

    assert settled is not None
    assert settled.status is HealStatus.REJECTED


def test_a_heal_still_at_the_gate_has_settled_nothing() -> None:
    """`None` distinguishes "proposed" from "kept" — the facade and the benchmark both need it."""
    pending = HealEvent(
        collector_id=STUB_COLLECTOR_ID,
        status=HealStatus.AWAITING_APPROVAL,
        created_at=FIXED_NOW,
    )

    assert latest_settled([pending]) is None
    assert latest_settled([]) is None
