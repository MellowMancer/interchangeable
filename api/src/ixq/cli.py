"""Typer entrypoints. The only module that knows the pipeline's stage order."""

import os
from pathlib import Path

import typer

from ixq.adapters.brightdata import label_source
from ixq.adapters.config import (
    load_collectors,
    load_concepts,
    load_sources,
    load_substances,
)
from ixq.adapters.sqlite import SqliteRepository, connect
from ixq.domain import CollectorKind
from ixq.pipeline.classify import classify
from ixq.pipeline.collect import collect
from ixq.pipeline.diverge import compare
from ixq.pipeline.fetch import fetch

app = typer.Typer(help="Provenance-carrying comparison of product labels.")

DB_NAME = "interchangeable.db"


def _data_dir() -> Path:
    """Where the database lives."""
    return Path(os.environ.get("IXQ_DATA_DIR", "data"))


def _config_dir() -> Path:
    """Where operator-tunable YAML lives.

    Defaults to `api/config`, which is where it sits from the repo root and from the
    container's workdir. The config is deployment data, not packaged into the wheel, so
    there is no importable location to resolve it from.
    """
    return Path(os.environ.get("IXQ_CONFIG_DIR", "api/config"))


@app.callback()
def main() -> None:
    """Keeps subcommand structure as stages are added; Typer would otherwise
    collapse a lone command into the root."""


@app.command()
def init() -> None:
    """Create the database, apply the schema, and load the rosters."""
    db_path = _data_dir() / DB_NAME
    repository = SqliteRepository(connect(db_path))
    config_dir = _config_dir()

    sources = load_sources(config_dir / "sources.yaml")
    substances = load_substances(config_dir / "substances.yaml")
    collectors = load_collectors(config_dir / "collectors.yaml")

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
def run(
    substance: str = typer.Option("", help="Only this substance id. Default: every one."),
    products: int = typer.Option(0, help="Cap products per substance. 0 means no cap."),
) -> None:
    """Collect products, fetch their labels, and classify what the labels say.

    Every collector call is billable, so `--products` exists to make a first run cheap:
    the whole roster is several hundred labels.
    """
    config_dir = _config_dir()
    repository = SqliteRepository(connect(_data_dir() / DB_NAME))

    sources = {s.id: s for s in load_sources(config_dir / "sources.yaml")}
    substances = load_substances(config_dir / "substances.yaml")
    concepts = load_concepts(config_dir / "concepts.yaml")
    collectors = load_collectors(config_dir / "collectors.yaml")
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
        labels = label_source(_data_dir() / DB_NAME, by_kind)

        for item in substances:
            with repository.transaction():
                repository.save_source(source)
                found = collect(item, source, by_kind[CollectorKind.SEARCH], labels, repository)
            chosen = found[:products] if products else found
            typer.echo(f"{item.id}: {len(found)} products, fetching {len(chosen)}")

            for product in chosen:
                _one_label(product, source, by_kind, labels, concepts, repository)


def _one_label(product, source, by_kind, labels, concepts, repository) -> None:
    """Fetch and classify one label. One product is one unit of work."""
    with repository.transaction():
        document = fetch(product, source, by_kind[CollectorKind.PRODUCT], labels, repository)
        if document is None:
            typer.echo(f"  {product.external_id}: no rows")
            return
        found = 0
        for section in repository.sections_for_document(document.sha256):
            for occurrence in classify(section, document.sha256, concepts):
                repository.save_occurrence(occurrence)
                found += 1
    typer.echo(f"  {product.external_id}: {found} occurrences")


@app.command()
def matrix(substance: str = typer.Argument(..., help="Substance id, e.g. ramipril")) -> None:
    """Show where the manufacturers of one substance disagree.

    Reads only what is already stored — no collector calls, nothing billable.
    """
    repository = SqliteRepository(connect(_data_dir() / DB_NAME))
    result = compare(substance, repository)
    if not result.products:
        typer.echo(f"no labels stored for {substance!r} — run `ixq run --substance {substance}`")
        raise typer.Exit(1)

    holders = [p.ma_holder or p.external_id for p in result.products]
    width = max(len(r.concept) for r in result.rows) + 2 if result.rows else 12
    typer.echo(f"\n{substance} — sections scanned: {', '.join(result.scanned)}")
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
