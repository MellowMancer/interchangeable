"""FastAPI application. The seam between the pipeline and the UI.

The UI never opens SQLite: every shape it renders is a response model declared here, so
the domain can change without breaking a screen and vice versa.
"""

from collections.abc import Iterator, Mapping

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from bdheal.models import FailureClass, HealStatus
from bdheal.ports import HealStore
from bdheal.store import SqliteHealStore
from bdheal.store import connect as heal_connect

from ixq.adapters.config import load_collectors, load_sources, load_substances
from ixq.adapters.sqlite import SqliteRepository, connect
from ixq.domain import Document, Occurrence, Placement, described_in, in_context, variant
from ixq.pipeline.diverge import Comparison, ConceptRow, compare
from ixq.pipeline.ports import Repository, SubstanceCounts
from ixq.settings import bench_database_path, config_dir, database_path, heal_database_path

app = FastAPI(title="Interchangeable?")

def repository() -> Iterator[Repository]:
    """A repository per request, so no two requests share a connection.

    FastAPI runs sync endpoints in a threadpool, so a connection cached for the process
    is used from whichever worker picks up the request and raises. Opening per request
    costs well under a millisecond and confines each connection to one request — not to
    one thread: this dependency's setup and the endpoint body run in different workers,
    which is why `connect` passes `check_same_thread=False`.
    """
    conn = connect(database_path())
    try:
        yield SqliteRepository(conn)
    finally:
        conn.close()


def heal_store() -> Iterator[HealStore]:
    """The `bdheal` store per request, thread-confined for the same reason as `repository`."""
    conn = heal_connect(heal_database_path())
    try:
        yield SqliteHealStore(conn)
    finally:
        conn.close()


def bench_store() -> Iterator[HealStore]:
    """The benchmark's own store, thread-confined for the same reason as `repository`."""
    conn = heal_connect(bench_database_path())
    try:
        yield SqliteHealStore(conn)
    finally:
        conn.close()


class DivergencePreview(BaseModel):
    """One disagreement, named but not evidenced.

    Concept and placements only. The index screen previews every substance at once, so
    quotes are deliberately absent: they would multiply the payload by the corpus and are
    one click away on the comparison itself.
    """

    concept: str
    placements: list[str]


class SubstanceSummary(BaseModel):
    """A row of the landing list."""

    id: str
    name: str
    products: int
    concepts: int
    divergent: int
    divergences: list[DivergencePreview] = []


class Evidence(BaseModel):
    """Why a cell says what it says. Verifiable against the source document."""

    quote: str
    section_code: str
    char_start: int
    char_end: int
    source_url: str


class Cell(BaseModel):
    """One manufacturer's position on one concept."""

    product_external_id: str
    placement: Placement
    evidence: Evidence | None = None


class Row(BaseModel):
    """One concept across every manufacturer."""

    concept: str
    diverges: bool
    cells: list[Cell]


class AppearanceView(BaseModel):
    """What one manufacturer says its product looks like, and what parsed out of it.

    `source_text` is §3 verbatim and is always present, so a description the parser could
    not read is still published — the same rule `unclassified` obeys for clauses. What a
    consumer draws from `shape` and `colours` is a drawing derived from that text and
    must be presented as one: no photograph of any product in this corpus exists.

    `length_mm` and `width_mm` are `None` on a label that states no dimensions. That is
    unknown, never a size to be borrowed from a product that does state one.
    """

    source_text: str
    shape: str | None = None
    colours: list[str] = []
    length_mm: float | None = None
    width_mm: float | None = None
    imprints: list[str] = []
    unparsed: list[str] = []
    """What could not be read, named. Empty is "fully parsed", not "nothing to say"."""


class ProductColumn(BaseModel):
    """A column of the matrix, with the context needed to read it."""

    external_id: str
    name: str
    variant: str | None = None
    """Strength and form, e.g. `2.5mg Capsules`. `None` when the name does not carry both.

    A manufacturer may authorise several strengths of one substance, each with its own
    label. Heading those columns by manufacturer alone makes them identical to read.
    """

    ma_holder: str | None = None
    revised: str | None = None
    source_url: str | None = None
    scanned: list[str] = []
    """Sections read for *this* label. An absence in this column means absent from these.

    Per column rather than per matrix: a product whose §4.5 came back empty was never
    scanned for 4.5, and saying otherwise claims a scope that does not exist for it.
    """

    appearance: AppearanceView | None = None
    """§3, when the label has one stored. Product metadata, never part of the comparison.

    Carried on the column because it is per product and it is small — a line of prose and
    a handful of parsed fields, once per manufacturer. What must not be attached here is
    anything that scales with the *rows*: that is the regression `counts_by_substance`
    exists to undo, and this does not do it.

    Deliberately absent from `scanned`, which is the scope every absence claim is measured
    against. §3 is not somewhere a safety concept could have been found.
    """


class ClauseCoverage(BaseModel):
    """How many stored clauses the lexicon matched, and how many it did not.

    Two counts, never a ratio: a percentage would read as a claim about the lexicon's
    recall in general, which one substance cannot support.
    """

    classified: int
    unclassified: int


class Matrix(BaseModel):
    """The comparison for one substance.

    Each column carries the sections read for it — required reading, not metadata:
    `absent` means absent from those sections, and a reader cannot judge an absence
    without knowing what was looked at.
    """

    substance_id: str
    substance_name: str
    """Carried here so a screen showing one concept needs only this response.

    The roster endpoint recomputes every substance's comparison to produce its counts, so
    fetching it for a display name costs the whole roster to render one back-link.
    """

    products: list[ProductColumn]
    rows: list[Row]
    clauses: ClauseCoverage
    """The recall gap, carried with the comparison it belongs to.

    Two counts rather than a ratio: a percentage would read as a claim about the lexicon's
    recall in general, which one substance's corpus cannot support.
    """


class ContextWindow(BaseModel):
    """The stored section text around one quote, with the quote's span inside it.

    A window rather than the whole section, and only on this endpoint. `GET
    /substances/{id}` carries every cell of every row, so section bodies there would be
    read once per concept per product on every navigation — the regression
    `counts_by_substance` exists to undo.

    Offsets are relative to `text`, so the screen highlights by slicing. Re-finding the
    quote by searching the window instead marks the wrong instance wherever a clause
    repeats within a section, and the highlight then sits on a sentence the cell does not
    quote. The absolute offsets stay on `Evidence`, and `char_start - quote_start` is
    where this window begins in the section.

    `truncated_start` and `truncated_end` say which ends were cut. Unmarked, a window
    that stops mid-sentence reads as a section that ends there — an invitation to
    conclude the label says nothing further, which is the one claim this project refuses
    to make.
    """

    text: str
    quote_start: int
    quote_end: int
    truncated_start: bool
    truncated_end: bool
    section_length: int


class ConceptCell(Cell):
    """A matrix cell with the label text its quote was sliced from.

    `context` is `None` in exactly the cases `evidence` is. A cell with no match has no
    text to surround, and an empty window rendered in the same frame as a real one would
    make an absence look like something that was read and found wanting. What an absence
    is defensible against is `scanned` on the column, never a window.
    """

    context: ContextWindow | None = None


class ConceptDetail(BaseModel):
    """One concept across every manufacturer, each quote shown where it was found.

    Its own endpoint rather than a field on `Matrix`: the matrix answers for every
    concept at once, so section text attached there is paid for the whole grid to render
    the one cell a reader opened.

    Self-contained, so the screen makes one request. The columns travel with the cells
    because `absent` cannot be read without the sections scanned for that column, and
    fetching the matrix alongside for them would give back everything the split saved.
    """

    substance_id: str
    substance_name: str
    concept: str
    diverges: bool
    products: list[ProductColumn]
    cells: list[ConceptCell]


CONTEXT_RADIUS = 400
"""Characters of section text shown either side of a quote.

Enough to carry the sentences a clause sits between, which is the whole reason to open
the screen, and bounded so a §4.4 running to several kilobytes never arrives whole.
"""


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/substances", response_model=list[SubstanceSummary])
def substances(repo: Repository = Depends(repository)) -> list[SubstanceSummary]:
    """The roster, with how much of it has actually been collected.

    Counted in storage rather than by building each comparison. Every screen reads this,
    so the previous shape — one full `compare()` per substance, reading all the section
    text and quotes to return three integers — was paid on every navigation.
    """
    counted = repo.counts_by_substance()
    diverging = repo.divergences_by_substance()
    empty = SubstanceCounts(products=0, concepts=0, divergent=0)
    return [
        SubstanceSummary(
            id=substance.id,
            name=substance.name,
            products=(counts := counted.get(substance.id, empty)).products,
            concepts=counts.concepts,
            divergent=counts.divergent,
            divergences=[
                DivergencePreview(concept=d.concept, placements=list(d.placements))
                for d in diverging.get(substance.id, ())
            ],
        )
        for substance in load_substances(config_dir() / "substances.yaml")
    ]


@app.get("/substances/{substance_id}", response_model=Matrix)
def matrix(substance_id: str, repo: Repository = Depends(repository)) -> Matrix:
    """The comparison, with the evidence for every cell that has any."""
    result = compare(substance_id, repo)
    if not result.products:
        raise HTTPException(404, f"no labels stored for {substance_id!r}")

    by_product = {d.product_external_id: d for d in result.documents}

    counted = repo.clause_counts(substance_id)
    return Matrix(
        substance_id=result.substance_id,
        substance_name=_substance_name(substance_id),
        products=_columns(result, repo.appearances_for_substance(substance_id)),
        clauses=ClauseCoverage(
            classified=counted.classified, unclassified=counted.unclassified
        ),
        rows=[
            Row(
                concept=row.concept,
                diverges=row.diverges,
                cells=[
                    Cell(
                        product_external_id=p.external_id,
                        placement=row.placements[p.external_id],
                        evidence=_evidence(
                            row.evidence.get(p.external_id),
                            by_product.get(p.external_id),
                        ),
                    )
                    for p in result.products
                ],
            )
            for row in sorted(result.rows, key=lambda r: (not r.diverges, r.concept))
        ],
    )


def _evidence(occurrence: Occurrence | None, document: Document | None) -> Evidence | None:
    """The quote behind one cell.

    Both arguments come from the caller's own loop over `(product, concept)`. Nothing is
    looked up again: `compare` already paired every occurrence with the document it
    belongs to, and re-deriving that pairing here is how a placement and its quote came
    from two different revisions of the same label.
    """
    if occurrence is None or document is None:
        return None
    return Evidence(
        quote=occurrence.quote,
        section_code=occurrence.section_code,
        char_start=occurrence.char_start,
        char_end=occurrence.char_end,
        source_url=document.source_url,
    )


def _columns(result: Comparison, described: Mapping[str, str]) -> list[ProductColumn]:
    """The columns of a comparison, each carrying the sections scanned for its own label.

    `described` is keyed by document sha, not by product, so the appearance shown is the
    one belonging to the revision the comparison is built from. Keyed by product it could
    survive a revision the rest of the column has moved past, and the reader would be
    looking at a picture of a product the current label no longer describes.
    """
    by_product = {d.product_external_id: d for d in result.documents}
    return [
        ProductColumn(
            external_id=p.external_id,
            name=p.name,
            variant=variant(p.name),
            ma_holder=p.ma_holder,
            revised=(d.last_updated if (d := by_product.get(p.external_id)) else None),
            source_url=(d.source_url if (d := by_product.get(p.external_id)) else None),
            scanned=list(result.scanned.get(p.external_id, ())),
            appearance=_appearance(
                described.get(d.sha256) if (d := by_product.get(p.external_id)) else None
            ),
        )
        for p in result.products
    ]


def _appearance(section_text: str | None) -> AppearanceView | None:
    """§3 parsed for display, or None when no §3 is stored for this label.

    None is "nothing was collected", which is not "described but not drawn" — a label
    nobody has fetched a description for must render as no claim at all, never as a gap
    in the manufacturer's own labelling.
    """
    if section_text is None:
        return None
    found = described_in(section_text)
    return AppearanceView(
        source_text=found.source_text,
        shape=found.shape.value if found.shape else None,
        colours=list(found.colours),
        length_mm=found.length_mm,
        width_mm=found.width_mm,
        imprints=list(found.imprints),
        unparsed=list(found.unparsed),
    )


def _substance_name(substance_id: str) -> str:
    """The display name from the configured roster, or the id when it names no such one."""
    names = {s.id: s.name for s in load_substances(config_dir() / "substances.yaml")}
    return names.get(substance_id, substance_id)


@app.get("/substances/{substance_id}/concepts/{concept}", response_model=ConceptDetail)
def concept(
    substance_id: str, concept: str, repo: Repository = Depends(repository)
) -> ConceptDetail:
    """One concept's row, each quote surrounded by the stored text it was sliced from.

    Section text is read here and nowhere else. Reading it in the matrix instead would
    attach a label body to every cell of every row — the shape `counts_by_substance` was
    introduced to undo, where one screen paid for the whole corpus to show one thing.
    Bounded here by the products of one substance, so the cost tracks what is on screen.

    A concept nothing matched is a 404 against *the sections scanned*, never a statement
    that the labels omit it.
    """
    result = compare(substance_id, repo)
    if not result.products:
        raise HTTPException(404, f"no labels stored for {substance_id!r}")

    row = next((r for r in result.rows if r.concept == concept), None)
    if row is None:
        raise HTTPException(
            404, f"{concept!r} was not matched in any section scanned for {substance_id!r}"
        )

    by_product = {d.product_external_id: d for d in result.documents}
    return ConceptDetail(
        substance_id=result.substance_id,
        substance_name=_substance_name(substance_id),
        concept=row.concept,
        diverges=row.diverges,
        products=_columns(result, repo.appearances_for_substance(substance_id)),
        cells=[
            _concept_cell(row, p.external_id, by_product.get(p.external_id), repo)
            for p in result.products
        ],
    )


def _concept_cell(
    row: ConceptRow, external_id: str, document: Document | None, repo: Repository
) -> ConceptCell:
    """One manufacturer's cell, with the surroundings of the quote that set it.

    The window is built only where the evidence is, so the two can never disagree about
    whether this cell has a source: a window beside a missing quote would dress an
    absence up as something read and rejected.
    """
    occurrence = row.evidence.get(external_id)
    evidence = _evidence(occurrence, document)
    return ConceptCell(
        product_external_id=external_id,
        placement=row.placements[external_id],
        evidence=evidence,
        context=_context(occurrence, repo) if evidence else None,
    )


def _context(occurrence: Occurrence | None, repo: Repository) -> ContextWindow | None:
    """The stored section text around one quote, read one section at a time.

    Fetched by the occurrence's own document and code rather than by re-deriving them:
    those are the coordinates the quote was sliced at, so the window cannot come from a
    section other than the one the offsets address.
    """
    if occurrence is None:
        return None
    text = repo.section_text(occurrence.document_sha256, occurrence.section_code)
    if text is None:
        return None
    found = in_context(text, occurrence, CONTEXT_RADIUS)
    return ContextWindow(
        text=found.text,
        quote_start=found.quote_start,
        quote_end=found.quote_end,
        truncated_start=found.truncated_start,
        truncated_end=found.truncated_end,
        section_length=found.section_length,
    )


class Heal(BaseModel):
    """One trip through the Bright Data heal gate, as the reliability screen shows it."""

    status: HealStatus
    created_at: str
    promoted: bool
    failure_class: FailureClass | None = None
    attempts: int
    error: str | None = None


class CollectorHealth(BaseModel):
    """A collector's configuration and what `bdheal` remembers about it.

    `baseline_captured_at` is `None` before a collector's first run — that is "not yet
    observed", not "healthy". The screen must not render the two the same way.
    """

    id: str
    kind: str
    source: str
    baseline_captured_at: str | None = None
    baseline_row_count: int | None = None
    heals: list[Heal] = []


@app.get("/collectors", response_model=list[CollectorHealth])
def collectors(store: HealStore = Depends(heal_store)) -> list[CollectorHealth]:
    """What is configured to collect, and how each one has been holding up."""
    sources = {s.id: s.name for s in load_sources(config_dir() / "sources.yaml")}
    health = []
    for collector in load_collectors(config_dir() / "collectors.yaml"):
        baseline = store.baseline(collector.id)
        health.append(
            CollectorHealth(
                id=collector.id,
                kind=collector.kind.value,
                source=sources.get(collector.source_id, collector.source_id),
                baseline_captured_at=baseline.captured_at.isoformat() if baseline else None,
                baseline_row_count=baseline.row_count if baseline else None,
                heals=[
                    Heal(
                        status=event.status,
                        created_at=event.created_at.isoformat(),
                        promoted=event.promoted,
                        failure_class=event.failure_class,
                        attempts=event.attempts,
                        error=event.error,
                    )
                    for event in reversed(store.heal_events(collector.id))
                ],
            )
        )
    return health


class BenchCase(BaseModel):
    """One mutation case's outcome on the controlled fixture site.

    Every field is reported, including the ones that record a failure. A case the
    detector missed, or caught but could not repair, is the coverage gap the benchmark
    exists to publish — filtering to the successes would make this endpoint a claim
    rather than a measurement.

    `caught_by` is `None` when nothing fired. `healed` false with `field_accuracy` and
    `non_regression_passed` both `None` means the repair was never scored, which is not
    the same as scoring zero.
    """

    case_id: str
    mutation: str
    expected_signals: list[str]
    caught_by: str | None = None
    fired_kinds: list[str] = []
    healed: bool
    field_accuracy: float | None = None
    non_regression_passed: bool | None = None
    attempts: int
    elapsed_s: float
    completed_at: str | None = None


class BenchRun(BaseModel):
    """One benchmark run, with every case it recorded."""

    run_id: str
    cases: list[BenchCase]


@app.get("/benchmark", response_model=list[BenchRun])
def benchmark(store: HealStore = Depends(bench_store)) -> list[BenchRun]:
    """How the heal loop scored against a site broken on cue.

    `medicines.org.uk` cannot be mutated to order, so the repair loop is measured against
    a fixture site instead. Read from `bench.db`, never from `bdheal.db`: a rehearsal and
    a production incident must not arrive through the same route.

    Every run is returned, oldest first, rather than one named here. Naming a run would
    let this endpoint publish the flattering half of a benchmark whose other half is
    sitting in the same file.
    """
    return [
        BenchRun(
            run_id=run_id,
            cases=[
                BenchCase(
                    case_id=case.case_id,
                    mutation=case.mutation.value,
                    expected_signals=sorted(s.value for s in case.expected_signals),
                    caught_by=case.caught_by.value if case.caught_by else None,
                    fired_kinds=sorted(s.value for s in case.fired_kinds),
                    healed=case.healed,
                    field_accuracy=case.field_accuracy,
                    non_regression_passed=case.non_regression_passed,
                    attempts=case.attempts,
                    elapsed_s=case.elapsed_s,
                    completed_at=case.completed_at.isoformat() if case.completed_at else None,
                )
                for case in store.bench_cases(run_id)
            ],
        )
        for run_id in store.bench_runs()
    ]
