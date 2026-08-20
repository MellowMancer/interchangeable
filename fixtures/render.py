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

import lxml.html
from lxml.html import HtmlElement

from bdheal.bench.mutate import (
    DAY_FIRST_DATE,
    first_page,
    ISO_DATE,
    LINK_TEXT,
    MOVED_PATH_PREFIX,
    MUTATIONS,
    TRACKING_QUERY,
    Mutation,
)
from bdheal.vocabulary import MutationClass

BASE_PAGE = "index.html"
CONTROL_PAGE = "control.html"
PAGE_TWO = "pagination-2.html"
NAV_PAGE = "pages.html"
MANIFEST = "manifest.json"
DOCTYPE = "<!doctype html>\n"
VIEWPORT = '<meta name="viewport" content="width=device-width,initial-scale=1">'
REGISTER_CLASS = "register ddc-table js-sortable"
BASE_EYEBROW = "bdheal benchmark fixture"

# Page furniture. Invented like everything else here, and deliberately *not* using any class
# the register uses: a collector has to tell the data apart from the decoration, but the
# golden must stay unambiguous about which rows are the data.
CRUMBS = ("Home", "Registers", "Components")
FILTERS = ("All categories", "Brackets", "Dampers", "Seals", "Recently updated")
COLOPHON = ("About this register", "Change log", "Contact")

# A decoy listing: same shape as the register, different classes, and deliberately shorter.
# `pagination` splits the largest group of identical siblings, so noise that repeated more
# than the register would hijack it.
RETIRED = (
    ("RT-114", "Obsolete Cam Follower"),
    ("RT-115", "Legacy Strut Mount"),
    ("RT-116", "Withdrawn Pivot Pin"),
    ("RT-117", "Superseded Trunnion Cap"),
)
NAV_EYEBROW = "bdheal benchmark"

# The fields a benchmark collector is asked to extract, in the order the page presents them.
FIELDS = ("ref", "name", "category", "updated", "href")

# `href` is read off the row's link, not a column of its own, so it is a golden field with
# no header. Emitting one produced a column with no cells under it, which reads as a
# rendering fault rather than as the deliberate shape it is.
HREF_FIELD = "href"
CELL_FIELDS = tuple(field for field in FIELDS if field != HREF_FIELD)

# Every page carries this, and it is not decoration: a page of realistic-looking records
# that escapes this directory should say what it is on its face.
NOTICE = (
    "These pages are synthetic fixtures for testing bdheal, the self-healing scraper "
    "benchmark. Every record is invented and describes nothing real."
)

# The links are extracted as data, never followed. They resolve to nothing on purpose, so a
# collector that ignores its single-page instruction fails loudly here instead of quietly
# crawling. See README.md.
NOFOLLOW = '<meta name="robots" content="nofollow">'

STYLE = (
    ":root{--ink:#12181f;--muted:#5b6672;--line:#dfe4ea;--bg:#f6f7f9;--card:#fff;"
    "--accent:#1f6feb;--warn:#8a4b00;--warn-bg:#fff4e0;--warn-line:#e3a343}"
    "*{box-sizing:border-box}"
    "body{margin:0;background:var(--bg);color:var(--ink);"
    "font:16px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    "-webkit-font-smoothing:antialiased;padding-bottom:6rem}"
    ".masthead{background:var(--card);border-bottom:1px solid var(--line);padding:2rem 1.5rem 1.25rem}"
    ".eyebrow{margin:0 0 .35rem;font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;"
    "color:var(--accent);font-weight:600}"
    ".masthead h1{margin:0;font-size:1.6rem;font-weight:650;letter-spacing:-.015em}"
    ".register{width:calc(100% - 3rem);max-width:64rem;margin:1.75rem 1.5rem;background:var(--card);"
    "border:1px solid var(--line);border-radius:10px;border-collapse:separate;border-spacing:0;"
    "overflow:hidden;box-shadow:0 1px 2px rgba(16,24,40,.04)}"
    ".register th{position:sticky;top:0;background:#eef1f5;color:var(--muted);text-align:left;"
    "font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;font-weight:600;"
    "padding:.7rem .9rem;border-bottom:1px solid var(--line);white-space:nowrap}"
    ".register td{padding:.72rem .9rem;border-bottom:1px solid #eef0f3;vertical-align:top}"
    ".register tr:last-child td{border-bottom:0}"
    ".register tbody tr:nth-child(even) td{background:#fafbfc}"
    ".register tbody tr:hover td{background:#f0f5ff}"
    ".ref{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.85rem;"
    "color:var(--muted);white-space:nowrap}"
    ".name a{color:var(--accent);text-decoration:none;font-weight:550}"
    ".name a:hover{text-decoration:underline}"
    ".category{color:var(--muted)}"
    ".updated{font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap}"
    "ul{max-width:64rem;margin:1.75rem 1.5rem;padding:0;list-style:none;background:var(--card);"
    "border:1px solid var(--line);border-radius:10px;overflow:hidden}"
    "li{border-bottom:1px solid #eef0f3}"
    "li:last-child{border-bottom:0}"
    "li a{display:block;padding:.8rem .9rem;color:var(--accent);text-decoration:none;font-weight:550}"
    "li a:hover{background:#f0f5ff}"
    ".pagination{display:flex;gap:.4rem;margin:0 1.5rem 2rem}"
    ".pagination .page{display:inline-block;min-width:2rem;text-align:center;padding:.4rem .6rem;"
    "background:var(--card);border:1px solid var(--line);border-radius:6px;color:var(--accent);"
    "text-decoration:none;font-size:.85rem}"
    ".wrap{display:contents}"
    ".part{display:inline}"
    ".disclaimer{position:fixed;right:1rem;bottom:1rem;z-index:9;max-width:22rem;"
    "background:var(--warn-bg);border:1px solid var(--warn-line);border-left:4px solid var(--warn-line);"
    "border-radius:8px;padding:.7rem .85rem;color:var(--warn);font-size:.78rem;line-height:1.45;"
    "box-shadow:0 6px 20px rgba(16,24,40,.13)}"
    ".ddc-cookie-bar{display:flex;gap:1rem;align-items:center;justify-content:space-between;"
    "background:#12181f;color:#e7ecf2;padding:.7rem 1.5rem;font-size:.82rem}"
    ".cookie-copy{margin:0}"
    ".btn{border:0;border-radius:6px;padding:.4rem .9rem;font:inherit;font-size:.8rem;cursor:pointer}"
    ".btn-primary{background:var(--accent);color:#fff}"
    ".page-wrap{padding-bottom:1rem}"
    ".container{max-width:80rem}"
    ".feature-slot{display:flex;align-items:center;justify-content:center;height:5.5rem;"
    "margin:1.25rem 1.5rem 0;border:1px dashed #ccd3db;border-radius:10px;background:#fbfcfd}"
    ".feature-note{font-size:.66rem;letter-spacing:.16em;text-transform:uppercase;color:#9aa5b1}"
    ".ddc-content-block{min-width:0}"
    ".table-responsive{overflow-x:auto}"
    ".crumbs{padding:.7rem 1.5rem;background:var(--card);border-bottom:1px solid var(--line);"
    "font-size:.8rem;color:var(--muted)}"
    ".crumb{color:var(--muted);text-decoration:none}"
    ".crumb:hover{color:var(--accent)}"
    ".crumb+.crumb:before{content:'/';margin:0 .5rem;color:#c3cad3}"
    ".layout{display:grid;grid-template-columns:minmax(0,1fr) 16rem;gap:0;align-items:start}"
    ".content{min-width:0}"
    ".panel{margin:1.75rem 1.5rem 0 0;background:var(--card);border:1px solid var(--line);"
    "border-radius:10px;padding:.9rem}"
    ".panel-title,.section-title{margin:0 0 .6rem;font-size:.72rem;letter-spacing:.1em;"
    "text-transform:uppercase;color:var(--muted);font-weight:600}"
    ".filters{margin:0;border:0;background:none;border-radius:0}"
    ".filters li{border-bottom:1px solid #f0f2f5}"
    ".filters li:last-child{border-bottom:0}"
    ".filters a{padding:.45rem .2rem;font-weight:450;font-size:.88rem}"
    ".related-wrap{margin:2rem 1.5rem}"
    ".related{width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;"
    "border-collapse:separate;border-spacing:0;overflow:hidden;opacity:.85}"
    ".related th{background:#f2f4f7;color:var(--muted);text-align:left;font-size:.68rem;"
    "letter-spacing:.09em;text-transform:uppercase;padding:.55rem .9rem;"
    "border-bottom:1px solid var(--line)}"
    ".related td{padding:.55rem .9rem;border-bottom:1px solid #eef0f3;font-size:.88rem;"
    "color:var(--muted)}"
    ".related tr:last-child td{border-bottom:0}"
    ".e-code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.8rem}"
    ".colophon{display:flex;gap:1.25rem;padding:1.5rem;margin-top:1rem;"
    "border-top:1px solid var(--line);font-size:.82rem}"
    ".foot-link{color:var(--muted);text-decoration:none}"
    ".foot-link:hover{color:var(--accent)}"
    "@media(max-width:900px){.layout{grid-template-columns:minmax(0,1fr)}"
    ".panel{margin:0 1.5rem}}"
    "@media(max-width:640px){.disclaimer{left:1rem;max-width:none}"
    ".register{width:calc(100% - 1.5rem);margin:1rem .75rem}}"
)


COOKIE_COPY = "This fixture site sets no cookies. The bar is here because real listings have one."
AD_LABEL = "Advertisement"
CONFIG_JSON = '{"registry":"components","version":2}'


def _cookie_bar() -> str:
    """A consent bar. Real listings open with one, and it is the first thing above the data."""
    return (
        '<div class="ddc-cookie-bar js-cookie-notice">'
        f'<p class="cookie-copy">{escape(COOKIE_COPY)}</p>'
        '<button class="btn btn-primary js-accept" type="button">Accept</button></div>'
    )


def _ad_slot() -> str:
    """An empty promotional container — structure a collector must walk past.

    Named `feature-slot` rather than `ad-slot` on purpose: the obvious names are cosmetic
    ad-blocker selectors, so the block vanished for anyone browsing with one and the
    fixture looked broken. Server-side scrapers never saw the difference.
    """
    return (
        '<div class="feature-slot ddc-feature" data-block="leaderboard">'
        f'<span class="feature-note">{escape(AD_LABEL)}</span></div>'
    )


def _config() -> str:
    """An inline config blob. Single-token text, so `field_split_merge` cannot get inside it."""
    return f'<script type="application/json" class="ddc-config">{CONFIG_JSON}</script>'


def _crumbs() -> str:
    """A breadcrumb trail — links that are not data, on a page whose data is links."""
    links = "".join(f'<a class="crumb" href="#">{escape(name)}</a>' for name in CRUMBS)
    return f'<nav class="crumbs">{links}</nav>'


def _panel() -> str:
    """A filter sidebar. Repeats, but fewer times than the register does."""
    items = "".join(f'<li class="filter"><a href="#">{escape(name)}</a></li>' for name in FILTERS)
    return (
        '<aside class="panel"><h2 class="panel-title">Filters</h2>'
        f'<ul class="filters">{items}</ul></aside>'
    )


def _related() -> str:
    """A second table of the same shape as the register — the noise that actually bites.

    A collector that finds "the table" rather than *this* table extracts the wrong rows,
    and nothing about the markup says which is which except what surrounds it.
    """
    rows = "".join(
        f'<tr class="entry"><td class="e-code">{escape(code)}</td>'
        f'<td class="e-title">{escape(title)}</td></tr>'
        for code, title in RETIRED
    )
    return (
        '<section class="related-wrap"><h2 class="section-title">Recently retired</h2>'
        '<table class="related"><thead><tr class="entry-head">'
        '<th class="h-code">Code</th><th class="h-title">Title</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></section>"
    )


def _colophon() -> str:
    """A footer. More links that are not data."""
    links = "".join(f'<a class="foot-link" href="#">{escape(name)}</a>' for name in COLOPHON)
    return f'<footer class="colophon">{links}</footer>'


def _masthead(title: str, eyebrow: str) -> str:
    """The page's heading block. `h1` carries the title on every page, control edits included."""
    return (
        f'<header class="masthead"><p class="eyebrow">{escape(eyebrow)}</p>'
        f"<h1>{escape(title)}</h1></header>"
    )


def _disclaimer() -> str:
    """The standing notice, pinned bottom-right so it cannot be scrolled past.

    A page of realistic-looking records that escapes this directory should say what it is
    on its face, and a banner at the top stops saying it the moment anyone scrolls.
    """
    return f'<aside class="disclaimer">{escape(NOTICE)}</aside>'


def load(path: Path) -> dict[str, Any]:
    """The dataset, as written. Fails loudly rather than rendering half a site."""
    return json.loads(path.read_text(encoding="utf-8"))


# The control's edits, chosen against what `skeleton()` actually reads: it keeps tags,
# sorted classes and nesting, and drops text, comments and every other attribute. All three
# of these therefore leave the fingerprint identical, and none touches an extracted field.
CONTROL_COMMENT = "<!-- Benign revision: wording and non-class attributes only. -->"
CONTROL_NOTE = " Wording revised for this copy; structure untouched."
CONTROL_TITLE_SUFFIX = " (revised)"
CONTROL_ATTRIBUTE = ' data-revision="2"'


def benign(base: str, title: str) -> str:
    """The base page changed in every way a detector must ignore.

    A control compared against an identical page proves nothing — whatever the detectors
    do, silence is guaranteed. So this one genuinely differs: reworded heading, reworded
    notice, an added comment and an added non-class attribute. If any detector fires on
    it, that is a false positive, which is the one thing nine mutation cases cannot measure.

    Each edit is asserted rather than attempted: a replacement that quietly missed would
    hand back the base page and make the control vacuous.
    """
    edits = (
        (f"<h1>{escape(title)}</h1>", f"<h1>{escape(title + CONTROL_TITLE_SUFFIX)}</h1>"),
        (escape(NOTICE), escape(NOTICE + CONTROL_NOTE)),
        (
            f'<table class="{REGISTER_CLASS}">',
            f'{CONTROL_COMMENT}<table class="{REGISTER_CLASS}"{CONTROL_ATTRIBUTE}>',
        ),
    )
    revised = base
    for target, replacement in edits:
        if target not in revised:
            raise ValueError(f"the control edit {target!r} matched nothing; the page moved")
        revised = revised.replace(target, replacement, 1)
    return revised


def anchored(records: list[dict[str, str]], base_path: str) -> list[dict[str, str]]:
    """Every record's link under the deployment's base path.

    The links are dead on purpose, but a root-relative one is dead *outside* this site: on
    a project Pages site `/register/rf-001` resolves against the account root, so the
    tripwire fires somewhere the fixtures do not own. Prefixing keeps the 404 inside the
    published site.

    Applied once, before anything is rendered or scored, so a page and the golden records
    it is scored against cannot disagree about where a link points.
    """
    return [record | {"href": base_path + record["href"]} for record in records]


def _document(title: str, body: str) -> str:
    """One page, head and all. Shared, so the fixtures and the index cannot drift apart."""
    head = (
        f'<meta charset="utf-8">{VIEWPORT}{NOFOLLOW}'
        f"<title>{escape(title)}</title><style>{STYLE}</style>"
    )
    return f'{DOCTYPE}<html lang="en">\n<head>{head}</head>\n<body>\n{body}\n</body>\n</html>\n'


def render_base(title: str, records: list[dict[str, str]]) -> str:
    """The base page — the layout a collector is built against before anything breaks."""
    body = (
        f"{_cookie_bar()}\n{_masthead(title, BASE_EYEBROW)}\n{_crumbs()}\n"
        '<div class="page-wrap">\n<div class="container">\n'
        f"{_ad_slot()}\n"
        '<div class="row layout">\n<div class="col-md-8 content">\n'
        '<div class="ddc-content-block">\n'
        f"{_table(records)}\n</div>\n{_related()}\n</div>\n"
        f'<div class="col-md-4 panel-col">\n{_panel()}\n</div>\n'
        "</div>\n</div>\n</div>\n"
        f"{_colophon()}\n{_disclaimer()}\n{_config()}"
    )
    return _document(title, body)


def _table(records: list[dict[str, str]]) -> str:
    """The register as a table: repeating rows, one class per column."""
    headers = "".join(
        f'<th class="h-{field} ddc-col-head">{field.title()}</th>' for field in CELL_FIELDS
    )
    rows = "\n".join(_row(record) for record in records)
    return (
        '<div class="table-responsive js-table-wrap">\n'
        f'<table class="{REGISTER_CLASS}">\n'
        f'<thead><tr class="head ddc-head-row">{headers}</tr></thead>\n'
        f"<tbody>\n{rows}\n</tbody>\n</table>\n</div>"
    )


def _row(record: dict[str, str]) -> str:
    """One record. The name sits inside the link, so relabelling links changes real data."""
    link = f'<a href="{escape(record["href"])}">{escape(record["name"])}</a>'
    cells = (
        f'<td class="ref ddc-col">{escape(record["ref"])}</td>'
        f'<td class="name ddc-col js-title">{link}</td>'
        f'<td class="category ddc-col">{escape(record["category"])}</td>'
        f'<td class="updated ddc-col">{escape(record["updated"])}</td>'
    )
    return f'<tr class="item productRow">{cells}</tr>'


def golden(
    mutation: MutationClass, records: list[dict[str, str]], origin: str
) -> list[dict[str, str]]:
    """What a correct collector should extract from one variant.

    Structural mutations move markup and leave every value where it was, so their golden is
    the base one. The three text-changing classes are the exception, and each is applied
    here with the generator's own constant.
    """
    return [_record(mutation, record, origin) for record in _carried(mutation, records)]


def _carried(mutation: MutationClass, records: list[dict[str, str]]) -> list[dict[str, str]]:
    """The records the mutated page still carries.

    Pagination is the one class that drops some, and it drops them by the generator's own
    rule rather than a second copy of it.
    """
    if mutation is MutationClass.PAGINATION:
        return records[: first_page(len(records))]
    return records


def _record(mutation: MutationClass, record: dict[str, str], origin: str) -> dict[str, str]:
    """One golden record under one mutation."""
    values = {field: record[field] for field in FIELDS}
    if mutation is MutationClass.DATE_FORMAT:
        values["updated"] = ISO_DATE.sub(DAY_FIRST_DATE, values["updated"])
    elif mutation is MutationClass.URL_PATTERN:
        values["href"] = f"{MOVED_PATH_PREFIX}{values['href']}{TRACKING_QUERY}"
    elif mutation is MutationClass.LINK_LABEL:
        values["name"] = LINK_TEXT
    values["href"] = origin + values["href"]
    return values


# Which file actually serves each page of the split listing. The generator emits
# `?page=N`, which is what a real listing does and what a static host cannot route:
# `pagination.html?page=2` serves `pagination.html`. These are the files that can.
def _page_files() -> dict[int, str]:
    """Page number to the file serving it. Page one is the mutation's own page."""
    return {1: f"{MutationClass.PAGINATION.value}.html", 2: PAGE_TWO}


def _link_pages(html: str) -> str:
    """Point the generator's `?page=N` links at the files that serve those pages.

    This is the one place a rendered page differs from its generator's raw output, and it
    is deliberate: without it the pager is decoration — every link serves page one again.
    """
    for number, page in _page_files().items():
        html = html.replace(f'href="?page={number}"', f'href="{page}"')
    return html


def _second_page(records: list[dict[str, str]], first: str) -> str:
    """Page two: page one, carrying the rows page one dropped.

    Built *from* page one rather than rendered afresh, so the two are structurally
    identical — including where the pager sits. Rendering it separately placed the pager
    at the end of the body instead of beside the listing, which reads as the control
    jumping position when you change page.
    """
    root = lxml.html.fromstring(first)
    holder = _register_body(root)
    for row in list(holder):
        holder.remove(row)
    holder.extend(
        lxml.html.fragment_fromstring(_row(record))
        for record in records[first_page(len(records)) :]
    )
    return DOCTYPE + lxml.html.tostring(root, encoding="unicode")


def _register_body(root: HtmlElement) -> HtmlElement:
    """The register's `tbody` — the one holding records, never the decoy listing's."""
    holders = root.xpath(
        "//table[contains(concat(' ', normalize-space(@class), ' '), ' register ')]/tbody"
    )
    if len(holders) != 1:
        raise ValueError(f"expected one register tbody on page one, found {len(holders)}")
    return holders[0]


def _write_pager(out: Path, title: str, records: list[dict[str, str]]) -> None:
    """Make the split listing navigable: real links on page one, and the page they reach."""
    page_one = out / _page_files()[1]
    first = _link_pages(page_one.read_text(encoding="utf-8"))
    _write(page_one, first)
    _write(out / PAGE_TWO, _link_pages(_second_page(records, first)))


def write_site(
    out: Path, title: str, records: list[dict[str, str]], origin: str
) -> list[dict[str, Any]]:
    """Write the base page, every mutated page, and return the manifest's variant entries."""
    out.mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    base = render_base(title, records)
    _write(out / BASE_PAGE, base)
    _write(out / CONTROL_PAGE, benign(base, title))
    variants = [_variant(out, mutation, base, records, origin) for mutation in MUTATIONS]
    _write_pager(out, title, records)
    _write(out / NAV_PAGE, render_nav(title, variants))
    return variants


def render_nav(title: str, variants: list[dict[str, Any]]) -> str:
    """A human index of the fixture set — the one page here meant to be clicked.

    Deliberately one-directional: it links to the fixtures and no fixture links back, so a
    collector anchored on a fixture can never reach it and the single-page tripwire is
    untouched. It is not a benchmark page and never appears in the manifest.
    """
    items = "\n".join(
        f'<li><a href="{escape(page)}">{escape(label)}</a></li>'
        for page, label in _listing(variants)
    )
    heading = f"{title} fixtures"
    body = (
        f"{_masthead(heading, NAV_EYEBROW)}\n<ul>\n{items}\n</ul>\n{_disclaimer()}"
    )
    return _document(heading, body)


def _listing(variants: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Every page the site serves, base first, each beside what it is."""
    return [
        (BASE_PAGE, "base layout"),
        (CONTROL_PAGE, "control — benign edits, no detector may fire"),
        *((variant["page"], variant["mutation"]) for variant in variants),
    ]


def _variant(
    out: Path, mutation: Mutation, base: str, records: list[dict[str, str]], origin: str
) -> dict[str, Any]:
    """One mutated page and the entry describing it."""
    page = f"{mutation.mutation.value}.html"
    _write(out / page, DOCTYPE + mutation.apply(base))
    return {
        "mutation": mutation.mutation.value,
        "page": page,
        "expected_signals": sorted(kind.value for kind in mutation.expected_signals),
        "golden": golden(mutation.mutation, records, origin),
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
    base_path = dataset["base_path"]
    records = anchored(dataset["records"], base_path)
    origin = dataset["origin"]
    variants = write_site(args.out, dataset["title"], records, origin)

    manifest = {
        "base_page": BASE_PAGE,
        # Published so a consumer can say what a healthy `href` looks like without
        # re-deriving it from the goldens. The benchmark's row schema is written against it.
        "base_path": base_path,
        # The origin a collector resolves the page's root-relative links against. The page
        # keeps them relative — absolute ones would stop `url_pattern` rewriting anything.
        "origin": origin,
        "fields": list(FIELDS),
        "base_golden": golden_base(records, origin),
        # Not a variant: nothing was broken, so it carries no expected signals and belongs
        # in no coverage row. It measures false positives, which no mutation can.
        "control": {"page": CONTROL_PAGE, "golden": golden_base(records, origin)},
        "variants": variants,
    }
    (args.out / MANIFEST).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"rendered {1 + len(variants)} fixture pages, {NAV_PAGE} and {MANIFEST} -> {args.out}")
    return 0


def golden_base(records: list[dict[str, str]], origin: str) -> list[dict[str, str]]:
    """The base page's golden — what the old layout must still yield after any heal."""
    return [
        {**{field: record[field] for field in FIELDS}, "href": origin + record["href"]}
        for record in records
    ]


if __name__ == "__main__":
    raise SystemExit(main())
