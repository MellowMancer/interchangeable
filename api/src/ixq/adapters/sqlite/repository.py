"""SQLite implementation of the pipeline's Repository port."""

import sqlite3
from datetime import date
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


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and the schema applied."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    schema = resources.files("ixq.adapters.sqlite").joinpath(_SCHEMA).read_text()
    conn.executescript(schema)
    return conn


def _to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _from_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


class SqliteRepository:
    """Persistence backed by a single SQLite file."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_source(self, source: Source) -> None:
        """Insert or update a source."""
        self._conn.execute(
            "INSERT INTO sources (id, name, base_url, variant) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "name = excluded.name, base_url = excluded.base_url, variant = excluded.variant",
            (source.id, source.name, source.base_url, source.variant),
        )
        self._conn.commit()

    def save_collector(self, collector: Collector) -> None:
        """Insert or update a collector. Its id is assigned by Bright Data, never by us."""
        self._conn.execute(
            "INSERT INTO collectors (id, source_id, kind) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "source_id = excluded.source_id, kind = excluded.kind",
            (collector.id, collector.source_id, collector.kind.value),
        )
        self._conn.commit()

    def collector_for(self, source_id: str, kind: CollectorKind) -> Collector | None:
        """The collector playing one role for one source, or None if not configured."""
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
        """Insert or update a substance."""
        self._conn.execute(
            "INSERT INTO substances (id, name) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name",
            (substance.id, substance.name),
        )
        self._conn.commit()

    def save_product(self, product: Product) -> Product:
        """Insert or update a product, returning it with its assigned id."""
        cursor = self._conn.execute(
            "INSERT INTO products (source_id, external_id, substance_id, name, ma_holder) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id, external_id) DO UPDATE SET "
            "substance_id = excluded.substance_id, name = excluded.name, "
            "ma_holder = excluded.ma_holder "
            "RETURNING id",
            (
                product.source_id,
                product.external_id,
                product.substance_id,
                product.name,
                product.ma_holder,
            ),
        )
        assigned = cursor.fetchone()["id"]
        self._conn.commit()
        return Product(
            source_id=product.source_id,
            external_id=product.external_id,
            substance_id=product.substance_id,
            name=product.name,
            ma_holder=product.ma_holder,
            id=assigned,
        )

    def save_document(self, document: Document) -> None:
        """Insert a document, keyed by content hash. Idempotent on re-fetch."""
        self._conn.execute(
            "INSERT INTO documents "
            "(sha256, source_id, product_external_id, source_url, title, last_updated, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(sha256) DO NOTHING",
            (
                document.sha256,
                document.source_id,
                document.product_external_id,
                document.source_url,
                document.title,
                _from_date(document.last_updated),
            ),
        )
        self._conn.commit()

    def save_section(self, document_sha256: str, section: Section) -> None:
        """Insert or replace one numbered section of a document."""
        self._conn.execute(
            "INSERT INTO sections (document_sha256, code, heading, text) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(document_sha256, code) DO UPDATE SET "
            "heading = excluded.heading, text = excluded.text",
            (document_sha256, section.code, section.heading, section.text),
        )
        self._conn.commit()

    def save_occurrence(self, occurrence: Occurrence) -> Occurrence:
        """Insert an occurrence, returning it with its assigned id."""
        cursor = self._conn.execute(
            "INSERT INTO occurrences "
            "(document_sha256, section_code, concept, quote, char_start, char_end) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(document_sha256, section_code, concept, char_start, char_end) "
            "DO UPDATE SET quote = excluded.quote "
            "RETURNING id",
            (
                occurrence.document_sha256,
                occurrence.section_code,
                occurrence.concept,
                occurrence.quote,
                occurrence.char_start,
                occurrence.char_end,
            ),
        )
        assigned = cursor.fetchone()["id"]
        self._conn.commit()
        return Occurrence(
            document_sha256=occurrence.document_sha256,
            section_code=occurrence.section_code,
            concept=occurrence.concept,
            quote=occurrence.quote,
            char_start=occurrence.char_start,
            char_end=occurrence.char_end,
            id=assigned,
        )

    def products_for_substance(self, substance_id: str) -> list[Product]:
        """Every product of a substance — the columns of the comparison."""
        rows = self._conn.execute(
            "SELECT * FROM products WHERE substance_id = ? ORDER BY name", (substance_id,)
        ).fetchall()
        return [_to_product(row) for row in rows]

    def sections_for_document(self, document_sha256: str) -> list[Section]:
        """Every section stored for a document, in code order."""
        rows = self._conn.execute(
            "SELECT code, heading, text FROM sections WHERE document_sha256 = ? ORDER BY code",
            (document_sha256,),
        ).fetchall()
        return [Section(code=r["code"], heading=r["heading"], text=r["text"]) for r in rows]

    def occurrences_for_substance(self, substance_id: str) -> list[Occurrence]:
        """Every occurrence across every product of a substance. This is the matrix."""
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
        id=row["id"],
    )


def _to_occurrence(row: sqlite3.Row) -> Occurrence:
    return Occurrence(
        document_sha256=row["document_sha256"],
        section_code=row["section_code"],
        concept=row["concept"],
        quote=row["quote"],
        char_start=row["char_start"],
        char_end=row["char_end"],
        id=row["id"],
    )
