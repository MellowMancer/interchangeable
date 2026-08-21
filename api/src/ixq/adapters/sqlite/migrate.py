"""One-shot migrations for the label database. Additive only, by construction.

The schema is create-only and there is no migration runner: `IF NOT EXISTS` will not
apply a changed column to a file that already exists. That is a deliberate constraint,
not an oversight — the database holds a corpus of billable fetches that no command
restores — so this module exists to move a file forward without rebuilding it.

It handles exactly one shape of change: **columns added to a table**. `ALTER TABLE ADD
COLUMN` is safe for that, rewrites nothing and cannot lose a row. A migration that
renames, retypes or drops a column is not expressible here and must not be forced into
it; that needs the rows copied into a fresh database, which is a different job with a
different risk.
"""

import sqlite3
from pathlib import Path

ADDED: dict[int, tuple[str, ...]] = {
    4: (
        "ALTER TABLE documents ADD COLUMN listing_updated TEXT",
        "ALTER TABLE documents ADD COLUMN holder_id INTEGER",
        "ALTER TABLE documents ADD COLUMN ingredient_id INTEGER",
        "ALTER TABLE documents ADD COLUMN atc_code TEXT",
        "ALTER TABLE documents ADD COLUMN legal_status TEXT",
        "ALTER TABLE documents ADD COLUMN ma_number TEXT",
        "ALTER TABLE documents ADD COLUMN discontinued INTEGER",
    ),
}
"""Target version -> the statements that bring the previous version up to it.

Keyed by the version it produces, so the path from any older file is the union of every
later key applied in order. Each column is nullable with no default: an existing document
was fetched before the field existed, and NULL is the honest record of that. Backfilling
a value would state something about a page nobody looked at.
"""


def migrate(db_path: Path, target: int) -> int:
    """Bring `db_path` up to `target`, returning the version it was on before.

    Idempotent by version, not by statement: a file already at `target` is left untouched.
    Every step runs inside one transaction with the stamp, so an interrupted migration
    leaves the file on its old version rather than half-way between two.

    The transaction is opened by hand. `with conn:` is not enough here: Python's `sqlite3`
    starts an implicit transaction only before DML, so `ALTER TABLE` and the `PRAGMA`
    stamp would each commit on their own and an interruption would leave columns added
    with the version unchanged — after which every re-run dies on `duplicate column name`
    and the corpus, which is hundreds of billable fetches, cannot be repaired by this
    module at all. SQLite itself is happy to roll DDL back; only the driver needed telling.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} does not exist — `ixq init` creates it")

    conn = sqlite3.connect(db_path)
    try:
        found = conn.execute("PRAGMA user_version").fetchone()[0]
        if found == target:
            return found
        if found > target:
            raise RuntimeError(
                f"{db_path} is at version {found}, newer than this build's {target}. "
                "Migrating backwards would drop columns a newer build wrote."
            )
        missing = sorted(set(range(found + 1, target + 1)) - set(ADDED))
        if missing:
            raise RuntimeError(
                f"no additive migration is defined for version(s) {missing}. Those "
                "versions changed something other than added columns, which this module "
                "cannot do safely — copy the rows into a fresh database instead."
            )
        conn.isolation_level = None
        conn.execute("BEGIN")
        try:
            for version in range(found + 1, target + 1):
                for statement in ADDED[version]:
                    conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {target}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        return found
    finally:
        conn.close()
