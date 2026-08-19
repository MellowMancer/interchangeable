"""The five published numbers and the coverage matrix.

Every metric is asserted to an exact value over a canned set of cases, because these are
the numbers the project publishes: "close enough" is how a benchmark quietly reports
something nobody measured.

Three obligations recorded upstream are tested here rather than trusted:
the non-regression rate covers six of the nine mutation classes and says so *in the
result* (F9); a class no detector caught is a gap and never a heal failure (F11(e), Q2);
and both promotion floors travel with the numbers, or the numbers are not reproducible
(F9, F10).
"""

import pytest
from conftest import bench_case

from bdheal.bench.metrics import (
    EXCLUDED_FROM_NON_REGRESSION,
    METHODOLOGY,
    PUBLISHED_FIELD_ACCURACY_FLOOR,
    PUBLISHED_NON_REGRESSION_FLOOR,
    Metrics,
    coverage,
    metrics,
)
from bdheal.healer import NO_FIELDS_RECOVERED
from bdheal.models import BenchCase
from bdheal.verify import NON_REGRESSION_FLOOR
from bdheal.vocabulary import MutationClass, SignalKind

# The disclosure `GOAL.md` fixes word for word, plus the coverage it resolves to. Quoted
# here rather than imported so a silent edit to the published wording fails a test.
EXPECTED_NOTE = (
    "date_format, link_label and url_pattern are excluded from the non-regression rate: "
    "their mutation changes the page text, so one golden set cannot score both layouts. "
    "Scoring them would report a heal that broke nothing as a regression. "
    "The rate therefore covers 6 of 9 mutation classes."
)

SKELETON = frozenset({SignalKind.SKELETON})


def scored_cases() -> list[BenchCase]:
    """Five attempted cases and one nothing detected — the canned set every metric is read off.

    Chosen so each metric lands on an exactly representable value, and so the excluded
    `date_format` case scores badly enough that including it would visibly move the
    non-regression rate.
    """
    return [
        bench_case(
            case_id="case_1",
            mutation=MutationClass.TABLE_TO_DIV,
            healed=True,
            field_accuracy=1.0,
            non_regression_passed=True,
            attempts=1,
            elapsed_s=10.0,
        ),
        bench_case(
            case_id="case_2",
            mutation=MutationClass.CLASS_RENAME,
            healed=True,
            field_accuracy=0.5,
            non_regression_passed=True,
            attempts=3,
            elapsed_s=30.0,
        ),
        bench_case(
            case_id="case_3",
            mutation=MutationClass.WRAPPER_NESTING,
            healed=False,
            field_accuracy=0.25,
            non_regression_passed=False,
            attempts=1,
            elapsed_s=8.0,
        ),
        bench_case(
            case_id="case_4",
            mutation=MutationClass.PAGINATION,
            healed=True,
            field_accuracy=1.0,
            non_regression_passed=True,
            attempts=2,
            elapsed_s=20.0,
        ),
        bench_case(
            case_id="case_5",
            mutation=MutationClass.DATE_FORMAT,
            expected_signals=frozenset({SignalKind.SCHEMA}),
            caught_by=SignalKind.SCHEMA,
            healed=True,
            field_accuracy=0.25,
            non_regression_passed=False,
            attempts=1,
            elapsed_s=4.0,
        ),
        undetected_case(),
    ]


def undetected_case() -> BenchCase:
    """The case no detector saw: nothing fired, nothing was attempted, nothing was scored."""
    return bench_case(
        case_id="case_6",
        mutation=MutationClass.LINK_LABEL,
        expected_signals=frozenset(),
        caught_by=None,
        healed=False,
        field_accuracy=None,
        non_regression_passed=None,
        attempts=0,
        elapsed_s=1.0,
    )


def test_heal_rate_is_healed_over_attempted() -> None:
    """(a) Four of the five cases a heal was attempted on were kept."""
    assert metrics(scored_cases()).heal_rate == 0.8


def test_field_accuracy_is_the_mean_over_every_scored_case() -> None:
    """(a) One number, over exactly the cases a golden set actually scored."""
    assert metrics(scored_cases()).field_accuracy == 0.6


def test_non_regression_rate_covers_the_six_structural_classes_only() -> None:
    """(a) and F9: three of four structural cases held the old layout — 0.75, not 0.6."""
    assert metrics(scored_cases()).non_regression_rate == 0.75


def test_mean_time_to_heal_is_measured_over_the_cases_that_healed() -> None:
    """(a) Time-to-heal is what a heal took, so a case that never healed cannot contribute."""
    assert metrics(scored_cases()).mean_time_to_heal_s == 16.0


def test_mean_attempts_to_heal_is_measured_over_the_cases_that_healed() -> None:
    """(a) Loop passes per kept heal (F10), not heal calls and not verification passes."""
    assert metrics(scored_cases()).mean_attempts_to_heal == 1.75


def test_the_excluded_classes_are_named_in_the_result_itself() -> None:
    """F9: a disclosure that lives only in a docstring is not published."""
    assert metrics(scored_cases()).non_regression_note == EXPECTED_NOTE


def test_the_excluded_classes_are_the_three_whose_mutation_changes_the_text() -> None:
    """F9: one golden set cannot score both layouts for these, so they are not scored at all."""
    assert EXCLUDED_FROM_NON_REGRESSION == frozenset(
        {MutationClass.DATE_FORMAT, MutationClass.URL_PATTERN, MutationClass.LINK_LABEL}
    )


def test_both_promotion_floors_travel_with_the_numbers() -> None:
    """F9 and F10: without the floors the metrics are not reproducible."""
    assert metrics(scored_cases()).methodology == METHODOLOGY
    assert any("1.0" in line for line in METHODOLOGY)
    assert any("0.0" in line for line in METHODOLOGY)


def test_the_published_floors_are_the_floors_the_loop_actually_applies() -> None:
    """The published methodology is a claim about running code; drift here fabricates it.

    `metrics` is Entities and may not import a use case, so the two constants are restated
    there and pinned to their originals here instead.
    """
    assert PUBLISHED_NON_REGRESSION_FLOOR == NON_REGRESSION_FLOOR
    assert PUBLISHED_FIELD_ACCURACY_FLOOR == NO_FIELDS_RECOVERED


def test_an_undetected_case_is_not_counted_as_a_heal_failure() -> None:
    """(e) A gap is a finding. Counting it as a failed heal publishes a number nobody measured."""
    attempted = [case for case in scored_cases() if case.attempts]

    assert metrics(scored_cases()).heal_rate == metrics(attempted).heal_rate


def test_an_undetected_case_is_not_silently_dropped() -> None:
    """(e) It leaves the matrix as a gap, so the published result carries the finding."""
    rows = {row.mutation: row for row in coverage(scored_cases())}

    assert rows[MutationClass.LINK_LABEL].is_gap is True
    assert rows[MutationClass.LINK_LABEL].caught_by == frozenset()


def test_a_gap_the_generator_declared_is_reported_as_declared() -> None:
    """(e) `link_label` declares that nothing catches it, and nothing did — the claim held."""
    rows = {row.mutation: row for row in coverage(scored_cases())}

    assert rows[MutationClass.LINK_LABEL].as_declared is True


def test_a_class_caught_by_the_signal_it_declared_agrees_with_its_declaration() -> None:
    """(e) The matrix's ordinary row: declared `skeleton`, caught by `skeleton`."""
    rows = {row.mutation: row for row in coverage(scored_cases())}

    assert rows[MutationClass.TABLE_TO_DIV].caught_by == SKELETON
    assert rows[MutationClass.TABLE_TO_DIV].as_declared is True
    assert rows[MutationClass.TABLE_TO_DIV].is_gap is False


def test_a_class_caught_by_a_signal_it_did_not_declare_is_reported_as_a_disagreement() -> None:
    """(e) The declaration is a claim the benchmark checks, not a label it copies out."""
    cases = [
        bench_case(
            mutation=MutationClass.DATE_FORMAT,
            expected_signals=frozenset({SignalKind.SCHEMA}),
            caught_by=SignalKind.SKELETON,
        )
    ]

    row = next(r for r in coverage(cases) if r.mutation is MutationClass.DATE_FORMAT)

    assert row.caught_by == SKELETON
    assert row.as_declared is False
    assert row.is_gap is False


def test_an_escalated_case_is_not_reported_as_a_detection_gap() -> None:
    """F10: no `SignalKind` means the loop's retry caught it, not that nothing saw it."""
    cases = [bench_case(mutation=MutationClass.COLUMN_REORDER, caught_by=None, attempts=1)]

    row = next(r for r in coverage(cases) if r.mutation is MutationClass.COLUMN_REORDER)

    assert row.escalated == 1
    assert row.is_gap is False


def test_the_matrix_reports_every_class_including_the_ones_never_run() -> None:
    """(e) A partial run must not look complete.

    Omitting classes with no cases made "never attempted" indistinguishable from "absent
    from the table" — the reader had to count rows against `MutationClass` to notice. Every
    class gets a row; `cases` says whether it was measured, and a class with none is not a
    detection gap.
    """
    rows = {row.mutation: row for row in coverage(scored_cases() + [bench_case(case_id="case_7")])}

    assert set(rows) == set(MutationClass), "every class is represented"
    unrun = rows[MutationClass.COLUMN_REORDER]
    assert unrun.cases == 0
    assert unrun.is_gap is False, "never run is not a measured gap"


def test_a_metric_with_nothing_to_measure_is_reported_as_unmeasured() -> None:
    """A rate over zero cases is not zero; publishing 0.0 would fabricate the one number missing."""
    result = metrics([undetected_case()])

    assert result.heal_rate is None
    assert result.field_accuracy is None
    assert result.non_regression_rate is None
    assert result.mean_time_to_heal_s is None
    assert result.mean_attempts_to_heal is None


def test_metrics_over_no_cases_at_all_is_refused() -> None:
    """An empty benchmark has no result to publish, and saying so beats five silent `None`s."""
    with pytest.raises(ValueError, match="no cases"):
        metrics([])


def test_metrics_are_pure_data() -> None:
    """Entities: the result is a value, so the same cases always publish the same numbers."""
    assert metrics(scored_cases()) == metrics(scored_cases())
    assert isinstance(metrics(scored_cases()), Metrics)
