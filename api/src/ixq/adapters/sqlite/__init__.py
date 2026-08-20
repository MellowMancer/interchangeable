"""SQLite-backed persistence."""

from ixq.adapters.sqlite.repository import SqliteRepository, connect

__all__ = ["SqliteRepository", "connect"]
