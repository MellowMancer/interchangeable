"""Verification, and the overfit check that is the point of the package.

Two things carry the weight here. `field_accuracy` feeds a published metric, so every
assertion is an exact value — a "close enough" comparison on a number that goes in a
benchmark table is how an inflated claim survives review. And the non-regression pass has
to *catch* an overfit: a heal that scores perfectly on the page it was shown and silently
stops working on every other page the collector serves is the failure mode nobody else
measures, so the tests here lead with that case rather than with the happy one.

The third thing, less obvious: a target that refuses the old-layout sample is not evidence
of an overfit. Reporting `non_regression_passed=False` for a throttled check would publish
a false accusation, so an unverifiable pass raises instead of scoring.
"""

from collections.abc import Sequence

import pytest
from conftest import FixedClock, StubStudioClient, row_error, run_result

from bdheal.errors import VerificationIncompleteError
from bdheal.models import CollectorSpec, RunResult
from bdheal.verify import field_accuracy, verify

OLD_LAYOUT_URL = "https://example.test/old"

# Four fields, so "three of four" is expressible as an exact quarter.
GOLDEN_ROW = {
    "title": "first",
    "url": "https://example.test/1",
    "published": "2026-01-01",
    "author": "someone",
}

GOLDEN = [
    {"title": "first", "url": "https://example.test/1", "published": "2026-01-01"},
    {"title": "second", "url": "https://example.test/2", "published": "2026-01-02"},
]

# The overfit: the new layout is recovered whole, the old one loses the field the heal
# re-anchored away from.
BROKEN_ON_OLD = [row | {"title": ""} for row in GOLDEN]

# How long one collector run takes, so `elapsed_s` is an exact multiple rather than a
# wall-clock reading that differs on every machine.
RUN_SECONDS = 4.0


def studio_returning(clock: FixedClock, *results: RunResult) -> StubStudioClient:
    """The stub queued with one result per run, its clock advancing as a real run would.

    The advance lives here rather than in `verify` because time passing is a property of
    the run, not of the measurement — and criterion (d) is that the value comes from the
    injected clock, which is only demonstrated if something other than `verify` moves it.
    """
    studio = StubStudioClient(clock)
    studio.run_results = list(results)
    queued = studio.run

    def run(spec: CollectorSpec, urls: Sequence[str]) -> RunResult:
        clock.advance(RUN_SECONDS)
        return queued(spec, urls)

    studio.run = run
    return studio


def test_three_correct_fields_of_four_is_exactly_three_quarters() -> None:
    """(a) The published number is an exact fraction, not a comparison with a tolerance."""
    scraped = GOLDEN_ROW | {"published": "01/01/2026"}
    assert field_accuracy([scraped], [GOLDEN_ROW]) == 0.75


def test_a_value_that_differs_only_in_whitespace_is_a_miss() -> None:
    """Correct means equal to the golden value. Any looser rule inflates the metric."""
    assert field_accuracy([{"title": " first "}], [{"title": "first"}]) == 0.0


def test_a_row_that_never_came_back_counts_every_golden_field_as_a_miss() -> None:
    """Half the records recovered is half the fields recovered, not full marks on what returned."""
    assert field_accuracy([GOLDEN[0]], GOLDEN) == 0.5


def test_a_field_the_row_never_carried_is_a_miss_even_when_the_golden_is_null() -> None:
    """An absent key is not a recovered null: nothing was extracted, so nothing is correct."""
    assert field_accuracy([{"title": "first"}], [{"title": "first", "published": None}]) == 0.5


def test_a_null_golden_field_recovered_as_null_is_correct() -> None:
    """A field the page legitimately does not carry is recovered by coming back empty."""
    row = {"title": "first", "published": None}
    assert field_accuracy([row], [row]) == 1.0


def test_scoring_against_no_golden_fields_at_all_is_refused() -> None:
    """A vacuous 1.0 is the one result this metric must never publish."""
    with pytest.raises(ValueError, match="golden"):
        field_accuracy([GOLDEN[0]], [])


def test_a_heal_that_fixes_the_new_layout_and_breaks_the_old_fails_non_regression(
    spec: CollectorSpec,
) -> None:
    """(b) The whole feature: a perfect score on the healed page is not a repair."""
    clock = FixedClock()
    studio = studio_returning(clock, run_result(rows=GOLDEN), run_result(rows=BROKEN_ON_OLD))
    report = verify(spec, GOLDEN, OLD_LAYOUT_URL, studio, clock)
    assert report.field_accuracy == 1.0
    assert report.non_regression_passed is False


def test_a_heal_that_satisfies_both_layouts_passes_non_regression(spec: CollectorSpec) -> None:
    """(b) The other half: recovering both layouts whole is what passing means."""
    clock = FixedClock()
    studio = studio_returning(clock, run_result(rows=GOLDEN), run_result(rows=GOLDEN))
    report = verify(spec, GOLDEN, OLD_LAYOUT_URL, studio, clock)
    assert report.field_accuracy == 1.0
    assert report.non_regression_passed is True


def test_the_non_regression_pass_runs_the_old_layout_url_through_the_port(
    spec: CollectorSpec,
) -> None:
    """(c) The old layout is re-run through `StudioClient`, in that order, and nowhere else."""
    clock = FixedClock()
    studio = studio_returning(clock, run_result(rows=GOLDEN), run_result(rows=GOLDEN))
    verify(spec, GOLDEN, OLD_LAYOUT_URL, studio, clock)
    assert studio.urls_run == [*spec.anchor_urls, OLD_LAYOUT_URL]
    assert studio.calls[-1] == ("run", spec.collector_id, OLD_LAYOUT_URL)


def test_the_report_carries_the_attempts_and_an_elapsed_time_from_the_injected_clock(
    spec: CollectorSpec,
) -> None:
    """(d) Two runs at a known cost each: the duration is an exact number, never wall-clock."""
    clock = FixedClock()
    studio = studio_returning(clock, run_result(rows=GOLDEN), run_result(rows=GOLDEN))
    report = verify(spec, GOLDEN, OLD_LAYOUT_URL, studio, clock, attempts=3)
    assert report.attempts == 3
    assert report.elapsed_s == 2 * RUN_SECONDS


@pytest.mark.parametrize("code", ["global_rate_limit", "blocked", "dead_page"])
def test_an_old_layout_sample_the_target_refused_is_not_reported_as_an_overfit(
    spec: CollectorSpec, code: str
) -> None:
    """A refusal means we could not check, which is not the same as finding a regression.

    `dead_page` is in the list because Bright Data calls it ambiguous: it may be the
    target's fault or the collector's, and one run cannot tell. Deciding it is the
    collector's here would convict on evidence that does not exist — the escalation is the
    loop's job, not the measurement's.
    """
    clock = FixedClock()
    refused = run_result(errors=[row_error(0, error_code=code)])
    studio = studio_returning(clock, run_result(rows=GOLDEN), refused)
    with pytest.raises(VerificationIncompleteError) as caught:
        verify(spec, GOLDEN, OLD_LAYOUT_URL, studio, clock)
    assert code in str(caught.value)


def test_a_healed_sample_the_target_refused_is_not_scored_as_a_field_accuracy(
    spec: CollectorSpec,
) -> None:
    """The same protection on the way in: a truncated sample cannot produce an accuracy."""
    clock = FixedClock()
    refused = run_result(errors=[row_error(0, error_code="bucket_rate_limit")])
    studio = studio_returning(clock, refused, run_result(rows=GOLDEN))
    with pytest.raises(VerificationIncompleteError):
        verify(spec, GOLDEN, OLD_LAYOUT_URL, studio, clock)


def test_a_collector_fault_on_the_old_layout_is_a_regression_not_an_excuse(
    spec: CollectorSpec,
) -> None:
    """The collector's own parser failing on a page it used to handle is exactly the overfit."""
    clock = FixedClock()
    broke = run_result(rows=[GOLDEN[0]], errors=[row_error(1, error_code="parse_error")])
    studio = studio_returning(clock, run_result(rows=GOLDEN), broke)
    report = verify(spec, GOLDEN, OLD_LAYOUT_URL, studio, clock)
    assert report.non_regression_passed is False
