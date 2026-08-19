"""Golden diff plus the non-regression check.

A heal that fixes the new layout by breaking the old one is an overfit, not a repair, so
the healed collector is re-run against `old_layout_url` and diffed too. That second pass
is the measurement nobody else takes.

Both passes are scored against the *same* golden records, because the mutation changed
the page's markup and not the records on it. So the old layout regressing means the heal
stopped recovering data it used to recover — measured against the records, never against
how well the new layout happened to score. Comparing the two passes to each other would
call a heal that broke both layouts a success, since neither would be the worse.

A sample the target refused is not a measurement. Rather than publish an accuracy taken
from a truncated run, or convict a heal of overfitting on evidence that was never
gathered, such a pass raises: the caller retries, which is the loop's decision to make.
"""

from collections.abc import Sequence
from typing import Any

from bdheal.errors import VerificationIncompleteError
from bdheal.models import CollectorSpec, RunResult, VerifyReport
from bdheal.ports import Clock, StudioClient
from bdheal.vocabulary import UNTRUSTWORTHY_SAMPLE_CODES

# How much of the golden data the old layout must still yield for the heal to count as
# non-regressive. All of it: a floor below 1.0 is a number nobody can defend, and it would
# let a heal quietly drop one field in ten and still be published as having regressed
# nothing.
NON_REGRESSION_FLOOR = 1.0

# The codes that mean the sample cannot be trusted rather than that the collector failed.
# A refusal never reached the extractor; an ambiguous code might have been either side's
# fault, and one run cannot tell — Bright Data's own reference says so. Codes it
# attributes to the scraper itself are deliberately absent: a parser that fails on a page
# it used to handle *is* the regression this pass exists to find.
UNVERIFIABLE_CODES: frozenset[str] = UNTRUSTWORTHY_SAMPLE_CODES

HEALED_LAYOUT = "healed layout"
OLD_LAYOUT = "old layout"

# Distinguishes a field the row never carried from one it carried as null. `None` cannot:
# a missing key would then score as a correctly recovered empty value.
_ABSENT = object()


def field_accuracy(rows: Sequence[dict[str, Any]], golden: Sequence[dict[str, Any]]) -> float:
    """Fraction of golden fields recovered exactly, in 0.0..1.0. Missing rows count as misses.

    Correct means equal to the golden value, with no normalisation: this number is
    published, and every looser rule inflates it by an amount nobody can audit.
    """
    total = sum(len(record) for record in golden)
    if not total:
        raise ValueError("field accuracy needs at least one golden field to score against")
    recovered = sum(
        _recovered(record, rows[index] if index < len(rows) else {})
        for index, record in enumerate(golden)
    )
    return recovered / total


def verify(
    spec: CollectorSpec,
    golden: Sequence[dict[str, Any]],
    old_layout_url: str,
    studio: StudioClient,
    clock: Clock,
    *,
    attempts: int = 1,
) -> VerifyReport:
    """Score the healed collector against golden records, then against the old layout."""
    started = clock.monotonic()
    healed = _score(spec, spec.anchor_urls, HEALED_LAYOUT, golden, studio)
    old = _score(spec, [old_layout_url], OLD_LAYOUT, golden, studio)
    return VerifyReport(
        field_accuracy=healed,
        non_regression_passed=old >= NON_REGRESSION_FLOOR,
        attempts=attempts,
        elapsed_s=clock.monotonic() - started,
    )


def _score(
    spec: CollectorSpec,
    urls: Sequence[str],
    layout: str,
    golden: Sequence[dict[str, Any]],
    studio: StudioClient,
) -> float:
    """Run one layout through the port and score what came back against the golden records."""
    result = studio.run(spec, urls)
    _refuse_incomplete(result, layout)
    return field_accuracy(result.rows, golden)


def _refuse_incomplete(result: RunResult, layout: str) -> None:
    """Stop before scoring a sample the target would not serve whole.

    Named codes only, never the payload or the URL, so nothing caller-supplied reaches the
    message (G6).
    """
    refused = sorted(code for code in result.error_codes if code in UNVERIFIABLE_CODES)
    if refused:
        raise VerificationIncompleteError(
            f"the {layout} sample is incomplete: the target returned {', '.join(refused)}, "
            "so retry the run rather than reading this as a regression"
        )


def _recovered(record: dict[str, Any], row: dict[str, Any]) -> int:
    """How many of one golden record's fields the scraped row carries with the same value."""
    return sum(1 for field, value in record.items() if row.get(field, _ABSENT) == value)
