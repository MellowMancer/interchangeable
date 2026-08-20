"""Typer entrypoints. The only module that knows the pipeline's stage order."""

import os
from pathlib import Path

import typer

from ixq.adapters.config import load_collectors, load_sources, load_substances
from ixq.adapters.sqlite import SqliteRepository, connect

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
