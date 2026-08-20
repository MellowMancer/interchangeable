"""SQLite implementation of the pipeline's Repository port."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from ixq.domain import (
    Collector,
    CollectorKind,
    Document,
    Occurrence,
    Product,
    Section,
    Source,
    Substance,
)

_SCHEMA = "schema.sql"
SCHEMA_VERSION = 1
"""Must match `PRAGMA user_version` in schema.sql.

The schema is create-only — `IF NOT EXISTS` will not apply a changed column to an
existing file — so a stale database has to be caught at open time or the first write
fails somewhere far from the cause.
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and the schema applied."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(resources.files("ixq.adapters.sqlite").joinpath(_SCHEMA).read_text())
    _check_version(conn, db_path)
    return conn


def _check_version(conn: sqlite3.Connection, db_path: Path) -> None:
    found = conn.execute("PRAGMA user_version").fetchone()[0]
    if found != SCHEMA_VERSION:
        raise RuntimeError(
            f"{db_path} is at schema version {found}, this build expects {SCHEMA_VERSION}. "
            "The schema is create-only and holds no irreplaceable state — delete the file "
            "and re-run init."
        )


class SqliteRepository:
    """Persistence backed by a single SQLite file.

    Writes do not commit individually. A commit is an fsync, and committing per row costs
    roughly 1.4 ms against ~30 ms for a whole run's worth of rows sharing one transaction.
    The caller sets the boundary with `transaction()`, which is also the unit that should
    be atomic: a document's sections and occurrences belong together.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """One unit of work. Commits on success, rolls back on any exception."""
        try:
            yield
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()

    def save_source(self, source: Source) -> None:
        self._conn.execute(
            "INSERT INTO sources (id, name, base_url, variant) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, base_url = excluded.base_url, variant = excluded.variant",
            (source.id, source.name, source.base_url, source.variant),
        )

    def save_collector(self, collector: Collector) -> None:
        self._conn.execute(
            "INSERT INTO collectors (id, source_id, kind) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "source_id = excluded.source_id, kind = excluded.kind",
            (collector.id, collector.source_id, collector.kind.value),
        )

    def collector_for(self, source_id: str, kind: CollectorKind) -> Collector | None:
        row = self._conn.execute(
            "SELECT * FROM collectors WHERE source_id = ? AND kind = ?",
            (source_id, kind.value),
        ).fetchone()
        if row is None:
            return None
        return Collector(
            id=row["id"], source_id=row["source_id"], kind=CollectorKind(row["kind"])
        )

    def save_substance(self, substance: Substance) -> None:
        self._conn.execute(
            "INSERT INTO substances (id, name) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
            (substance.id, substance.name),
        )

    def save_product(self, product: Product) -> None:
        self._conn.execute(
            "INSERT INTO products (source_id, external_id, substance_id, name, ma_holder) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id, external_id) DO UPDATE SET "
            "substance_id = excluded.substance_id, name = excluded.name, "
            "ma_holder = excluded.ma_holder",
            (
                product.source_id,
                product.external_id,
                product.substance_id,
                product.name,
                product.ma_holder,
            ),
        )

    def save_document(self, document: Document) -> None:
        self._conn.execute(
            "INSERT INTO documents "
            "(sha256, source_id, product_external_id, source_url, title, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(sha256) DO NOTHING",  # same bytes, same document
            (
                document.sha256,
                document.source_id,
                document.product_external_id,
                document.source_url,
                document.title,
            ),
        )

    def save_section(self, document_sha256: str, section: Section) -> None:
        self._conn.execute(
            "INSERT INTO sections (document_sha256, code, heading, text) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(document_sha256, code) DO UPDATE SET "
            "heading = excluded.heading, text = excluded.text",
            (document_sha256, section.code, section.heading, section.text),
        )

    def save_occurrence(self, occurrence: Occurrence) -> None:
        self._conn.execute(
            "INSERT INTO occurrences "
            "(document_sha256, section_code, concept, quote, char_start, char_end) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(document_sha256, section_code, concept, char_start, char_end) "
            "DO UPDATE SET quote = excluded.quote",
            (
                occurrence.document_sha256,
                occurrence.section_code,
                occurrence.concept,
                occurrence.quote,
                occurrence.char_start,
                occurrence.char_end,
            ),
        )

    def products_for_substance(self, substance_id: str) -> list[Product]:
        rows = self._conn.execute(
            "SELECT * FROM products WHERE substance_id = ? ORDER BY name", (substance_id,)
        ).fetchall()
        return [_to_product(row) for row in rows]

    def sections_for_document(self, document_sha256: str) -> list[Section]:
        rows = self._conn.execute(
            "SELECT code, heading, text FROM sections WHERE document_sha256 = ? ORDER BY code",
            (document_sha256,),
        ).fetchall()
        return [Section(code=r["code"], heading=r["heading"], text=r["text"]) for r in rows]

    def occurrences_for_substance(self, substance_id: str) -> list[Occurrence]:
        rows = self._conn.execute(
            "SELECT o.* FROM occurrences o "
            "JOIN documents d ON d.sha256 = o.document_sha256 "
            "JOIN products p ON p.source_id = d.source_id "
            "AND p.external_id = d.product_external_id "
            "WHERE p.substance_id = ? "
            "ORDER BY p.name, o.section_code, o.concept, o.char_start",
            (substance_id,),
        ).fetchall()
        return [_to_occurrence(row) for row in rows]


def _to_product(row: sqlite3.Row) -> Product:
    return Product(
        source_id=row["source_id"],
        external_id=row["external_id"],
        substance_id=row["substance_id"],
        name=row["name"],
        ma_holder=row["ma_holder"],
    )


def _to_occurrence(row: sqlite3.Row) -> Occurrence:
    return Occurrence(
        document_sha256=row["document_sha256"],
        section_code=row["section_code"],
        concept=row["concept"],
        quote=row["quote"],
        char_start=row["char_start"],
        char_end=row["char_end"],
    )
