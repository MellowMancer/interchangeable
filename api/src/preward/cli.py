"""Typer entrypoints. The only module that knows the pipeline's stage order."""

import os
from pathlib import Path

import typer

from preward.adapters.config import load_sources, load_substances
from preward.adapters.sqlite import SqliteRepository, connect

app = typer.Typer(help="Provenance-carrying comparison of product labels.")

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
    """Create the database, apply the schema, and load the rosters."""
    db_path = _data_dir() / DB_NAME
    repository = SqliteRepository(connect(db_path))
    config_dir = _config_dir()

    sources = load_sources(config_dir / "sources.yaml")
    for source in sources:
        repository.save_source(source)

    substances = load_substances(config_dir / "substances.yaml")
    for substance in substances:
        repository.save_substance(substance)

    typer.echo(
        f"initialised {db_path} with {len(sources)} sources and {len(substances)} substances"
    )
