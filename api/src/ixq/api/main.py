"""FastAPI application. The seam between the pipeline and the UI.

The UI never opens SQLite: every shape it renders is a response model declared here, so
the domain can change without breaking a screen and vice versa.
"""

from collections.abc import Iterator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from bdheal.models import FailureClass, HealStatus
from bdheal.ports import HealStore
from bdheal.store import SqliteHealStore
from bdheal.store import connect as heal_connect

from ixq.adapters.config import load_collectors, load_sources, load_substances
from ixq.adapters.sqlite import SqliteRepository, connect
from ixq.domain import Document, Occurrence, Placement, variant
from ixq.pipeline.diverge import compare
from ixq.pipeline.ports import Repository, SubstanceCounts
from ixq.settings import config_dir, database_path, heal_database_path

app = FastAPI(title="Interchangeable?")

def repository() -> Iterator[Repository]:
    """A repository per request, because a SQLite connection belongs to one thread.

    FastAPI runs sync endpoints in a threadpool, so a connection cached for the process
    is used from whichever worker picks up the request and raises. Opening per request
    costs well under a millisecond and keeps each one thread-confined.
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


class SubstanceSummary(BaseModel):
    """A row of the landing list."""

    id: str
    name: str
    products: int
    concepts: int
    divergent: int


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
    empty = SubstanceCounts(products=0, concepts=0, divergent=0)
    return [
        SubstanceSummary(
            id=substance.id,
            name=substance.name,
            products=(counts := counted.get(substance.id, empty)).products,
            concepts=counts.concepts,
            divergent=counts.divergent,
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

    names = {s.id: s.name for s in load_substances(config_dir() / "substances.yaml")}
    return Matrix(
        substance_id=result.substance_id,
        substance_name=names.get(substance_id, substance_id),
        products=[
            ProductColumn(
                external_id=p.external_id,
                name=p.name,
                variant=variant(p.name),
                ma_holder=p.ma_holder,
                revised=(d.last_updated if (d := by_product.get(p.external_id)) else None),
                source_url=(d.source_url if (d := by_product.get(p.external_id)) else None),
                scanned=list(result.scanned.get(p.external_id, ())),
            )
            for p in result.products
        ],
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
