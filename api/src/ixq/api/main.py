"""FastAPI application. The seam between the pipeline and the UI.

The UI never opens SQLite: every shape it renders is a response model declared here, so
the domain can change without breaking a screen and vice versa.
"""

import os
from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from ixq.adapters.config import load_collectors, load_sources, load_substances
from ixq.adapters.sqlite import SqliteRepository, connect
from ixq.domain import Placement
from ixq.pipeline.diverge import compare
from ixq.pipeline.ports import Repository
from ixq.settings import database_path

app = FastAPI(title="Interchangeable?")

def _config_dir() -> Path:
    return Path(os.environ.get("IXQ_CONFIG_DIR", "api/config"))


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
    ma_holder: str | None = None
    revised: str | None = None
    source_url: str | None = None


class Matrix(BaseModel):
    """The comparison for one substance.

    `scanned` is required reading, not metadata: `absent` means absent from these
    sections, and a reader cannot judge an absence without knowing what was looked at.
    """

    substance_id: str
    scanned: list[str]
    products: list[ProductColumn]
    rows: list[Row]


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/substances", response_model=list[SubstanceSummary])
def substances(repo: Repository = Depends(repository)) -> list[SubstanceSummary]:
    """The roster, with how much of it has actually been collected."""
    summaries = []
    for substance in load_substances(_config_dir() / "substances.yaml"):
        result = compare(substance.id, repo)
        summaries.append(
            SubstanceSummary(
                id=substance.id,
                name=substance.name,
                products=len(result.products),
                concepts=len(result.rows),
                divergent=len(result.divergent),
            )
        )
    return summaries


@app.get("/substances/{substance_id}", response_model=Matrix)
def matrix(substance_id: str, repo: Repository = Depends(repository)) -> Matrix:
    """The comparison, with the evidence for every cell that has any."""
    result = compare(substance_id, repo)
    if not result.products:
        raise HTTPException(404, f"no labels stored for {substance_id!r}")

    by_product = {d.product_external_id: d for d in result.documents}
    quotes = _quotes(result, repo)

    return Matrix(
        substance_id=result.substance_id,
        scanned=list(result.scanned),
        products=[
            ProductColumn(
                external_id=p.external_id,
                name=p.name,
                ma_holder=p.ma_holder,
                revised=(d.last_updated if (d := by_product.get(p.external_id)) else None),
                source_url=(d.source_url if (d := by_product.get(p.external_id)) else None),
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
                        evidence=quotes.get((p.external_id, row.concept)),
                    )
                    for p in result.products
                ],
            )
            for row in sorted(result.rows, key=lambda r: (not r.diverges, r.concept))
        ],
    )


def _quotes(result, repo: Repository) -> dict[tuple[str, str], Evidence]:
    """One quote per (product, concept) — the strongest placement's, matching the cell."""
    by_sha = {d.sha256: d for d in result.documents}
    found: dict[tuple[str, str], Evidence] = {}
    for occurrence in repo.occurrences_for_substance(result.substance_id):
        document = by_sha.get(occurrence.document_sha256)
        if document is None:
            continue
        key = (document.product_external_id, occurrence.concept)
        if key not in found:
            found[key] = Evidence(
                quote=occurrence.quote,
                section_code=occurrence.section_code,
                char_start=occurrence.char_start,
                char_end=occurrence.char_end,
                source_url=document.source_url,
            )
    return found


@app.get("/collectors")
def collectors() -> list[dict[str, str]]:
    """What is configured to collect, and from where."""
    sources = {s.id: s.name for s in load_sources(_config_dir() / "sources.yaml")}
    return [
        {"id": c.id, "kind": c.kind.value, "source": sources.get(c.source_id, c.source_id)}
        for c in load_collectors(_config_dir() / "collectors.yaml")
    ]
