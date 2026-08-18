"""SQLite-backed persistence."""

from preward.adapters.sqlite.repository import SqliteRepository, connect

__all__ = ["SqliteRepository", "connect"]
