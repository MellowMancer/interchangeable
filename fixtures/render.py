#!/usr/bin/env python3
"""Render `data.json` into the benchmark's fixture site: one base page, one page per mutation.

The dataset is the single source of truth. The base page is rendered from it, every mutated
page is that base page put through one of `bdheal`'s own generators, and the golden records
are derived from the same dataset rather than transcribed — so a fixture and the records it
is scored against cannot drift apart.

Three mutation classes rewrite the page's *text* rather than its markup, so their golden
differs from the base one. Those transforms are applied here using the generators' own
constants, never a second copy of the rule: change `MOVED_PATH_PREFIX` in `bdheal` and the
golden follows it.

Deterministic. The same dataset renders byte-identical output every time, which is what
makes a `git diff` of `site/` the reviewable record of what a mutation changed.

    uv run --package bdheal python fixtures/render.py
"""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

from bdheal.bench.mutate import (
    DAY_FIRST_DATE,
    ISO_DATE,
    LINK_TEXT,
    MOVED_PATH_PREFIX,
    MUTATIONS,
    TRACKING_QUERY,
    Mutation,
)
from bdheal.vocabulary import MutationClass

BASE_PAGE = "index.html"
MANIFEST = "manifest.json"
DOCTYPE = "<!doctype html>\n"

# The fields a benchmark collector is asked to extract, in the order the page presents them.
FIELDS = ("ref", "name", "category", "updated", "href")

# Every page carries this, and it is not decoration: a page of realistic-looking records
# that escapes this directory should say what it is on its face.
NOTICE = (
    "Synthetic fixture for the bdheal self-healing benchmark. "
    "Every record on this page is invented and describes nothing real."
)

# The links are extracted as data, never followed. They resolve to nothing on purpose, so a
# collector that ignores its single-page instruction fails loudly here instead of quietly
# crawling. See README.md.
NOFOLLOW = '<meta name="robots" content="nofollow">'

STYLE = (
    "body{font-family:system-ui,sans-serif;margin:2rem;max-width:60rem}"
    ".notice{background:#fde8e8;border-left:4px solid #c53030;padding:.75rem;color:#742a2a}"
    ".register{border-collapse:collapse;width:100%;margin-top:1.5rem}"
    ".register th,.register td{border:1px solid #ddd;padding:.5rem;text-align:left}"
)


def load(path: Path) -> dict[str, Any]:
    """The dataset, as written. Fails loudly rather than rendering half a site."""
    return json.loads(path.read_text(encoding="utf-8"))


def render_base(title: str, records: list[dict[str, str]]) -> str:
    """The base page — the layout a collector is built against before anything breaks."""
    head = (
        f'<meta charset="utf-8">{NOFOLLOW}<title>{escape(title)}</title><style>{STYLE}</style>'
    )
    body = (
        f'<p class="notice">{escape(NOTICE)}</p>\n'
        f"<h1>{escape(title)}</h1>\n"
        f"{_table(records)}"
    )
    return f"{DOCTYPE}<html lang=\"en\">\n<head>{head}</head>\n<body>\n{body}\n</body>\n</html>\n"


def _table(records: list[dict[str, str]]) -> str:
    """The register as a table: repeating rows, one class per column."""
    headers = "".join(f'<th class="h-{field}">{field.title()}</th>' for field in FIELDS)
    rows = "\n".join(_row(record) for record in records)
    return (
        f'<table class="register">\n<thead><tr class="head">{headers}</tr></thead>\n'
        f"<tbody>\n{rows}\n</tbody>\n</table>"
    )


def _row(record: dict[str, str]) -> str:
    """One record. The name sits inside the link, so relabelling links changes real data."""
    link = f'<a href="{escape(record["href"])}">{escape(record["name"])}</a>'
    cells = (
        f'<td class="ref">{escape(record["ref"])}</td>'
        f'<td class="name">{link}</td>'
        f'<td class="category">{escape(record["category"])}</td>'
        f'<td class="updated">{escape(record["updated"])}</td>'
    )
    return f'<tr class="item">{cells}</tr>'


def golden(mutation: MutationClass, records: list[dict[str, str]]) -> list[dict[str, str]]:
    """What a correct collector should extract from one variant.

    Structural mutations move markup and leave every value where it was, so their golden is
    the base one. The three text-changing classes are the exception, and each is applied
    here with the generator's own constant.
    """
    return [_record(mutation, record) for record in records]


def _record(mutation: MutationClass, record: dict[str, str]) -> dict[str, str]:
    """One golden record under one mutation."""
    values = {field: record[field] for field in FIELDS}
    if mutation is MutationClass.DATE_FORMAT:
        values["updated"] = ISO_DATE.sub(DAY_FIRST_DATE, values["updated"])
    elif mutation is MutationClass.URL_PATTERN:
        values["href"] = f"{MOVED_PATH_PREFIX}{values['href']}{TRACKING_QUERY}"
    elif mutation is MutationClass.LINK_LABEL:
        values["name"] = LINK_TEXT
    return values


def write_site(out: Path, title: str, records: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Write the base page, every mutated page, and return the manifest's variant entries."""
    out.mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    base = render_base(title, records)
    _write(out / BASE_PAGE, base)
    return [_variant(out, mutation, base, records) for mutation in MUTATIONS]


def _variant(
    out: Path, mutation: Mutation, base: str, records: list[dict[str, str]]
) -> dict[str, Any]:
    """One mutated page and the entry describing it."""
    page = f"{mutation.mutation.value}.html"
    _write(out / page, DOCTYPE + mutation.apply(base))
    return {
        "mutation": mutation.mutation.value,
        "page": page,
        "expected_signals": sorted(kind.value for kind in mutation.expected_signals),
        "golden": golden(mutation.mutation, records),
    }


def _write(path: Path, html: str) -> None:
    """Newline-normalised, so the site renders identically on any platform that generates it."""
    path.write_text(html, encoding="utf-8", newline="\n")


def main() -> int:
    """Render the site and its manifest beside this script."""
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=here / "data.json")
    parser.add_argument("--out", type=Path, default=here / "site")
    args = parser.parse_args()

    dataset = load(args.data)
    records = dataset["records"]
    variants = write_site(args.out, dataset["title"], records)

    manifest = {
        "base_page": BASE_PAGE,
        "fields": list(FIELDS),
        "base_golden": golden_base(records),
        "variants": variants,
    }
    (args.out / MANIFEST).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"rendered {1 + len(variants)} pages and {MANIFEST} -> {args.out}")
    return 0


def golden_base(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """The base page's golden — what the old layout must still yield after any heal."""
    return [{field: record[field] for field in FIELDS} for record in records]


if __name__ == "__main__":
    raise SystemExit(main())
