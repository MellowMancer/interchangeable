"""Where the database lives. Shared by every driver so they cannot disagree."""

import os
from pathlib import Path

DB_NAME = "interchangeable.db"
HEAL_DB_NAME = "bdheal.db"


def data_dir() -> Path:
    """The directory holding everything a run produces."""
    return Path(os.environ.get("IXQ_DATA_DIR", "data"))


def database_path() -> Path:
    """Path to the SQLite file the pipeline, API and MCP server all read."""
    return data_dir() / DB_NAME


def heal_database_path() -> Path:
    """Where `bdheal` keeps its baselines and heal events — a separate file, deliberately.

    They shared one file, and nothing joins across the boundary: `bdheal` declares no
    foreign key into these tables and this schema declares none into those. What sharing
    did buy was a single `PRAGMA user_version` governing both, owned by the app — so an
    app schema bump refused a file whose `bdheal` half was untouched and still valid, and
    the documented recovery ("delete it") destroyed heal history as collateral.

    That history is the only unregenerable data here. The corpus is expensive but can be
    re-fetched; that a collector broke and was healed on some past run cannot be re-derived
    from anything.
    """
    return data_dir() / HEAL_DB_NAME


def config_dir() -> Path:
    """Where operator-tunable YAML lives.

    Defaults to `api/config`, which is where it sits from the repo root and from the
    container's workdir. The config is deployment data, not packaged into the wheel, so
    there is no importable location to resolve it from.
    """
    return Path(os.environ.get("IXQ_CONFIG_DIR", "api/config"))
