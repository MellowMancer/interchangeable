"""The four detectors and the throttling policy, ordered by what each costs when wrong.

The load-bearing tests here are the throttling ones. A run that came back entirely
rate-limited has zero usable rows, which on the wire is indistinguishable from a total
break — and healing against a truncated sample is the expensive failure mode: it burns
credits and can promote a collector fitted to data that was never there. So a wholly
throttled run must read as `broken=False`, and a partially throttled one must abstain on
volume while still reporting a malformed row, because malformed is malformed regardless
of what happened to its siblings (resolved decision Q3).

The rule those tests are really pinning is one line: **extraction problems justify a
heal; target-side problems justify a retry; neither justifies silence.** Criterion (h)
exists because the first draft applied it to the literal code `rate_limit` alone, so a
run half-refused with `blocked` came back completely silent — the exact failure the
package exists to prevent, in the module whose job is preventing it.

Every fixture is generic. A term from any problem domain appearing in `detect.py` is a
defect, and `test_detect_names_no_problem_domain` is where that is caught rather than
noticed.
"""

import ast
import inspect

import pytest
from conftest import FIXED_NOW, STUB_COLLECTOR_ID, SampleRow, baseline, run_result

from bdheal import detect as detect_module
from bdheal.detect import (
    NULL_RATE_SPIKE,
    THROTTLED_LABEL,
    capture_baseline,
    detect,
    null_rates,
)
from bdheal.models import Baseline, CollectorSpec, DetectVerdict, RowError, RunResult
from bdheal.ports import HealStore
from bdheal.skeleton import skeleton_hash
from bdheal.studio import _distinct_codes
from bdheal.vocabulary import COLLECTOR_FAULT_CODES, THROTTLE_CODES, SignalKind, SignalOutcome

DETECT_SOURCE = inspect.getsource(detect_module)

FIELDS = list(SampleRow.model_fields)
HEALTHY_NULL_RATES = dict.fromkeys(FIELDS, 0.0)

BLOCKED_CODE = "blocked"
THROTTLED_CODE = "rate_limit"

BASELINE_HTML = '<ul class="rows"><li class="row"><a class="link"></a></li></ul>'
REBUILT_HTML = '<ul class="rows"><li class="record"><a class="link"></a></li></ul>'

def _row(index: int, *, published: str | None = "2026-01-01") -> dict[str, str | None]:
    """One well-formed row of the generic sample schema."""
    return {
        "title": f"item {index}",
        "url": f"https://example.test/{index}",
        "published": published,
    }


def _throttled(index: int) -> RowError:
    """A target-side throttle: no row came back, and the reason is not our schema."""
    return RowError(index=index, message="too many requests", error_code=THROTTLED_CODE)


def _malformed(index: int) -> RowError:
    """A row that *did* come back and failed the caller's schema."""
    return RowError(
        index=index,
        message="row does not match the collector's row schema",
        field_errors={"title": "Field required"},
    )


def _refused(index: int, code: str = BLOCKED_CODE) -> RowError:
    """A target-side refusal that is not throttling: blocked, captcha'd, navigation failed."""
    return RowError(index=index, message="the target refused the request", error_code=code)


def _not_an_object(index: int) -> RowError:
    """What `studio._row` yields for a non-dict item: no field errors, and no error code."""
    return RowError(index=index, message="expected an object, got str")


def _result(
    rows: list[dict] | None = None,
    errors: list[RowError] | None = None,
) -> RunResult:
    """A run shaped as the studio adapter builds one, `error_codes` and all."""
    return run_result(rows=rows or [], errors=errors or [])


def _store_baseline(
    store: HealStore,
    *,
    row_count: int = 3,
    rates: dict[str, float] | None = None,
    page_hash: str | None = None,
) -> None:
    """Give the collector a prior run to be compared against."""
    store.save_baseline(
        baseline(
            row_count=row_count,
            null_rates=HEALTHY_NULL_RATES if rates is None else rates,
            skeleton_hash=page_hash,
        )
    )


def _outcomes(verdict: DetectVerdict) -> dict[SignalKind, SignalOutcome]:
    """Every signal the verdict carries, keyed by kind — so exclusivity is assertable."""
    return {signal.kind: signal.outcome for signal in verdict.signals}


def test_a_schema_validation_failure_is_a_break(spec: CollectorSpec, store: HealStore) -> None:
    """A row the caller's schema rejects is break evidence, and only the schema signal fires."""
    _store_baseline(store)
    verdict = detect(spec, _result([_row(0), _row(1)], [_malformed(2)]), store)

    assert verdict.broken is True
    assert _outcomes(verdict) == {SignalKind.SCHEMA: SignalOutcome.FIRED}


@pytest.mark.parametrize("code", sorted(COLLECTOR_FAULT_CODES))
def test_a_collector_fault_code_is_break_evidence(
    code: str, spec: CollectorSpec, store: HealStore
) -> None:
    """A code Bright Data attributes to the scraper is the scraper failing, so it justifies a heal.

    `parse_error` was observed 19 times in one real payload — the price parser failing on
    pages that had loaded perfectly well. A retry would reproduce it exactly.

    Parametrised over the whole class because the live rule is its *complement*: `detect`
    asks whether a code is a refusal or ambiguous, so a code moved into either of those
    sets changes this verdict with nothing in the module to say it had.
    """
    _store_baseline(store, row_count=10)
    errors = [
        RowError(index=0, message="Parse error: value must be finite number", error_code=code),
    ]

    verdict = detect(spec, _result([_row(1)], errors), store)

    assert verdict.broken is True
    assert verdict.incomplete is False, "the scraper's own fault does not excuse the sample"
    assert verdict.retry_requested is False, "retrying reproduces a parse error exactly"
    assert {signal.kind for signal in verdict.fired} == {SignalKind.SCHEMA}


def test_an_ambiguous_code_is_reported_rather_than_judged(
    spec: CollectorSpec, store: HealStore
) -> None:
    """`dead_page` may be the target's fault or the collector's, and one run cannot tell.

    Bright Data documents it as a target issue ("the page does not exist"). But 980 of
    them in one real payload came from the collector resolving relative links against the
    site root instead of the current page, so every link off page 2 onward 404'd. Detect
    therefore retries rather than healing, and names the code so the facade can escalate
    if it survives the retry.
    """
    _store_baseline(store, row_count=10)
    errors = [
        RowError(index=0, message="The navigation resulted in a dead page (404 status code)",
                 error_code="dead_page"),
    ]

    verdict = detect(spec, _result([_row(1)], errors), store)

    assert verdict.incomplete is True
    assert verdict.retry_requested is True
    assert verdict.ambiguous_codes == ("dead_page",)
    assert SignalKind.SCHEMA not in {signal.kind for signal in verdict.fired}


def test_an_unknown_code_defaults_to_heal_able(spec: CollectorSpec, store: HealStore) -> None:
    """A code nobody has seen is treated as the collector's fault, not the target's.

    A wasted heal is caught by verification; a wrong retry is silent and permanent, so the
    safer default is the one that still produces an answer.
    """
    _store_baseline(store, row_count=10)
    errors = [RowError(index=0, message="something new", error_code="never_seen_before")]

    verdict = detect(spec, _result([_row(1)], errors), store)

    assert verdict.broken is True
    assert verdict.retry_requested is False


def test_a_row_that_is_not_an_object_is_break_evidence(
    spec: CollectorSpec, store: HealStore
) -> None:
    """No field errors and no error code: the target answered, and the extractor did not.

    A collector that returned objects and now returns strings is broken, and a heal is
    exactly the remedy for it — so this cannot be the one failure shape detect ignores.
    """
    _store_baseline(store)
    verdict = detect(spec, _result([_row(0), _row(1)], [_not_an_object(2)]), store)

    assert verdict.broken is True
    assert _outcomes(verdict) == {SignalKind.SCHEMA: SignalOutcome.FIRED}


def test_zero_rows_after_a_productive_prior_run_is_a_break(
    spec: CollectorSpec, store: HealStore
) -> None:
    """Silence where the baseline holds rows is the plainest break there is."""
    _store_baseline(store, row_count=3)
    verdict = detect(spec, _result(), store)

    assert verdict.broken is True
    assert _outcomes(verdict) == {SignalKind.ZERO_ROWS: SignalOutcome.FIRED}


def test_a_rebuilt_page_moves_the_skeleton_hash_and_is_a_break(
    spec: CollectorSpec, store: HealStore
) -> None:
    """A tag-and-class tree that no longer hashes to the baseline is a structural break."""
    _store_baseline(store, page_hash=skeleton_hash(BASELINE_HTML))
    verdict = detect(spec, _result([_row(0), _row(1), _row(2)]), store, page_html=REBUILT_HTML)

    assert verdict.broken is True
    assert _outcomes(verdict) == {SignalKind.SKELETON: SignalOutcome.FIRED}


def test_the_skeleton_signal_is_skipped_when_no_html_is_supplied(
    spec: CollectorSpec, store: HealStore
) -> None:
    """Detect keeps only the store port, so an absent page means an unasked question."""
    _store_baseline(store, page_hash=skeleton_hash(BASELINE_HTML))
    verdict = detect(spec, _result([_row(0), _row(1), _row(2)]), store)

    assert verdict.broken is False
    assert SignalKind.SKELETON not in _outcomes(verdict)


def test_a_field_going_null_across_the_sample_is_a_break(
    spec: CollectorSpec, store: HealStore
) -> None:
    """A field the baseline always carried and this run never does has stopped extracting."""
    _store_baseline(store)
    rows = [_row(index, published=None) for index in range(3)]
    verdict = detect(spec, _result(rows), store)

    assert verdict.broken is True
    assert _outcomes(verdict) == {SignalKind.NULL_RATE: SignalOutcome.FIRED}


def test_a_null_rate_rise_below_the_threshold_is_not_a_break(
    spec: CollectorSpec, store: HealStore
) -> None:
    """One blank field in four rows is a page, not a break. False positives burn credits."""
    assert 0.25 < NULL_RATE_SPIKE

    _store_baseline(store, row_count=4)
    rows = [_row(0, published=None), _row(1), _row(2), _row(3)]
    verdict = detect(spec, _result(rows), store)

    assert verdict.broken is False
    assert verdict.signals == []


def test_a_wholly_throttled_run_is_not_broken(spec: CollectorSpec, store: HealStore) -> None:
    """The highest-value test: zero usable rows because of throttling is not a break.

    On the wire this is identical to a total break — the baseline holds rows and this run
    returned none — so nothing but the error codes separates "the site is rate limiting
    us" from "the site was rebuilt". Reading it as broken would heal against no data.
    """
    _store_baseline(store, row_count=3)
    verdict = detect(spec, _result(errors=[_throttled(index) for index in range(4)]), store)

    assert verdict.broken is False
    assert verdict.incomplete is True
    assert verdict.retry_requested is True
    assert THROTTLED_CODE in (verdict.reason or "")
    assert "throttl" in (verdict.reason or "")
    assert SignalOutcome.FIRED not in _outcomes(verdict).values()
    assert _outcomes(verdict) == {
        SignalKind.ZERO_ROWS: SignalOutcome.INCONCLUSIVE,
        SignalKind.NULL_RATE: SignalOutcome.INCONCLUSIVE,
    }


def test_a_partial_throttle_suppresses_volume_signals_but_keeps_schema_evidence(
    spec: CollectorSpec, store: HealStore
) -> None:
    """The worked case: 10 inputs, 3 throttled, 7 returned, 2 of those malformed.

    The sample is incomplete, so volume abstains; but two rows that *did* come back are
    malformed, and that is true whatever happened to their siblings.
    """
    _store_baseline(store, row_count=10)
    rows = [_row(index) for index in range(5)]
    errors = [_throttled(index) for index in range(3)] + [_malformed(index) for index in (8, 9)]
    verdict = detect(spec, _result(rows, errors), store)

    assert _outcomes(verdict) == {
        SignalKind.SCHEMA: SignalOutcome.FIRED,
        SignalKind.ZERO_ROWS: SignalOutcome.INCONCLUSIVE,
        SignalKind.NULL_RATE: SignalOutcome.INCONCLUSIVE,
    }
    assert verdict.broken is True
    assert verdict.incomplete is True
    assert verdict.retry_requested is True


def test_a_partial_throttle_never_proposes_a_heal_on_volume_grounds(
    spec: CollectorSpec, store: HealStore
) -> None:
    """Same incomplete sample without the malformed rows: nothing to heal, only to retry."""
    _store_baseline(store, row_count=10)
    errors = [_throttled(index) for index in range(3)]
    verdict = detect(spec, _result([_row(0)], errors), store)

    assert verdict.broken is False
    assert verdict.retry_requested is True


def test_a_blocked_target_is_reported_rather_than_passed_over_in_silence(
    spec: CollectorSpec, store: HealStore
) -> None:
    """The demonstrated false negative, verbatim: 10 expected rows, 5 of them `blocked`.

    Half the run failed on the target side and the first draft said nothing at all — not
    broken, not throttled, no signals, no retry. Bright Data returns blocking, captcha,
    navigation and timeout codes in ordinary operation, so a policy keyed to the literal
    string `rate_limit` is silence waiting to happen.
    """
    _store_baseline(store, row_count=10)
    rows = [_row(index) for index in range(5)]
    verdict = detect(spec, _result(rows, [_refused(index) for index in range(5, 10)]), store)

    assert verdict.broken is False
    assert verdict.incomplete is True
    assert verdict.retry_requested is True
    assert verdict.signals != []
    assert BLOCKED_CODE in (verdict.reason or "")
    assert _outcomes(verdict) == {
        SignalKind.ZERO_ROWS: SignalOutcome.INCONCLUSIVE,
        SignalKind.NULL_RATE: SignalOutcome.INCONCLUSIVE,
    }


def test_a_wholly_blocked_run_proposes_no_heal(spec: CollectorSpec, store: HealStore) -> None:
    """Zero usable rows because the target refused every one of them. Healing fixes nothing."""
    _store_baseline(store, row_count=10)
    verdict = detect(spec, _result(errors=[_refused(index) for index in range(10)]), store)

    assert verdict.broken is False
    assert verdict.retry_requested is True
    assert SignalOutcome.FIRED not in _outcomes(verdict).values()


def test_every_observed_error_code_is_named_in_the_reason(
    spec: CollectorSpec, store: HealStore
) -> None:
    """`blocked` and `rate_limit` are different operational problems and read differently."""
    _store_baseline(store, row_count=10)
    errors = [_refused(index) for index in range(5)] + [_throttled(index) for index in range(5, 10)]
    verdict = detect(spec, _result(errors=errors), store)
    reason = verdict.reason or ""

    assert BLOCKED_CODE in reason
    assert THROTTLED_CODE in reason


def test_a_target_side_failure_is_never_read_as_an_extraction_fault(
    spec: CollectorSpec, store: HealStore
) -> None:
    """The whole principle in one assertion: a code means retry, never heal."""
    _store_baseline(store, row_count=10)
    verdict = detect(spec, _result(errors=[_refused(index) for index in range(10)]), store)

    assert SignalKind.SCHEMA not in _outcomes(verdict)
    assert verdict.broken is False


def test_a_first_ever_run_with_no_baseline_is_not_broken(
    spec: CollectorSpec, store: HealStore
) -> None:
    """Nothing stored means nothing to compare against — not a break, and not a signal."""
    verdict = detect(spec, _result(), store)

    assert verdict.broken is False
    assert verdict.signals == []
    assert verdict.retry_requested is False


def test_a_healthy_run_matching_its_baseline_reports_nothing(
    spec: CollectorSpec, store: HealStore
) -> None:
    """The quiet path: same shape, same page, no complaint."""
    _store_baseline(store, page_hash=skeleton_hash(BASELINE_HTML))
    rows = [_row(index) for index in range(3)]
    verdict = detect(spec, _result(rows), store, page_html=BASELINE_HTML)

    assert verdict == DetectVerdict(broken=False, signals=[], incomplete=False)
    assert verdict.reason is None


def test_every_signal_explains_itself(spec: CollectorSpec, store: HealStore) -> None:
    """A signal with no detail is a verdict nobody can act on."""
    _store_baseline(store, page_hash=skeleton_hash(BASELINE_HTML))
    errors = [_throttled(0), _malformed(1)]
    verdict = detect(spec, _result([], errors), store, page_html=REBUILT_HTML)

    assert len(verdict.signals) == len(SignalKind)
    assert all(signal.detail.strip() for signal in verdict.signals)


def test_detect_reads_history_through_the_store_port_only() -> None:
    """The one seam detect is allowed: no studio client, no clock, no database."""
    imported = {
        alias.name
        for node in ast.walk(ast.parse(DETECT_SOURCE))
        if isinstance(node, ast.ImportFrom) and node.module == "bdheal.ports"
        for alias in node.names
    }

    assert imported == {"HealStore"}


def test_null_rates_of_an_empty_sample_are_zero() -> None:
    """No rows means no evidence of nullness — never a division by zero, never a spike."""
    assert null_rates([], FIELDS) == HEALTHY_NULL_RATES


def test_null_rates_count_blank_strings_as_null() -> None:
    """A field extracted as an empty string stopped extracting just as surely as a `None`."""
    rows = [_row(0, published=None), _row(1, published="   "), _row(2), _row(3)]

    assert null_rates(rows, FIELDS) == {"title": 0.0, "url": 0.0, "published": 0.5}


def test_capture_baseline_takes_the_shape_of_a_healthy_run() -> None:
    """What gets stored is row count, per-field null rates and the page's structural hash."""
    result = _result([_row(0), _row(1, published=None)])

    baseline = capture_baseline(result, FIELDS, FIXED_NOW, skeleton_hash(BASELINE_HTML))

    assert baseline == Baseline(
        collector_id=STUB_COLLECTOR_ID,
        captured_at=FIXED_NOW,
        row_count=2,
        null_rates={"title": 0.0, "url": 0.0, "published": 0.5},
        skeleton_hash=skeleton_hash(BASELINE_HTML),
    )


@pytest.mark.parametrize("code", sorted(THROTTLE_CODES))
def test_a_throttled_sample_is_named_as_throttling(
    code: str, spec: CollectorSpec, store: HealStore
) -> None:
    """Throttling is the one refusal that clears up on its own, so the reason says so.

    Bright Data documents two rate-limit codes and a third was observed live, and only
    the observed one was recognised — so a run the vendor's own documented code throttled
    read as a plain "incomplete sample" and told the operator nothing about waiting.
    """
    _store_baseline(store, row_count=10)
    errors = [_refused(index, code) for index in range(3)]

    verdict = detect(spec, _result(errors=errors), store)

    assert THROTTLED_LABEL in (verdict.reason or "")


def test_the_module_docstring_states_the_rule_the_module_implements() -> None:
    """The stated rule and the running rule have to be the same rule.

    The docstring claimed that *any* row carrying an `error_code` makes the sample
    incomplete. `_is_refusal` does not agree: a collector-fault code leaves the sample
    whole, and a `parse_error` row carries a code and fires the schema signal. A stated
    rule the code does not follow is worse than no statement, because it is the one the
    next reader will implement against.
    """
    doc = detect_module.__doc__ or ""

    assert "any row carrying an `error_code`" not in doc
    assert "target-side" in doc
    assert "ambiguous" in doc
