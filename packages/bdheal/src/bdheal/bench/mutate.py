"""Nine domain-free HTML perturbations. Structure and text, never meaning.

Each generator is a pure `str -> str` function and carries, as data, the detect signal it
is *declared* to trip. The declaration is a claim the benchmark then checks against what
actually fired; where the two disagree the result is a published coverage gap, not a
hidden failure. `link_label` is declared as the empty set on purpose — no detector can see it, and
saying so is the honest finding.

The declared signal for each class is fixed by the architecture contract; `MUTATIONS`
below is populated to match it.
"""

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

import lxml.html
from lxml.html import HtmlElement

from bdheal.vocabulary import MutationClass, SignalKind

CLASS_PREFIX = "x-"
LINK_TEXT = "Details"
MOVED_PATH_PREFIX = "/v2"
TRACKING_QUERY = "?ref=list"
ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DAY_FIRST_DATE = r"\3/\2/\1"
PART_CLASS = "part"
WRAPPER_CLASS = "wrap"
PAGINATION_CLASS = "pagination"
PAGE_CLASS = "page"
PAGE_NUMBERS = (1, 2)
DIV_TAG = "div"
TABLE_TAGS = frozenset({"table", "thead", "tbody", "tfoot", "tr", "th", "td"})


@dataclass(frozen=True, slots=True)
class Mutation:
    """One perturbation: what it is called, what it does, and what should catch it."""

    mutation: MutationClass
    expected_signals: frozenset[SignalKind]
    apply: Callable[[str], str]



def _parse(html: str) -> HtmlElement:
    """`html` as a tree. The generators share one parser so their output shares one shape."""
    return lxml.html.fromstring(html)


def _serialise(root: HtmlElement) -> str:
    """The tree back as HTML — deterministic, which is what makes goldens assertable."""
    return lxml.html.tostring(root, encoding="unicode")


RAW_TEXT_TAGS = frozenset({"style", "script"})
"""Elements whose content is not markup, and must not be mutated as though it were.

A mutation models a publisher rebuilding a *layout*. Rewriting the text inside `<style>`
models nothing: `field_split_merge` wrapped every run of CSS in `<span class="part">`,
which does not restructure the page so much as destroy its stylesheet — the fixture then
renders unstyled, which is a broken page rather than a moved one. The extracted values
were unaffected, so no benchmark number was ever wrong; the page simply lied about what
the mutation had done to it.
"""


def _elements(root: HtmlElement) -> list[HtmlElement]:
    """Every element from `root` down, excluding comments, PIs and raw-text elements."""
    return [
        node
        for node in root.iter()
        if isinstance(node.tag, str) and node.tag not in RAW_TEXT_TAGS
    ]


def _children(node: HtmlElement) -> list[HtmlElement]:
    """The element children of `node`, in document order."""
    return [child for child in node if isinstance(child.tag, str)]


def _content_host(root: HtmlElement) -> HtmlElement:
    """Where page content lives: `body` for a whole document, the fragment itself otherwise."""
    body = root.find("body")
    return root if body is None else body


def _element(tag: str, attributes: dict[str, str], text: str | None = None) -> HtmlElement:
    """A new element with its attributes in a fixed order, so serialisation is stable."""
    node = lxml.html.Element(tag, attributes)
    node.text = text
    return node


def class_rename(html: str) -> str:
    """Prefix every class token, the way a redesign renames the hooks a selector relies on."""
    root = _parse(html)
    for node in _elements(root):
        names = (node.get("class") or "").split()
        if names:
            node.set("class", " ".join(CLASS_PREFIX + name for name in names))
    return _serialise(root)


def table_to_div(html: str) -> str:
    """Rebuild table markup as nested divs, keeping every class and every word."""
    root = _parse(html)
    for node in _elements(root):
        if node.tag in TABLE_TAGS:
            node.tag = DIV_TAG
    return _serialise(root)


def column_reorder(html: str) -> str:
    """Reverse sibling columns that share a tag but differ in class.

    Identical siblings are excluded deliberately: swapping two indistinguishable elements
    does not change the structure, so it cannot — and should not — move a structural hash.
    """
    root = _parse(html)
    for node in _elements(root):
        columns = _children(node)
        if _are_columns(columns):
            node.extend(reversed(columns))
    return _serialise(root)


def _uniform_tag(children: list[HtmlElement]) -> bool:
    """Two or more siblings sharing one tag — a group, before asking what tells them apart."""
    return len(children) >= 2 and len({child.tag for child in children}) == 1


def _classes(children: list[HtmlElement]) -> set[str | None]:
    """The distinct class attributes across siblings: one means uniform, more means columns."""
    return {child.get("class") for child in children}


def _are_columns(children: list[HtmlElement]) -> bool:
    """Two or more siblings of one tag, told apart by class: a row of columns."""
    return _uniform_tag(children) and len(_classes(children)) > 1


def _are_rows(children: list[HtmlElement]) -> bool:
    """Two or more siblings of one tag and one class: the repeating rows of a listing."""
    return _uniform_tag(children) and len(_classes(children)) == 1


def link_label(html: str) -> str:
    """Relabel every link. Words only, which is why no structural detector sees it."""
    root = _parse(html)
    for node in root.iter("a"):
        node.text = LINK_TEXT
    return _serialise(root)


def url_pattern(html: str) -> str:
    """Move relative links onto another path prefix and add a query — the URL scheme shifted."""
    root = _parse(html)
    for node in _elements(root):
        href = node.get("href")
        if href and href.startswith("/"):
            node.set("href", f"{MOVED_PATH_PREFIX}{href}{TRACKING_QUERY}")
    return _serialise(root)


def date_format(html: str) -> str:
    """Rewrite ISO dates as day-first text, so a date field stops validating."""
    root = _parse(html)
    for node in _elements(root):
        node.text = _day_first(node.text)
        node.tail = _day_first(node.tail)
    return _serialise(root)


def _day_first(text: str | None) -> str | None:
    """`2026-01-01` becomes `01/01/2026` wherever it appears in `text`."""
    return None if text is None else ISO_DATE.sub(DAY_FIRST_DATE, text)


def field_split_merge(html: str) -> str:
    """Split each single-value field into two elements, the way one column becomes two."""
    root = _parse(html)
    for node in _elements(root):
        words = (node.text or "").split()
        if len(node) or len(words) < 2:
            continue
        node.text = None
        node.extend(_parts(words))
    return _serialise(root)


def _parts(words: list[str]) -> list[HtmlElement]:
    """The first word and the rest, each in its own element."""
    return [
        _element("span", {"class": PART_CLASS}, words[0]),
        _element("span", {"class": PART_CLASS}, " ".join(words[1:])),
    ]


def wrapper_nesting(html: str) -> str:
    """Nest the content one level deeper, the way a layout rewrite adds a container."""
    root = _parse(html)
    host = _content_host(root)
    wrapper = _element(DIV_TAG, {"class": WRAPPER_CLASS})
    wrapper.extend(_children(host))
    host.append(wrapper)
    return _serialise(root)


def first_page(total: int) -> int:
    """How many rows the first page keeps once a listing of `total` rows is split."""
    return math.ceil(total / len(PAGE_NUMBERS))


def _repeating(root: HtmlElement) -> list[HtmlElement]:
    """The largest group of identical siblings on the page — the listing's rows.

    Structural rather than named, so the generator stays domain-free: a listing is
    whatever repeats most. A page with nothing repeating yields no rows and simply keeps
    all of them, which is what makes this safe on a one-row fragment.
    """
    groups = (_children(node) for node in _elements(root))
    return max((group for group in groups if _are_rows(group)), key=len, default=[])


def pagination(html: str) -> str:
    """Split the listing across pages: drop all but the first page, then add the page links.

    The rows a collector expects genuinely stop arriving, so the row count falls as well as
    the shape changing. That is what makes this the one class exercising the volume
    detector — appending navigation alone moves the skeleton hash and nothing else.
    """
    root = _parse(html)
    rows = _repeating(root)
    for row in rows[first_page(len(rows)) :]:
        row.getparent().remove(row)
    navigation = _element("nav", {"class": PAGINATION_CLASS})
    navigation.extend(
        _element("a", {"class": PAGE_CLASS, "href": f"?page={number}"}, str(number))
        for number in PAGE_NUMBERS
    )
    _place_pager(root, rows, navigation)
    return _serialise(root)


def _place_pager(root: HtmlElement, rows: list[HtmlElement], navigation: HtmlElement) -> None:
    """Put the pager immediately after the listing it pages, not at the end of the document.

    A pager appended to the body lands after whatever else the page carries — on a real
    layout, below the footer. Falls back to appending when there is no listing to sit
    beside, which is what a fragment with a single row has.
    """
    listing = rows[0].getparent() if rows else None
    anchor = None if listing is None else listing.getparent()
    if anchor is not None and anchor.getparent() is not None:
        anchor.addnext(navigation)
        return
    _content_host(root).append(navigation)


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        MutationClass.CLASS_RENAME,
        frozenset({SignalKind.SKELETON, SignalKind.ROW_COUNT}),
        class_rename,
    ),
    Mutation(
        MutationClass.TABLE_TO_DIV,
        frozenset({SignalKind.SKELETON, SignalKind.ROW_COUNT}),
        table_to_div,
    ),
    Mutation(MutationClass.COLUMN_REORDER, frozenset({SignalKind.SKELETON}), column_reorder),
    Mutation(MutationClass.LINK_LABEL, frozenset(), link_label),
    Mutation(MutationClass.URL_PATTERN, frozenset({SignalKind.SCHEMA, SignalKind.NULL_RATE}), url_pattern),
    Mutation(
        MutationClass.DATE_FORMAT,
        frozenset({SignalKind.SCHEMA, SignalKind.NULL_RATE}),
        date_format,
    ),
    Mutation(MutationClass.FIELD_SPLIT_MERGE, frozenset({SignalKind.SKELETON}), field_split_merge),
    Mutation(MutationClass.WRAPPER_NESTING, frozenset({SignalKind.SKELETON}), wrapper_nesting),
    Mutation(
        MutationClass.PAGINATION,
        frozenset({SignalKind.SKELETON, SignalKind.ROW_COUNT}),
        pagination,
    ),
)
