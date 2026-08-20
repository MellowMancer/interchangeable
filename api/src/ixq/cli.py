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
from ixq.pipeline.fetch import fetch

app = typer.Typer(help="Provenance-carrying comparison of product labels.")

DB_NAME = "interchangeable.db"


def _data_dir() -> Path:
    """Where the database lives."""
    return Path(os.environ.get("IXQ_DATA_DIR", "data"))


def _config_dir() -> Path:
    """Where operator-tunable YAML lives."""
    return Path(os.environ.get("IXQ_CONFIG_DIR", "config"))


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
