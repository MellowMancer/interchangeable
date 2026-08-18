"""The four break detectors, and the throttling policy that keeps them honest.

Nothing in this module names a problem domain: it compares this run against the stored
baseline and against the caller's schema, and that is all it knows. History is read
through the `HealStore` port only — detect never touches a database or a network.

Policy (resolved Q3): any `rate_limit` row makes the sample incomplete, so the
volume-based detectors — zero-rows-vs-prior and null-rate spike — record
`INCONCLUSIVE` and a retry is requested. A row that *did* return and failed the caller's
schema is still valid break evidence: malformed is malformed regardless of throttling.
"""

from datetime import datetime

from bdheal.models import Baseline, CollectorSpec, DetectVerdict, RunResult
from bdheal.ports import HealStore

RATE_LIMIT_CODE = "rate_limit"


def detect(
    spec: CollectorSpec,
    result: RunResult,
    store: HealStore,
    page_html: str | None = None,
) -> DetectVerdict:
    """Judge one run against its baseline. `page_html` enables the skeleton signal.

    A collector with no stored baseline is never broken — there is nothing to compare
    against, and a first run reporting a break would be noise.
    """
    raise NotImplementedError


def null_rates(rows: list[dict], fields: list[str]) -> dict[str, float]:
    """Fraction of rows where each field is null or blank. Empty input gives 0.0 per field."""
    raise NotImplementedError


def capture_baseline(
    result: RunResult,
    fields: list[str],
    captured_at: datetime,
    skeleton_hash: str | None = None,
) -> Baseline:
    """The known-good shape of a healthy run, ready to store."""
    raise NotImplementedError
