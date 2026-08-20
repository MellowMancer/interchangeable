"""Proof that each golden is true of the page it scores.

`render.py` derives every golden from `data.json` using the mutation generators' own
constants, which establishes that the goldens agree with the *dataset*. It does not
establish that they agree with the *pages*: the generators perturb HTML through `lxml`
while the goldens are transformed at the dict level, and a divergence between those two
paths would corrupt every published benchmark number with the whole suite still green.

So these read the committed pages back. The extractor below is an oracle, not a second
implementation of healing — it is told which classes to look for, where the benchmark's
real extractor is a Bright Data collector that has to work them out for itself.

    uv run --package bdheal pytest fixtures/tests
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import lxml.html
import pytest
from lxml.html import HtmlElement

from bdheal.bench.mutate import CLASS_PREFIX, MUTATIONS
from bdheal.skeleton import skeleton_hash
from bdheal.vocabulary import MutationClass

FIXTURES = Path(__file__).resolve().parent.parent
SITE = FIXTURES / "site"
RENDER = FIXTURES / "render.py"
MANIFEST = json.loads((SITE / "manifest.json").read_text(encoding="utf-8"))

RENDER_TIMEOUT_S = 120
PAGE_TWO = "pagination-2.html"
ROW_CLASS = "item"
HREF_FIELD = "href"
LINK_FIELD = "name"

# Read off the page rather than restated: `href` is the one field that is an attribute of
# the link inside a cell rather than the text of a cell of its own.
TEXT_FIELDS = tuple(field for field in MANIFEST["fields"] if field != HREF_FIELD)

# What the library declares each class should trip, which the manifest must not drift from.
DECLARED = {
    mutation.mutation.value: sorted(kind.value for kind in mutation.expected_signals)
    for mutation in MUTATIONS
}

CONTROL = MANIFEST["control"]

# Every page carrying records, as (id, mutation, page, golden). The base and the control
# have no mutation, so neither takes a class prefix.
PAGES = [
    ("base", None, MANIFEST["base_page"], MANIFEST["base_golden"]),
    ("control", None, CONTROL["page"], CONTROL["golden"]),
    *(
        (variant["mutation"], variant["mutation"], variant["page"], variant["golden"])
        for variant in MANIFEST["variants"]
    ),
]
PAGE_IDS = [page_id for page_id, _, _, _ in PAGES]
VARIANT_IDS = [variant["mutation"] for variant in MANIFEST["variants"]]


def extract(html: str, prefix: str = "") -> list[dict[str, str]]:
    """The records a correct collector should read off one page.

    Selection is by class token, never by tag: `table_to_div` rewrites every `tr` and `td`
    to a `div`, so a tag-based selector reads nothing there while a class-based one is
    untouched. `wrapper_nesting`'s extra container is transparent to a descendant search,
    and scoping to rows keeps `pagination`'s added page links out of the result.
    """
    root = lxml.html.fromstring(html)
    return [_record(row, prefix) for row in root.xpath(f"//*[{_token(prefix, ROW_CLASS)}]")]


def prefix_for(mutation: str | None) -> str:
    """`class_rename` prefixes every class token; no other page touches them.

    The prefix is imported from the generator rather than spelled again here, so changing
    it in one place cannot leave this reading for the old one.
    """
    return CLASS_PREFIX if mutation == MutationClass.CLASS_RENAME.value else ""


def _record(row: HtmlElement, prefix: str) -> dict[str, str]:
    """One row's fields, in the manifest's own vocabulary."""
    record = {field: _text(_cell(row, prefix, field)) for field in TEXT_FIELDS}
    raw = _cell(row, prefix, LINK_FIELD).xpath("./a/@href")[0]
    # Resolved against the site's origin, because that is what a collector returns: the
    # page carries a root-relative link and every scraper hands back the absolute one.
    record[HREF_FIELD] = MANIFEST["origin"] + raw
    return record


def _token(prefix: str, name: str) -> str:
    """An XPath predicate matching one class *token*, not the whole attribute.

    Real markup stacks classes — a cell reads `class="ref ddc-col"` — so an equality test
    on `@class` finds nothing. Padding with spaces and matching ` token ` is the standard
    way to ask "is this class among them" without a CSS engine.
    """
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {prefix}{name} ')"


def _cell(row: HtmlElement, prefix: str, field: str) -> HtmlElement:
    """The single element in `row` carrying `field`'s class, or a failure naming the field."""
    cells = row.xpath(f".//*[{_token(prefix, field)}]")
    assert len(cells) == 1, f"expected one {prefix}{field} cell per row, found {len(cells)}"
    return cells[0]


def _text(cell: HtmlElement) -> str:
    """`cell`'s words, with an element boundary counting as whitespace.

    That is the one assumption these tests make about how a page is read, and it is what
    `field_split_merge` needs: it rewrites a name as two adjacent spans with no separator
    between them, so concatenating their text yields `CobaltSpindle Bracket` — what a
    browser renders, and not what the golden says. Joining on the boundary is what "one
    column becomes two" means. See `fixtures/README.md`.
    """
    return " ".join(" ".join(cell.itertext()).split())


@pytest.mark.parametrize(("page_id", "mutation", "page", "golden"), PAGES, ids=PAGE_IDS)
def test_page_yields_its_golden(
    page_id: str, mutation: str | None, page: str, golden: list[dict]
) -> None:
    """Every page still contains the records the benchmark will score a collector against."""
    html = (SITE / page).read_text(encoding="utf-8")
    assert extract(html, prefix_for(mutation)) == golden


def test_pagination_splits_the_records_without_losing_any() -> None:
    """Page one plus page two must be the whole dataset, in order.

    The mutation drops rows from page one on purpose, and the golden scores it on that.
    What must never happen is rows going missing altogether: a split that lost records
    would let a collector score perfectly against a golden that is itself short.
    """
    page_two = (SITE / PAGE_TWO).read_text(encoding="utf-8")
    paginated = next(v for v in MANIFEST["variants"] if v["mutation"] == "pagination")
    assert paginated["golden"] + extract(page_two) == MANIFEST["base_golden"]


def test_both_pages_of_the_split_are_structurally_identical() -> None:
    """Page two must differ from page one only in text — same layout, same pager position.

    Rendering page two independently once put its pager at the end of the body while page
    one's sat beside the listing, which reads as the control jumping when you change page.
    Equal skeletons is the assertion that catches that, since the hash keeps tag, class and
    nesting and drops every word.
    """
    page_one = (SITE / paginated_page()).read_text(encoding="utf-8")
    page_two = (SITE / PAGE_TWO).read_text(encoding="utf-8")
    assert page_one != page_two
    assert skeleton_hash(page_one) == skeleton_hash(page_two)


def test_page_two_is_reachable_from_page_one() -> None:
    """A pager whose links all serve page one again is decoration, not pagination."""
    page_one = (SITE / paginated_page()).read_text(encoding="utf-8")
    assert f'href="{PAGE_TWO}"' in page_one
    assert 'href="?page=' not in page_one


def paginated_page() -> str:
    """The file the pagination variant is rendered to."""
    return next(v["page"] for v in MANIFEST["variants"] if v["mutation"] == "pagination")


def test_control_changed_the_page_without_changing_its_skeleton() -> None:
    """The control measures false positives, and only earns that if it genuinely differs.

    A control identical to the base would pass whatever the detectors do, so the first
    assertion is the load-bearing one. The second is the skeleton detector's own contract:
    reworded text, a comment and a non-class attribute are exactly what it drops.
    """
    base = (SITE / MANIFEST["base_page"]).read_text(encoding="utf-8")
    control = (SITE / CONTROL["page"]).read_text(encoding="utf-8")
    assert control != base
    assert skeleton_hash(control) == skeleton_hash(base)


def test_control_carries_the_same_records_as_the_base() -> None:
    """Nothing extractable changed, so every value detector must stay silent on it too."""
    assert CONTROL["golden"] == MANIFEST["base_golden"]


def test_committed_site_is_what_render_produces(tmp_path: Path) -> None:
    """`site/` is generated but committed, so a `git diff` of it is the record of a mutation.

    That only holds while the committed bytes are the render's. Drift would make the diff
    describe a change nobody made.
    """
    subprocess.run(
        [sys.executable, str(RENDER), "--out", str(tmp_path)],
        check=True,
        capture_output=True,
        timeout=RENDER_TIMEOUT_S,
    )
    fresh, committed = _tree(tmp_path), _tree(SITE)
    assert sorted(fresh) == sorted(committed)
    assert [name for name in committed if fresh[name] != committed[name]] == []


def test_manifest_covers_every_declared_mutation() -> None:
    """A class missing from the manifest is a class the benchmark silently never runs."""
    assert sorted(variant["mutation"] for variant in MANIFEST["variants"]) == sorted(DECLARED)


@pytest.mark.parametrize("variant", MANIFEST["variants"], ids=VARIANT_IDS)
def test_expected_signals_match_the_library_declaration(variant: dict) -> None:
    """The manifest publishes the declaration; `MUTATIONS` owns it. They cannot disagree."""
    assert variant["expected_signals"] == DECLARED[variant["mutation"]]


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under `root`, keyed by its path relative to it."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
