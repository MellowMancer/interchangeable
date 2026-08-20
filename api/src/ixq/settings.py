"""Where the database lives. Shared by every driver so they cannot disagree."""

import os
from pathlib import Path

DB_NAME = "interchangeable.db"


def database_path() -> Path:
    """Path to the SQLite file the pipeline, API and MCP server all read."""
    return Path(os.environ.get("IXQ_DATA_DIR", "data")) / DB_NAME


def config_dir() -> Path:
    """Where operator-tunable YAML lives.

    Defaults to `api/config`, which is where it sits from the repo root and from the
    container's workdir. The config is deployment data, not packaged into the wheel, so
    there is no importable location to resolve it from.
    """
    return Path(os.environ.get("IXQ_CONFIG_DIR", "api/config"))
