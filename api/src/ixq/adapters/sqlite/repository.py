"""SQLite implementation of the pipeline's Repository port."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from ixq.domain import (
    UNCLASSIFIED,
    Collector,
    CollectorKind,
    Document,
    Occurrence,
    Placement,
    Product,
    Section,
    Source,
    Substance,
    appearance,
)
from ixq.pipeline.ports import ClauseCounts, ConceptDivergence, SubstanceCounts

_SCHEMA = "schema.sql"
SCHEMA_VERSION = 4
"""Must match `PRAGMA user_version` in schema.sql.

The schema is create-only — `IF NOT EXISTS` will not apply a changed column to an
existing file — so a stale database has to be caught at open time or the first write
fails somewhere far from the cause.
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced, creating the schema only if absent.

    The version is read **before** the schema is applied. Applying it first rewrote
    `PRAGMA user_version` to the expected value, so the staleness check could never fail
    and a database missing a renamed column opened cleanly, then failed on the first write
    far from the cause.

    Creating only when the stamp is 0 also takes the schema out of the request path. The
    pragma write is a header fsync — measured at ~95% of this function's cost, and it
    cannot run while another connection holds a read transaction.

    `check_same_thread=False` because FastAPI runs a sync generator dependency's setup in
    one threadpool worker and the endpoint body in another, so a per-request connection
    still crosses threads and raised under concurrent load. It is safe here only because
    the connection is never shared between requests and the three phases that touch it —
    setup, endpoint, teardown — run in sequence, never at once.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA user_version").fetchone()[0] == 0:
        conn.executescript(
            resources.files("ixq.adapters.sqlite").joinpath(_SCHEMA).read_text()
        )
    _check_version(conn, db_path)
    return conn


def _check_version(conn: sqlite3.Connection, db_path: Path) -> None:
    found = conn.execute("PRAGMA user_version").fetchone()[0]
    if found != SCHEMA_VERSION:
        raise RuntimeError(
            f"{db_path} is at schema version {found}, this build expects {SCHEMA_VERSION}. "
            "There is no migration path: the schema is create-only, so a changed column "
            "cannot be applied to an existing file.\n"
            "Deleting it is NOT free. The file holds the collected corpus — hundreds of "
            "billable fetches, which `init` does not restore and `run` re-bills — and "
            "bdheal's baselines and heal events, which are history no command can "
            "regenerate and which the collector health screen reads."
        )


_CURRENT_DOCUMENTS = """
            SELECT d.sha256, d.product_external_id, p.substance_id
            FROM documents d
            JOIN products p
              ON p.source_id = d.source_id AND p.external_id = d.product_external_id
            WHERE d.sha256 = (
              SELECT d2.sha256 FROM documents d2
              WHERE d2.source_id = d.source_id
                AND d2.product_external_id = d.product_external_id
              ORDER BY d2.fetched_at DESC, d2.sha256 DESC
              LIMIT 1
            )
"""
"""The newest revision of each product's label, and only that one.

One URL yields a new document every time its label is revised, and that history is kept
deliberately. `compare()` reduces it with a last-write-wins pass over `fetched_at`; every
query that counts or previews the comparison has to agree with it, or the roster
advertises findings the matrix does not have.

Held here once rather than pasted into each query. Three of them had drifted into joining
every revision, which agreed with `compare()` only for as long as newer revisions happened
to be supersets of older ones.

The `sha256` tiebreak makes it deterministic where two revisions share a `fetched_at`,
which the caller-side reduction cannot promise.
"""


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

    def section_codes_for_substance(self, substance_id: str) -> dict[str, tuple[str, ...]]:
        """Every document's section codes for one substance, in one query.

        Deliberately selects `code` only. The text column holds whole SmPC sections, and
        the caller is building a set of four short strings from it.
        """
        rows = self._conn.execute(
            "SELECT s.document_sha256 AS sha, s.code FROM sections s "
            "JOIN documents d ON d.sha256 = s.document_sha256 "
            "JOIN products p ON p.source_id = d.source_id "
            "AND p.external_id = d.product_external_id "
            "WHERE p.substance_id = ? ORDER BY s.document_sha256, s.code",
            (substance_id,),
        ).fetchall()
        codes: dict[str, list[str]] = {}
        for row in rows:
            codes.setdefault(row["sha"], []).append(row["code"])
        return {sha: tuple(found) for sha, found in codes.items()}

    def appearances_for_substance(self, substance_id: str) -> dict[str, str]:
        """Every document's §3 text for one substance, in one query.

        Addressed by section code rather than by a column of its own: §3 is a section the
        publisher numbers, and storing it anywhere else would fork how sections are read.
        Keeping it out of the comparison is `COMPARABLE`'s job, not the schema's — which
        is also why this needs no schema change and no migration of the collected corpus.
        """
        rows = self._conn.execute(
            "SELECT s.document_sha256 AS sha, s.text FROM sections s "
            "JOIN documents d ON d.sha256 = s.document_sha256 "
            "JOIN products p ON p.source_id = d.source_id "
            "AND p.external_id = d.product_external_id "
            "WHERE p.substance_id = ? AND s.code = ?",
            (substance_id, appearance.SECTION_CODE),
        ).fetchall()
        return {row["sha"]: row["text"] for row in rows}

    def counts_by_substance(self) -> dict[str, SubstanceCounts]:
        """The roster's three numbers per substance, counted in SQL.

        `MIN(section_code)` reproduces `PRECEDENCE` only because the placement codes sort
        lexicographically in the same order they rank — 4.3 < 4.4 < 4.5 < 4.6. That
        coupling is load-bearing and invisible, so a test asserts it directly; a placement
        code that breaks the ordering would change these counts silently.

        A concept diverges when its products do not all place it the same way, which is
        two things: more than one distinct placement among the products that have it, or
        at least one product missing it entirely (that product's cell reads ABSENT).
        """
        rows = self._conn.execute(
            """
            WITH current AS ("""
            + _CURRENT_DOCUMENTS
            + """),
            placed AS (
              SELECT c.substance_id, c.product_external_id, o.concept,
                     MIN(o.section_code) AS code
              FROM occurrences o
              JOIN current c ON c.sha256 = o.document_sha256
              GROUP BY c.substance_id, c.product_external_id, o.concept
            ),
            totals AS (
              SELECT substance_id, COUNT(DISTINCT product_external_id) AS products
              FROM current GROUP BY substance_id
            ),
            per_concept AS (
              SELECT substance_id, concept,
                     COUNT(DISTINCT code) AS variants,
                     COUNT(DISTINCT product_external_id) AS seen
              FROM placed WHERE concept != ? GROUP BY substance_id, concept
            )
            SELECT t.substance_id,
                   t.products,
                   COUNT(pc.concept) AS concepts,
                   COALESCE(SUM(pc.variants > 1 OR pc.seen < t.products), 0) AS divergent
            FROM totals t
            LEFT JOIN per_concept pc ON pc.substance_id = t.substance_id
            GROUP BY t.substance_id, t.products
            """,
            (UNCLASSIFIED,),
        ).fetchall()
        return {
            r["substance_id"]: SubstanceCounts(
                products=r["products"], concepts=r["concepts"], divergent=r["divergent"]
            )
            for r in rows
        }

    def clause_counts(self, substance_id: str) -> ClauseCounts:
        """Occurrences split by whether the lexicon matched them, counted in SQL.

        Counted over occurrences rather than concepts: the gap being published is how many
        clauses fell through, and a single `unclassified` concept row says nothing about
        whether that was one clause or a hundred.
        """
        row = self._conn.execute(
            """
            WITH current AS ("""
            + _CURRENT_DOCUMENTS
            + """)
            SELECT
              COALESCE(SUM(o.concept != ?), 0) AS classified,
              COALESCE(SUM(o.concept = ?), 0) AS unclassified
            FROM occurrences o
            JOIN current c ON c.sha256 = o.document_sha256
            WHERE c.substance_id = ?
            """,
            (UNCLASSIFIED, UNCLASSIFIED, substance_id),
        ).fetchone()
        return ClauseCounts(classified=row["classified"], unclassified=row["unclassified"])

    def divergences_by_substance(self) -> dict[str, tuple[ConceptDivergence, ...]]:
        """Which concepts diverge per substance, in SQL, with no section text read.

        The same CTEs as `counts_by_substance` and the same `MIN(section_code)` coupling:
        the placement codes sort lexicographically in the order they rank, and a test
        asserts that directly.

        `ABSENT` is appended when fewer products carry the concept than the substance has,
        which is exactly the condition that makes the missing product's cell read absent.
        """
        rows = self._conn.execute(
            """
            WITH current AS ("""
            + _CURRENT_DOCUMENTS
            + """),
            placed AS (
              SELECT c.substance_id, c.product_external_id, o.concept,
                     MIN(o.section_code) AS code
              FROM occurrences o
              JOIN current c ON c.sha256 = o.document_sha256
              GROUP BY c.substance_id, c.product_external_id, o.concept
            ),
            totals AS (
              SELECT substance_id, COUNT(DISTINCT product_external_id) AS products
              FROM current GROUP BY substance_id
            )
            SELECT p.substance_id, p.concept,
                   GROUP_CONCAT(DISTINCT p.code) AS codes,
                   COUNT(DISTINCT p.product_external_id) AS seen,
                   t.products
            FROM placed p
            JOIN totals t ON t.substance_id = p.substance_id
            WHERE p.concept != ?
            GROUP BY p.substance_id, p.concept
            HAVING COUNT(DISTINCT p.code) > 1 OR COUNT(DISTINCT p.product_external_id) < t.products
            ORDER BY p.substance_id, p.concept
            """,
            (UNCLASSIFIED,),
        ).fetchall()

        found: dict[str, list[ConceptDivergence]] = {}
        for row in rows:
            codes = sorted((row["codes"] or "").split(","))
            if row["seen"] < row["products"]:
                codes.append(Placement.ABSENT.value)
            found.setdefault(row["substance_id"], []).append(
                ConceptDivergence(concept=row["concept"], placements=tuple(codes))
            )
        return {substance: tuple(items) for substance, items in found.items()}

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
        """Insert a label, or refresh the source's record around one already stored.

        `sha256` addresses the label, so the same bytes are the same document and nothing
        about the text is rewritten. The listing columns are another matter: they are the
        source's current answer, not part of what is compared, so a re-fetch that finds a
        product newly discontinued must record that rather than discard it as a duplicate.
        """
        self._conn.execute(
            "INSERT INTO documents "
            "(sha256, source_id, product_external_id, source_url, title, "
            "active_substance, last_updated, fetched_at, listing_updated, holder_id, "
            "ingredient_id, atc_code, legal_status, ma_number, discontinued) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?) "
            # COALESCE, not assignment: these columns are the source's current answer, and
            # a re-fetch whose row failed validation arrives with them nulled. Overwriting
            # a recorded `discontinued = 1` with NULL turns "known discontinued" into
            # "nothing is known", which is the one collapse this column must never make.
            "ON CONFLICT(sha256) DO UPDATE SET "
            "listing_updated = COALESCE(excluded.listing_updated, listing_updated), "
            "holder_id = COALESCE(excluded.holder_id, holder_id), "
            "ingredient_id = COALESCE(excluded.ingredient_id, ingredient_id), "
            "atc_code = COALESCE(excluded.atc_code, atc_code), "
            "legal_status = COALESCE(excluded.legal_status, legal_status), "
            "ma_number = COALESCE(excluded.ma_number, ma_number), "
            "discontinued = COALESCE(excluded.discontinued, discontinued)",
            (
                document.sha256,
                document.source_id,
                document.product_external_id,
                document.source_url,
                document.title,
                document.active_substance,
                document.last_updated,
                document.listing_updated,
                document.holder_id,
                document.ingredient_id,
                document.atc_code,
                document.legal_status,
                document.ma_number,
                document.discontinued,
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

    def delete_occurrences(self, document_sha256: str) -> None:
        self._conn.execute(
            "DELETE FROM occurrences WHERE document_sha256 = ?", (document_sha256,)
        )

    def products_for_substance(self, substance_id: str) -> list[Product]:
        rows = self._conn.execute(
            "SELECT * FROM products WHERE substance_id = ? ORDER BY name", (substance_id,)
        ).fetchall()
        return [_to_product(row) for row in rows]

    def documents_for_substance(self, substance_id: str) -> list[Document]:
        rows = self._conn.execute(
            "SELECT d.* FROM documents d "
            "JOIN products p ON p.source_id = d.source_id "
            "AND p.external_id = d.product_external_id "
            # fetched_at breaks the tie between revisions of one product, so the caller's
            # last-write-wins picks the newest deliberately rather than by SQLite's whim.
            "WHERE p.substance_id = ? ORDER BY p.name, d.fetched_at",
            (substance_id,),
        ).fetchall()
        return [_to_document(r) for r in rows]

    def sections_for_document(self, document_sha256: str) -> list[Section]:
        rows = self._conn.execute(
            "SELECT code, heading, text FROM sections WHERE document_sha256 = ? ORDER BY code",
            (document_sha256,),
        ).fetchall()
        return [Section(code=r["code"], heading=r["heading"], text=r["text"]) for r in rows]

    def section_text(self, document_sha256: str, code: str) -> str | None:
        """One section's body, addressed by the primary key, so at most one row is read.

        Selects `text` alone and never joins: the caller already holds the document sha
        from the occurrence it is showing, so there is nothing left to resolve.
        """
        row = self._conn.execute(
            "SELECT text FROM sections WHERE document_sha256 = ? AND code = ?",
            (document_sha256, code),
        ).fetchone()
        return row["text"] if row else None

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


def _to_document(row: sqlite3.Row) -> Document:
    """`discontinued` is rebuilt as a tri-state: SQLite stores it as 0/1/NULL."""
    flag = row["discontinued"]
    return Document(
        sha256=row["sha256"],
        source_id=row["source_id"],
        product_external_id=row["product_external_id"],
        source_url=row["source_url"],
        title=row["title"],
        active_substance=row["active_substance"],
        last_updated=row["last_updated"],
        listing_updated=row["listing_updated"],
        holder_id=row["holder_id"],
        ingredient_id=row["ingredient_id"],
        atc_code=row["atc_code"],
        legal_status=row["legal_status"],
        ma_number=row["ma_number"],
        discontinued=None if flag is None else bool(flag),
    )


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
