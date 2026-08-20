#!/usr/bin/env python3
"""Run the self-healing benchmark against the published fixture site.

The composition root: the one place that names concrete adapters, reads the environment
and spends money. `bdheal` ships none of this on purpose — nothing in the package reaches
the network unless something hands it a client that can.

    BDHEAL_BENCH=1 BDHEAL_PAGES_URL=https://<owner>.github.io/<repo> \
      uv run --package bdheal python fixtures/benchmark.py

**This costs real Bright Data credit and hours of wall-clock**: nine collectors built at
roughly two minutes each, then several collector runs per case. State is written per case,
so re-running with the same `--run-id` executes only what is left, and collector ids are
remembered so a second run does not pay to build them again.

## Why the row schema is the instrument

`date_format` and `url_pattern` are declared to trip the `schema` signal, and they only do
so because `updated` refuses a day-first date and `href` refuses a link that moved. Loosen
either to a plain `str` and those two classes report a *detector* gap that is really a
schema gap.

The types are strings carrying patterns rather than `date` and `AnyUrl`, and that is
deliberate: `studio.py` validates with `model_dump()`, and `verify.py` scores with no
normalisation at all, so a `date`-typed field would dump a `datetime.date` that can never
equal the golden's `"2026-01-14"`. Every field has to survive the round trip as the string
the manifest holds.

## A consequence to read before publishing these numbers

The schema that detects `date_format` and `url_pattern` is the same schema that rejects the
healed output: after the page changes, the values a correct collector extracts are exactly
the ones the schema refuses. Bright Data's heal repairs selectors, not your Pydantic model.
So both classes are expected to be **detected and then not healable** — `caught_by=schema`,
`healed=False`. That is a property of what the mutation does, not a failure of healing, and
it should be published as such rather than folded into the heal rate without comment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from bdheal.bench.metrics import Metrics, coverage, metrics
from bdheal.bench.runner import BenchCaseSpec, run_benchmark
from bdheal.clock import SystemClock
from bdheal.healer import Healer
from bdheal.models import BenchCase, CollectorSpec, DetectVerdict
from bdheal.process import SubprocessRunner
from bdheal.store import SqliteHealStore, connect
from bdheal.studio import BdataStudioClient
from bdheal.vocabulary import MutationClass, SignalKind

HERE = Path(__file__).resolve().parent
GATE = "BDHEAL_BENCH"
BASE_URL_VARIABLE = "BDHEAL_PAGES_URL"

# `bdata scraper create` truncates past this, and a truncated description is a collector
# scoped to something other than what was asked for.
MAX_DESCRIPTION_CHARS = 500

# `bdata scraper create` polls AI generation for `--timeout` seconds and defaults to 600.
# Measured here: a build took well over ten minutes, so the default abandons a job that is
# still running and leaves a half-built collector behind — and Bright Data exposes no
# programmatic delete, so every abandoned attempt is permanent litter in the account.
CREATE_TIMEOUT_S = 2400

# Every collector is built against the base page and told, in the words the CLI actually
# reads, not to crawl. A probe collector built without this walked 1.05K pages and failed
# 999 of them to return one record. See `fixtures/README.md`.
COLLECTOR_DESCRIPTION = (
    "Extract every row of the component register table on THIS PAGE ONLY. "
    "Follow no links. Do not paginate. Do not visit any other URL. "
    "Return one object per row with these fields: "
    "ref (the reference code, such as RF-001), "
    "name (the component name, which is the text of the row's link), "
    "category (the single category word), "
    "updated (the date exactly as printed on the page), "
    "href (the row link's href attribute, exactly as written)."
)

CONTROL_CASE_ID = "control"

# Scraper Studio returns one envelope per input URL with the rows under a name its
# generated template chose. Verified against the first built collector, which named it
# this. A collector that names it something else reads as zero rows, so check the first
# run of any newly built collector before trusting its numbers.
ROWS_KEY = "components"
ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
REGISTER_SEGMENT = "register"

# `mean_attempts_to_heal` is 1.0 by construction until the runner has a retry budget: one
# loop pass per case, one heal per pass. Recorded as a known gap in `docs/ARCHITECTURE.md`
# and repeated on the artifact, because a number carrying no information should say so
# where it is read rather than where it was decided.
ATTEMPTS_NOTE = "1.0 by construction: the loop heals once per pass and each case is one pass"


def row_schema(anchor_prefix: str) -> type[BaseModel]:
    """The shape a healthy row has on this deployment.

    Built from the site's own origin and base path, so the accepted link shape follows
    wherever the fixtures are published rather than pinning one URL into the schema. The
    prefix is absolute because collectors resolve the page's relative links before
    returning them.
    """
    pattern = rf"^{re.escape(anchor_prefix)}/{REGISTER_SEGMENT}/[a-z0-9-]+$"

    class RegisterRow(BaseModel):
        """One row of the component register, strict enough to notice when the page moves."""

        ref: str
        name: str
        category: str
        updated: str = Field(pattern=ISO_DATE_PATTERN)
        href: str = Field(pattern=pattern)

    return RegisterRow


def collector_ids(path: Path, studio: BdataStudioClient, base_url: str, cases: list[str]) -> dict[str, str]:
    """One collector per mutation class, built against the base page and remembered.

    Written back after every single build, not at the end: Bright Data exposes no
    programmatic delete, so a crash halfway through leaves collectors that can only be
    reused if their ids survived the crash.
    """
    if len(COLLECTOR_DESCRIPTION) > MAX_DESCRIPTION_CHARS:
        raise ValueError(
            f"the collector description is {len(COLLECTOR_DESCRIPTION)} characters and "
            f"`bdata scraper create` truncates past {MAX_DESCRIPTION_CHARS}"
        )
    known: dict[str, str] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for case in cases:
        if case in known:
            continue
        print(f"building a collector for {case} (about two minutes)", flush=True)
        known[case] = studio.create(base_url, COLLECTOR_DESCRIPTION)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(known, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return known


def _schema(manifest: dict[str, Any]) -> type[BaseModel]:
    """This deployment's row schema, from the origin and base path the manifest publishes."""
    return row_schema(manifest["origin"] + manifest["base_path"])


def bench_cases(manifest: dict[str, Any], base_url: str, ids: dict[str, str]) -> list[BenchCaseSpec]:
    """One case per variant, each anchored on its own fixture page."""
    schema = _schema(manifest)
    old_layout_url = f"{base_url}/{manifest['base_page']}"
    return [
        _case(variant, base_url, old_layout_url, ids[variant["mutation"]], schema)
        for variant in manifest["variants"]
    ]


def _case(
    variant: dict[str, Any],
    base_url: str,
    old_layout_url: str,
    collector_id: str,
    schema: type[BaseModel],
) -> BenchCaseSpec:
    """One mutation, hosted where it is published, scored against its own golden rows."""
    mutation = variant["mutation"]
    fixture_url = f"{base_url}/{variant['page']}"
    return BenchCaseSpec(
        case_id=mutation,
        mutation=MutationClass(mutation),
        expected_signals=frozenset(SignalKind(kind) for kind in variant["expected_signals"]),
        spec=CollectorSpec(
            collector_id=collector_id,
            name=mutation,
            anchor_urls=[fixture_url],
            row_schema=schema,
            rows_key=ROWS_KEY,
        ),
        fixture_url=fixture_url,
        old_layout_url=old_layout_url,
        golden=tuple(variant["golden"]),
    )


def control_verdict(
    manifest: dict[str, Any], base_url: str, collector_id: str, loop: Healer
) -> DetectVerdict:
    """Judge a page that changed only in ways no detector is allowed to see.

    Nine mutation cases can show that breakage is caught. None of them can show that an
    intact page is left alone, and a detector that fired on everything would score
    perfectly across all nine. This is the only thing here that measures a false positive.
    """
    schema = _schema(manifest)
    spec = CollectorSpec(
        collector_id=collector_id,
        name=CONTROL_CASE_ID,
        anchor_urls=[f"{base_url}/{manifest['base_page']}"],
        row_schema=schema,
        rows_key=ROWS_KEY,
    )
    loop.detect(spec, loop.run(spec, spec.anchor_urls))
    revised = spec.model_copy(
        update={"anchor_urls": [f"{base_url}/{manifest['control']['page']}"]}
    )
    return loop.detect(revised, loop.run(revised, revised.anchor_urls))


def report(cases: Sequence[BenchCase], control: DetectVerdict) -> str:
    """The run's numbers, its false-positive check, and its coverage matrix."""
    return "\n".join([*_headline(metrics(cases)), "", *_control(control), "", *_matrix(cases)])


def _control(verdict: DetectVerdict) -> list[str]:
    """What the untouched page did. Silence is the pass; anything else is a false positive."""
    if not verdict.broken:
        return ["false positives      0 of 1  the control page fired nothing"]
    fired = ", ".join(sorted(kind.value for kind in verdict.fired_kinds)) or "no named signal"
    return [f"false positives      1 of 1  FIRED on an intact page: {fired}"]


def _headline(measured: Metrics) -> list[str]:
    """The five metrics, then every disclosure the library attaches to them."""
    rows = [
        ("heal rate", measured.heal_rate, ""),
        ("field accuracy", measured.field_accuracy, ""),
        ("non-regression rate", measured.non_regression_rate, ""),
        ("mean time to heal (s)", measured.mean_time_to_heal_s, ""),
        ("mean attempts to heal", measured.mean_attempts_to_heal, ATTEMPTS_NOTE),
    ]
    lines = [f"{name:<24}{_number(value):>8}  {note}".rstrip() for name, value, note in rows]
    return [*lines, "", measured.non_regression_note, "", "methodology:", *(f"  - {item}" for item in measured.methodology)]


def _number(value: float | None) -> str:
    """A measured value, or the word for one that was never measured. Never zero by default."""
    return "unmeasured" if value is None else f"{value:.2f}"


def _matrix(cases: Sequence[BenchCase]) -> list[str]:
    """One row per mutation class, including the classes this run never reached."""
    header = f"{'mutation':<20}{'cases':>6}  {'expected':<20}{'caught':<20}verdict"
    return ["coverage", header, *(_matrix_row(row) for row in coverage(cases))]


def _matrix_row(row: Any) -> str:
    """What one class declared, what actually fired, and which of those two that makes it."""
    escalated = f" (+{row.escalated} escalated)" if row.escalated else ""
    return (
        f"{row.mutation.value:<20}{row.cases:>6}  "
        f"{_kinds(row.expected_signals):<20}{_kinds(row.caught_by):<20}{_verdict(row)}{escalated}"
    )


def _kinds(kinds: frozenset[SignalKind]) -> str:
    """A signal set as a reader sees it. An empty set is a dash, never a blank."""
    return ", ".join(sorted(kind.value for kind in kinds)) or "-"


def _verdict(row: Any) -> str:
    """A class that ran, was missed, or fired something nobody declared for it."""
    if not row.cases:
        return "not run"
    if row.is_gap:
        return "gap"
    return "as declared" if row.as_declared else "UNDECLARED SIGNAL"


def main() -> int:
    """Wire the real adapters, run every case not already done, and publish the run."""
    parser = argparse.ArgumentParser(description="Run the bdheal self-healing benchmark.")
    parser.add_argument("--run-id", default="bench", help="re-use to resume an interrupted run")
    parser.add_argument("--base-url", default=os.environ.get(BASE_URL_VARIABLE))
    parser.add_argument("--db", type=Path, default=HERE / "run" / "bench.db")
    parser.add_argument("--collectors", type=Path, default=HERE / "run" / "collectors.json")
    args = parser.parse_args()

    if os.environ.get(GATE) != "1":
        parser.error(f"set {GATE}=1 to spend Bright Data credit on a benchmark run")
    if not args.base_url:
        parser.error(f"set {BASE_URL_VARIABLE} or pass --base-url: the fixtures must be public")

    base_url = args.base_url.rstrip("/")
    manifest = json.loads((HERE / "site" / "manifest.json").read_text(encoding="utf-8"))

    clock = SystemClock()
    studio = BdataStudioClient(SubprocessRunner(), clock, timeout_s=CREATE_TIMEOUT_S)
    args.db.parent.mkdir(parents=True, exist_ok=True)
    store = SqliteHealStore(connect(args.db))

    ids = collector_ids(
        args.collectors, studio, f"{base_url}/{manifest['base_page']}",
        [*(variant["mutation"] for variant in manifest["variants"]), CONTROL_CASE_ID],
    )
    loop = Healer(studio, store, clock)
    cases = bench_cases(manifest, base_url, ids)
    run_benchmark(args.run_id, cases, loop, store, clock)
    control = control_verdict(manifest, base_url, ids[CONTROL_CASE_ID], loop)

    # Published from the store, never from what this call returned: the runner's return is
    # only the work *this* process did, so a resumed run would otherwise publish a matrix
    # missing everything an earlier process finished.
    print(report(store.bench_cases(args.run_id), control))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
