"""The migration exists to protect a corpus of billable fetches. It is tested as such."""

import sqlite3
from pathlib import Path

import pytest

from ixq.adapters.sqlite import SCHEMA_VERSION, connect, migrate
from ixq.adapters.sqlite.migrate import ADDED

V3_DOCUMENTS = (
    "CREATE TABLE documents ("
    "sha256 TEXT PRIMARY KEY, source_id TEXT, product_external_id TEXT, "
    "source_url TEXT, title TEXT, active_substance TEXT, last_updated TEXT, "
    "fetched_at TEXT NOT NULL)"
)
"""The v3 shape of the only table v4 changes, reduced to what the migration touches."""


def _v3(path: Path, rows: int = 1) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(f"PRAGMA user_version = 3; {V3_DOCUMENTS};")
    for n in range(rows):
        conn.execute(
            "INSERT INTO documents (sha256, source_id, product_external_id, source_url, "
            "title, last_updated, fetched_at) VALUES (?, 'emc', ?, ?, ?, '07/07/2026', ?)",
            (f"{n:064d}", str(n), f"https://example.test/{n}", f"Label {n}", "2026-08-21"),
        )
    conn.commit()
    conn.close()


def test_migrating_preserves_every_stored_row(tmp_path: Path) -> None:
    """The whole point. A corpus is hundreds of billable fetches no command restores."""
    path = tmp_path / "corpus.db"
    _v3(path, rows=25)

    assert migrate(path, SCHEMA_VERSION) == 3

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM documents ORDER BY sha256").fetchall()
    assert len(rows) == 25
    assert rows[0]["title"] == "Label 0"
    assert rows[0]["last_updated"] == "07/07/2026", "existing columns are untouched"


def test_the_added_columns_are_null_not_backfilled(tmp_path: Path) -> None:
    """A document fetched before the field existed has no value, and must not be given one.

    Defaulting `discontinued` to 0 would assert that every historical label was actively
    marketed, on evidence nobody collected.
    """
    path = tmp_path / "corpus.db"
    _v3(path)
    migrate(path, SCHEMA_VERSION)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM documents").fetchone()
    assert row["discontinued"] is None
    assert row["atc_code"] is None
    assert row["holder_id"] is None


def test_a_migrated_database_opens(tmp_path: Path) -> None:
    """`connect` refuses an unrecognised version, so this is the end-to-end criterion."""
    path = tmp_path / "corpus.db"
    _v3(path)
    migrate(path, SCHEMA_VERSION)

    conn = connect(path)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_migrating_twice_is_a_no_op(tmp_path: Path) -> None:
    """Re-running must not fail on `duplicate column name`, which is what ALTER raises."""
    path = tmp_path / "corpus.db"
    _v3(path)
    migrate(path, SCHEMA_VERSION)

    assert migrate(path, SCHEMA_VERSION) == SCHEMA_VERSION


def test_a_failed_step_leaves_the_old_version_rather_than_half_a_schema(
    tmp_path: Path,
) -> None:
    """Interrupted half-way, the file must still be recognisable as what it was.

    Stamping outside the transaction would leave a database claiming a version whose
    columns it does not all have — refused by `connect` with no way back.
    """
    path = tmp_path / "corpus.db"
    _v3(path)
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE documents ADD COLUMN atc_code TEXT")  # a partial earlier run
    conn.commit()
    conn.close()

    with pytest.raises(sqlite3.OperationalError, match="duplicate column"):
        migrate(path, SCHEMA_VERSION)

    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3


def test_an_undefined_version_refuses_rather_than_guessing(tmp_path: Path) -> None:
    """Only added columns are expressible here. Anything else needs the rows copied."""
    path = tmp_path / "corpus.db"
    _v3(path)

    with pytest.raises(RuntimeError, match="no additive migration"):
        migrate(path, max(ADDED) + 1)


def test_migrating_backwards_is_refused(tmp_path: Path) -> None:
    """A newer build wrote columns this one does not know; going back would drop them."""
    path = tmp_path / "corpus.db"
    _v3(path)
    migrate(path, SCHEMA_VERSION)

    with pytest.raises(RuntimeError, match="newer than this build"):
        migrate(path, SCHEMA_VERSION - 1)


def test_a_missing_database_is_not_created(tmp_path: Path) -> None:
    """Creating one here would produce an empty file that looks like a migrated corpus."""
    with pytest.raises(FileNotFoundError):
        migrate(tmp_path / "absent.db", SCHEMA_VERSION)
