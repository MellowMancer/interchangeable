"""Typer entrypoints. The only module that knows the pipeline's stage order."""

import os
from pathlib import Path

import typer

from preward.adapters.config import load_sources
from preward.adapters.sqlite import SqliteRepository, connect

app = typer.Typer(help="Tiered, provenance-carrying signal extraction from documents.")

DB_NAME = "rf.db"


def _data_dir() -> Path:
    """Where the database and fetched artifacts live."""
    return Path(os.environ.get("PREWARD_DATA_DIR", "data"))


def _config_dir() -> Path:
    """Where operator-tunable YAML lives."""
    return Path(os.environ.get("PREWARD_CONFIG_DIR", "config"))


@app.callback()
def main() -> None:
    """Keeps subcommand structure as stages are added; Typer would otherwise
    collapse a lone command into the root."""


@app.command()
def init() -> None:
    """Create the database, apply the schema, and load the source roster."""
    db_path = _data_dir() / DB_NAME
    repository = SqliteRepository(connect(db_path))

    sources = load_sources(_config_dir() / "sources.yaml")
    for source in sources:
        repository.save_source(source)

    typer.echo(f"initialised {db_path} with {len(sources)} sources")
