"""Where the database lives. Shared by every driver so they cannot disagree."""

import os
from pathlib import Path

DB_NAME = "interchangeable.db"


def database_path() -> Path:
    """Path to the SQLite file the pipeline, API and MCP server all read."""
    return Path(os.environ.get("IXQ_DATA_DIR", "data")) / DB_NAME
