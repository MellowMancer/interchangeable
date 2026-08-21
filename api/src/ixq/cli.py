"""Typer entrypoints. The only module that knows the pipeline's stage order."""

from collections.abc import Sequence

import typer

from ixq.adapters.brightdata import label_source
from ixq.adapters.config import (
    load_collectors,
    load_concepts,
    load_sources,
    load_substances,
)
from ixq.adapters.sqlite import SCHEMA_VERSION, SqliteRepository, connect, migrate
from ixq.domain import Collector, CollectorKind
from ixq.pipeline.classify import classify_document
from ixq.pipeline.collect import collect, shortlist
from ixq.pipeline.diverge import compare
from ixq.pipeline.fetch import fetch
from ixq.pipeline.ports import CollectorMaintainer
from ixq.settings import config_dir, database_path

app = typer.Typer(help="Provenance-carrying comparison of product labels.")

@app.callback()
def main() -> None:
    """Keeps subcommand structure as stages are added; Typer would otherwise
    collapse a lone command into the root."""


@app.command()
def init() -> None:
    """Create the database, apply the schema, and load the rosters."""
    db_path = database_path()
    repository = SqliteRepository(connect(db_path))
    config = config_dir()

    sources = load_sources(config / "sources.yaml")
    substances = load_substances(config / "substances.yaml")
    collectors = load_collectors(config / "collectors.yaml")

    with repository.transaction():
        for source in sources:
            repository.save_source(source)
        for substance in substances:
            repository.save_substance(substance)
        for collector in collectors:
            repository.save_collector(collector)

    typer.echo(
        f"initialised {db_path} with {len(sources)} sources, "
        f"{len(substances)} substances and {len(collectors)} collectors"
    )


@app.command()
def upgrade() -> None:
    """Add the columns a newer build expects to an existing database, in place.

    The alternative `connect()` offers is refusing to open the file at all, and deleting
    it costs the whole corpus — hundreds of billable fetches this command does not spend.
    Only ever adds columns; anything else refuses and says why.
    """
    db_path = database_path()
    was = migrate(db_path, SCHEMA_VERSION)
    if was == SCHEMA_VERSION:
        typer.echo(f"{db_path} is already at schema version {SCHEMA_VERSION}")
        return
    typer.echo(
        f"{db_path} migrated from schema version {was} to {SCHEMA_VERSION}. "
        "Columns added by this step are NULL until the labels are re-fetched."
    )


@app.command()
def check() -> None:
    """Judge every configured collector against its anchor, and repair one that has moved.

    The same check `run` performs, without collecting anything. It exists because that is
    the only thing that captures a baseline, and pairing it with a full collection meant
    the reliability screen could not be populated without paying to re-fetch the corpus.

    Costs one anchor fetch per collector, and writes to `bdheal.db` — never the label
    database, so a schema change on one cannot disturb the other.
    """
    config = config_dir()
    sources = {s.id: s for s in load_sources(config / "sources.yaml")}
    collectors = load_collectors(config / "collectors.yaml")

    for source_id in sources:
        mine = [c for c in collectors if c.source_id == source_id]
        if not mine:
            continue
        by_kind = {c.kind: c.id for c in mine}
        typer.echo(f"{source_id}: checking {len(mine)} collectors")
        _check(label_source(database_path(), by_kind, mine), mine, heal=True)


@app.command()
def run(
    substance: str = typer.Option("", help="Only this substance id. Default: every one."),
    products: int = typer.Option(0, help="Cap products per substance. 0 means no cap."),
    heal: bool = typer.Option(
        True, help="Check each collector against its anchor and repair it if it has moved."
    ),
) -> None:
    """Collect products, fetch their labels, and classify what the labels say.

    Every collector call is billable, so `--products` exists to make a first run cheap:
    the whole roster is several hundred labels.

    The health check costs one fetch per collector against its stable anchor, which is
    also the only thing that captures a baseline — without it nothing is ever recorded and
    the reliability screen stays empty however many runs happen.
    """
    config = config_dir()
    repository = SqliteRepository(connect(database_path()))

    sources = {s.id: s for s in load_sources(config / "sources.yaml")}
    substances = load_substances(config / "substances.yaml")
    concepts = load_concepts(config / "concepts.yaml")
    collectors = load_collectors(config / "collectors.yaml")
    if substance:
        substances = [s for s in substances if s.id == substance]
        if not substances:
            raise typer.BadParameter(f"no substance {substance!r} in the roster")

    for source_id, source in sources.items():
        by_kind = {c.kind: c.id for c in collectors if c.source_id == source_id}
        missing = {CollectorKind.SEARCH, CollectorKind.PRODUCT} - set(by_kind)
        if missing:
            raise typer.BadParameter(
                f"source {source_id!r} has no {', '.join(sorted(k.value for k in missing))} "
                "collector configured"
            )
        mine = [c for c in collectors if c.source_id == source_id]
        labels = label_source(database_path(), by_kind, mine)
        _check(labels, mine, heal=heal)

        for item in substances:
            with repository.transaction():
                repository.save_source(source)
                found = collect(item, source, by_kind[CollectorKind.SEARCH], labels, repository)
            chosen = shortlist(found, products)
            holders = len({p.ma_holder or p.external_id for p in chosen})
            typer.echo(
                f"{item.id}: {len(found)} products, fetching {len(chosen)} "
                f"from {holders} manufacturers"
            )

            for product in chosen:
                try:
                    _one_label(product, source, by_kind, labels, concepts, repository)
                except Exception as failure:  # noqa: BLE001 — one label must not end the run
                    # A run is hundreds of billable fetches. Losing all of them to one
                    # unparseable page would mean paying for them twice, and a partial
                    # corpus is visible in the comparison while a crashed run is not.
                    typer.echo(f"  {product.external_id}: FAILED — {failure}")


def _check(
    labels: CollectorMaintainer, collectors: Sequence[Collector], *, heal: bool
) -> None:
    """Judge each collector against its anchor before spending a fetch per product.

    A break found here is reported and not raised: one moved collector should not stop the
    others, and a partial corpus is visible in the comparison while a crashed run is not.
    That has to be enforced, not just intended — the collector library raises on a refused
    target, and letting it through would lose the whole run to one flaky page.
    """
    if not heal:
        typer.echo("skipping the collector health check (--no-heal)")
        return
    for collector in collectors:
        try:
            check = labels.ensure_healthy(collector.id)
        except Exception as failure:  # noqa: BLE001 — the boundary this docstring promises
            typer.echo(f"  {collector.id}: health check failed — {failure}")
            continue
        if check.promoted_unverified:
            typer.echo(f"  {collector.id}: healed, UNVERIFIED — {check.reason}")
        elif check.healed:
            typer.echo(f"  {collector.id}: was broken, healed and verified")
        elif check.broken:
            typer.echo(f"  {collector.id}: BROKEN — {check.reason}")
        elif check.reason:
            typer.echo(f"  {collector.id}: not checked — {check.reason}")
        else:
            # Said out loud: a silent healthy pass is indistinguishable from a command
            # that did nothing, and this is the one that captures the baseline.
            typer.echo(f"  {collector.id}: healthy — baseline captured")


def _one_label(product, source, by_kind, labels, concepts, repository) -> None:
    """Fetch and classify one label. One product is one unit of work."""
    with repository.transaction():
        document = fetch(product, source, by_kind[CollectorKind.PRODUCT], labels, repository)
        if document is None:
            typer.echo(f"  {product.external_id}: no usable label")
            return
        found = classify_document(document.sha256, repository, concepts)
    typer.echo(f"  {product.external_id}: {found} occurrences")


@app.command()
def reclassify(
    substance: str = typer.Option("", help="Only this substance id. Default: every one."),
) -> None:
    """Re-derive every finding from the sections already stored. Costs nothing.

    Sections are kept verbatim, so what a clause is and what concept it carries can both
    be recomputed from them — a change to the clause splitter or the lexicon does not need
    the corpus fetched again. `run` would re-fetch it, which is billable and, for a
    question already answered by stored bytes, pointless.

    One transaction per document, because clearing a document's findings and re-deriving
    them is one unit of work.
    """
    config = config_dir()
    repository = SqliteRepository(connect(database_path()))
    concepts = load_concepts(config / "concepts.yaml")

    substances = load_substances(config / "substances.yaml")
    if substance:
        substances = [s for s in substances if s.id == substance]
        if not substances:
            raise typer.BadParameter(f"no substance {substance!r} in the roster")

    for item in substances:
        documents = repository.documents_for_substance(item.id)
        if not documents:
            continue
        total = 0
        for document in documents:
            with repository.transaction():
                total += classify_document(document.sha256, repository, concepts)
        typer.echo(f"{item.id}: {len(documents)} labels, {total} occurrences")


@app.command()
def matrix(substance: str = typer.Argument(..., help="Substance id, e.g. ramipril")) -> None:
    """Show where the manufacturers of one substance disagree.

    Reads only what is already stored — no collector calls, nothing billable.
    """
    repository = SqliteRepository(connect(database_path()))
    result = compare(substance, repository)
    if not result.products:
        typer.echo(f"no labels stored for {substance!r} — run `ixq run --substance {substance}`")
        raise typer.Exit(1)

    holders = [p.ma_holder or p.external_id for p in result.products]
    width = max(len(r.concept) for r in result.rows) + 2 if result.rows else 12
    typer.echo(f"\n{substance}")
    for product in result.products:
        read = ", ".join(result.scanned.get(product.external_id, ())) or "nothing"
        typer.echo(f"  {product.ma_holder or product.external_id} — sections read: {read}")
    typer.echo("(absent means absent from those sections, not from the label)\n")
    typer.echo(" " * width + "  ".join(h[:16].ljust(16) for h in holders))
    for row in sorted(result.rows, key=lambda r: (not r.diverges, r.concept)):
        cells = "  ".join(
            row.placements[p.external_id].value.ljust(16) for p in result.products
        )
        mark = "  <-- differs" if row.diverges else ""
        typer.echo(f"{row.concept.ljust(width)}{cells}{mark}")

    typer.echo(f"\n{len(result.divergent)} of {len(result.rows)} concepts differ")
    for document in result.documents:
        product = next(p for p in result.products if p.external_id == document.product_external_id)
        typer.echo(f"  {(product.ma_holder or ''):<34} revised {document.last_updated or 'unknown'}")
