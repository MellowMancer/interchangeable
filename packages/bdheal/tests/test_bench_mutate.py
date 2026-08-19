"""The nine perturbations, pinned to golden output and to a declared detector.

Every assertion runs against one generic listing fragment. A benchmark whose fixtures
carry problem-domain words measures the corpus rather than the loop, so the fixture is
deliberately about "items" and nothing else, and one test reads the module source back to
prove no domain vocabulary crept in.

Two halves that look contradictory and are not (resolved decision Q2): the six structural
classes must move the F5 skeleton hash, and the three text or attribute classes must
leave it exactly where it was. `link_label` declaring `NONE` is the honest statement that
no detector sees it — a published gap, not a defect to hide by widening the hash.

The fixture's two columns differ in class (`td.name` vs `td.date`) on purpose: swapping
byte-identical siblings cannot move a structural hash, so a uniform-cell fixture would
fail `column_reorder` for a correct implementation.
"""

from pathlib import Path

import lxml.html
import pytest

from conftest import DOMAIN_TERMS
from lxml import etree

from bdheal.bench import mutate
from bdheal.bench.mutate import MUTATIONS, Mutation
from bdheal.skeleton import skeleton_hash
from bdheal.vocabulary import ExpectedSignal, MutationClass

FIXTURE = (
    '<div class="listing">'
    '<h2 class="title">Sample listing</h2>'
    '<table class="rows">'
    '<tr class="row">'
    '<td class="name"><a class="link" href="/items/1">First item</a></td>'
    '<td class="date">2026-01-01</td>'
    "</tr>"
    "</table>"
    "</div>"
)

# ARCHITECTURE.md §12, restated as an assertion rather than trusted.
DECLARED_SIGNAL = {
    MutationClass.CLASS_RENAME: ExpectedSignal.SKELETON,
    MutationClass.TABLE_TO_DIV: ExpectedSignal.SKELETON,
    MutationClass.COLUMN_REORDER: ExpectedSignal.SKELETON,
    MutationClass.FIELD_SPLIT_MERGE: ExpectedSignal.SKELETON,
    MutationClass.WRAPPER_NESTING: ExpectedSignal.SKELETON,
    MutationClass.PAGINATION: ExpectedSignal.SKELETON,
    MutationClass.DATE_FORMAT: ExpectedSignal.SCHEMA,
    MutationClass.URL_PATTERN: ExpectedSignal.SCHEMA_OR_NULL_RATE,
    MutationClass.LINK_LABEL: ExpectedSignal.NONE,
}
STRUCTURAL = frozenset(
    name for name, signal in DECLARED_SIGNAL.items() if signal is ExpectedSignal.SKELETON
)

GOLDEN = {
    MutationClass.CLASS_RENAME: (
        '<div class="x-listing">'
        '<h2 class="x-title">Sample listing</h2>'
        '<table class="x-rows">'
        '<tr class="x-row">'
        '<td class="x-name"><a class="x-link" href="/items/1">First item</a></td>'
        '<td class="x-date">2026-01-01</td>'
        "</tr>"
        "</table>"
        "</div>"
    ),
    MutationClass.TABLE_TO_DIV: (
        '<div class="listing">'
        '<h2 class="title">Sample listing</h2>'
        '<div class="rows">'
        '<div class="row">'
        '<div class="name"><a class="link" href="/items/1">First item</a></div>'
        '<div class="date">2026-01-01</div>'
        "</div>"
        "</div>"
        "</div>"
    ),
    MutationClass.COLUMN_REORDER: (
        '<div class="listing">'
        '<h2 class="title">Sample listing</h2>'
        '<table class="rows">'
        '<tr class="row">'
        '<td class="date">2026-01-01</td>'
        '<td class="name"><a class="link" href="/items/1">First item</a></td>'
        "</tr>"
        "</table>"
        "</div>"
    ),
    MutationClass.LINK_LABEL: (
        '<div class="listing">'
        '<h2 class="title">Sample listing</h2>'
        '<table class="rows">'
        '<tr class="row">'
        '<td class="name"><a class="link" href="/items/1">Details</a></td>'
        '<td class="date">2026-01-01</td>'
        "</tr>"
        "</table>"
        "</div>"
    ),
    MutationClass.URL_PATTERN: (
        '<div class="listing">'
        '<h2 class="title">Sample listing</h2>'
        '<table class="rows">'
        '<tr class="row">'
        '<td class="name"><a class="link" href="/v2/items/1?ref=list">First item</a></td>'
        '<td class="date">2026-01-01</td>'
        "</tr>"
        "</table>"
        "</div>"
    ),
    MutationClass.DATE_FORMAT: (
        '<div class="listing">'
        '<h2 class="title">Sample listing</h2>'
        '<table class="rows">'
        '<tr class="row">'
        '<td class="name"><a class="link" href="/items/1">First item</a></td>'
        '<td class="date">01/01/2026</td>'
        "</tr>"
        "</table>"
        "</div>"
    ),
    MutationClass.FIELD_SPLIT_MERGE: (
        '<div class="listing">'
        '<h2 class="title"><span class="part">Sample</span><span class="part">listing</span></h2>'
        '<table class="rows">'
        '<tr class="row">'
        '<td class="name"><a class="link" href="/items/1">'
        '<span class="part">First</span><span class="part">item</span></a></td>'
        '<td class="date">2026-01-01</td>'
        "</tr>"
        "</table>"
        "</div>"
    ),
    MutationClass.WRAPPER_NESTING: (
        '<div class="listing">'
        '<div class="wrap">'
        '<h2 class="title">Sample listing</h2>'
        '<table class="rows">'
        '<tr class="row">'
        '<td class="name"><a class="link" href="/items/1">First item</a></td>'
        '<td class="date">2026-01-01</td>'
        "</tr>"
        "</table>"
        "</div>"
        "</div>"
    ),
    MutationClass.PAGINATION: (
        '<div class="listing">'
        '<h2 class="title">Sample listing</h2>'
        '<table class="rows">'
        '<tr class="row">'
        '<td class="name"><a class="link" href="/items/1">First item</a></td>'
        '<td class="date">2026-01-01</td>'
        "</tr>"
        "</table>"
        '<nav class="pagination">'
        '<a class="page" href="?page=1">1</a>'
        '<a class="page" href="?page=2">2</a>'
        "</nav>"
        "</div>"
    ),
}

# Words from this project's problem domain. A generator that needs one is not corpus-free.


def _round_trip(html: str) -> str:
    """`html` serialised by the same parser the generators use, so a no-op is visible."""
    return lxml.html.tostring(lxml.html.fromstring(html), encoding="unicode")


def _mutation(name: MutationClass) -> Mutation:
    """The registered generator for `name`; a missing class fails the test that asked."""
    registered = {mutation.mutation: mutation for mutation in MUTATIONS}
    assert name in registered, f"no generator registered for {name}"
    return registered[name]


@pytest.mark.parametrize("name", list(MutationClass))
def test_there_is_one_generator_for_each_mutation_class(name: MutationClass) -> None:
    """Nine classes, nine callables — a missing class is a hole in the benchmark."""
    assert isinstance(_mutation(name).apply(FIXTURE), str)


def test_the_registry_holds_each_class_exactly_once() -> None:
    """A duplicate entry would run one class twice and score it twice."""
    assert [mutation.mutation for mutation in MUTATIONS] == list(MutationClass)


@pytest.mark.parametrize("name", list(MutationClass))
def test_every_output_reparses_cleanly_and_is_not_empty(name: MutationClass) -> None:
    """A mutated fixture that no parser accepts measures the parser, not the loop."""
    mutated = _mutation(name).apply(FIXTURE)
    parser = etree.HTMLParser(recover=False)
    parsed = etree.fromstring(mutated, parser)
    assert parsed is not None
    assert not parser.error_log
    assert mutated.strip()


@pytest.mark.parametrize("name", list(MutationClass))
def test_every_output_differs_from_its_input(name: MutationClass) -> None:
    """Compared against the round-tripped input, so re-serialisation cannot pass as a change."""
    mutated = _mutation(name).apply(FIXTURE)
    assert mutated != FIXTURE
    assert mutated != _round_trip(FIXTURE)


@pytest.mark.parametrize("name", list(MutationClass))
def test_every_output_matches_its_golden_fixture(name: MutationClass) -> None:
    """Byte-for-byte goldens: a generator that drifts fails here, not in a benchmark run."""
    assert _mutation(name).apply(FIXTURE) == GOLDEN[name]


@pytest.mark.parametrize("name", list(MutationClass))
def test_repeating_a_generator_returns_the_same_bytes(name: MutationClass) -> None:
    """Determinism: the same input twice gives the same output twice."""
    mutation = _mutation(name)
    assert mutation.apply(FIXTURE) == mutation.apply(FIXTURE)


@pytest.mark.parametrize("name", list(MutationClass))
def test_every_generator_declares_a_permitted_detector(name: MutationClass) -> None:
    """Q2: the declaration is data on the generator, and it is one of the four values."""
    declared = _mutation(name).expected_signal
    assert isinstance(declared, ExpectedSignal)
    assert declared == DECLARED_SIGNAL[name]


def test_link_label_declares_that_nothing_catches_it() -> None:
    """The published coverage gap, asserted so it cannot be quietly re-declared."""
    assert _mutation(MutationClass.LINK_LABEL).expected_signal is ExpectedSignal.NONE


@pytest.mark.parametrize("name", sorted(STRUCTURAL))
def test_structural_classes_move_the_skeleton_hash(name: MutationClass) -> None:
    """Six rebuilds of the tree; each one must be visible to the structural detector."""
    assert skeleton_hash(_mutation(name).apply(FIXTURE)) != skeleton_hash(FIXTURE)


@pytest.mark.parametrize("name", sorted(set(MutationClass) - STRUCTURAL))
def test_text_and_attribute_classes_leave_the_skeleton_hash_alone(name: MutationClass) -> None:
    """F5 is text-insensitive by contract; these three are other detectors' work."""
    assert skeleton_hash(_mutation(name).apply(FIXTURE)) == skeleton_hash(FIXTURE)


def test_no_generator_names_the_problem_domain() -> None:
    """A corpus word in a generator would make the benchmark unpublishable elsewhere."""
    source = Path(mutate.__file__).read_text().lower()
    for term in DOMAIN_TERMS:
        assert term not in source, term


def test_the_fixture_under_test_is_generic() -> None:
    """The generators are exercised on a made-up listing, never on a corpus page."""
    for term in DOMAIN_TERMS:
        assert term not in FIXTURE.lower(), term
