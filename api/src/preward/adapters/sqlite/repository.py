"""SQLite implementation of the pipeline's Repository port."""

import json
import sqlite3
from datetime import date
from importlib import resources
from pathlib import Path

from preward.domain import (
    Document,
    ExtractionMethod,
    Page,
    Record,
    Signal,
    Source,
    Tier,
)

_SCHEMA = "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and the schema applied."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    schema = resources.files("preward.adapters.sqlite").joinpath(_SCHEMA).read_text()
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

    def save_document(self, document: Document) -> None:
        """Insert a document, keyed by content hash. Idempotent on re-fetch."""
        self._conn.execute(
            "INSERT INTO documents "
            "(sha256, source_id, source_url, title, published_date, category, fetched_at, page_count) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?) "
            "ON CONFLICT(sha256) DO NOTHING",
            (
                document.sha256,
                document.source_id,
                document.source_url,
                document.title,
                _from_date(document.published_date),
                document.category,
                document.page_count,
            ),
        )
        self._conn.commit()

    def save_page(self, document_sha256: str, page: Page) -> None:
        """Insert or replace one page of extracted text."""
        self._conn.execute(
            "INSERT INTO pages (document_sha256, page_no, text, extraction_method) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(document_sha256, page_no) DO UPDATE SET "
            "text = excluded.text, extraction_method = excluded.extraction_method",
            (document_sha256, page.page_no, page.text, page.extraction_method.value),
        )
        self._conn.commit()

    def save_record(self, record: Record) -> Record:
        """Insert or update a record, returning it with its assigned id."""
        cur = self._conn.execute(
            "INSERT INTO records (source_id, designation, name) VALUES (?, ?, ?) "
            "ON CONFLICT(source_id, designation) DO UPDATE SET name = excluded.name "
            "RETURNING id",
            (record.source_id, record.designation, record.name),
        )
        record_id = cur.fetchone()["id"]
        self._conn.commit()
        return Record(
            source_id=record.source_id,
            name=record.name,
            designation=record.designation,
            id=record_id,
        )

    def save_signal(self, signal: Signal) -> Signal:
        """Insert a signal, returning it with its assigned id."""
        cur = self._conn.execute(
            "INSERT INTO signals "
            "(record_id, document_sha256, page_no, tier, confidence, quote, "
            " char_start, char_end, amount_cents, event_date, fired_cues_json, extraction_method) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (
                signal.record_id,
                signal.document_sha256,
                signal.page_no,
                int(signal.tier),
                signal.confidence,
                signal.quote,
                signal.char_start,
                signal.char_end,
                signal.amount_cents,
                _from_date(signal.event_date),
                json.dumps(list(signal.fired_cues)),
                signal.extraction_method.value,
            ),
        )
        signal_id = cur.fetchone()["id"]
        self._conn.commit()
        return self._signal_from_row(
            self._conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        )

    def signals_for_record(self, record_id: int) -> list[Signal]:
        """Every signal for a record, oldest event first. This is the ladder."""
        rows = self._conn.execute(
            "SELECT * FROM signals WHERE record_id = ? "
            "ORDER BY event_date IS NULL, event_date, id",
            (record_id,),
        ).fetchall()
        return [self._signal_from_row(row) for row in rows]

    @staticmethod
    def _signal_from_row(row: sqlite3.Row) -> Signal:
        return Signal(
            id=row["id"],
            record_id=row["record_id"],
            document_sha256=row["document_sha256"],
            page_no=row["page_no"],
            tier=Tier(row["tier"]),
            confidence=row["confidence"],
            quote=row["quote"],
            char_start=row["char_start"],
            char_end=row["char_end"],
            amount_cents=row["amount_cents"],
            event_date=_to_date(row["event_date"]),
            fired_cues=tuple(json.loads(row["fired_cues_json"])),
            extraction_method=ExtractionMethod(row["extraction_method"]),
        )
