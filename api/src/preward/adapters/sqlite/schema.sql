-- rf-pre schema. Single source of truth; applied as migrations by adapters/sqlite.
-- Deliberately corpus-neutral: nothing here names a subject domain.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id       TEXT PRIMARY KEY,              -- slug
    name     TEXT NOT NULL,
    base_url TEXT NOT NULL,
    variant  TEXT                           -- collector layout family, not a topic
);

CREATE TABLE IF NOT EXISTS collectors (
    id             TEXT PRIMARY KEY,        -- Bright Data collector id (c_...)
    source_id      TEXT NOT NULL REFERENCES sources(id),
    source_kind    TEXT NOT NULL,           -- scraper_studio | feed
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collector_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id  TEXT NOT NULL REFERENCES collectors(id),
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,            -- ok | failed | empty | rate_limited
    row_count     INTEGER NOT NULL DEFAULT 0,
    skeleton_hash TEXT,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    sha256         TEXT PRIMARY KEY,
    source_id      TEXT NOT NULL REFERENCES sources(id),
    source_url     TEXT NOT NULL,
    title          TEXT,
    published_date TEXT,                    -- ISO 8601 date
    category       TEXT,
    fetched_at     TEXT NOT NULL,
    page_count     INTEGER,
    UNIQUE (source_id, source_url)
);

CREATE TABLE IF NOT EXISTS pages (
    document_sha256   TEXT NOT NULL REFERENCES documents(sha256),
    page_no           INTEGER NOT NULL,
    text              TEXT NOT NULL,
    extraction_method TEXT NOT NULL,        -- native | ocr
    PRIMARY KEY (document_sha256, page_no)
);

CREATE TABLE IF NOT EXISTS doc_tables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_sha256 TEXT NOT NULL REFERENCES documents(sha256),
    page_no         INTEGER NOT NULL,
    cells_json      TEXT NOT NULL,
    extractor       TEXT NOT NULL           -- pymupdf | pdfplumber
);

CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL REFERENCES sources(id),
    designation TEXT,                       -- identifier assigned by the source
    name        TEXT NOT NULL,
    UNIQUE (source_id, designation)
);

CREATE TABLE IF NOT EXISTS record_aliases (
    record_id INTEGER NOT NULL REFERENCES records(id),
    alias     TEXT NOT NULL,
    PRIMARY KEY (record_id, alias)
);

-- The provenance contract. Every column here is rendered or linked in the UI.
CREATE TABLE IF NOT EXISTS signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id         INTEGER NOT NULL REFERENCES records(id),
    document_sha256   TEXT NOT NULL REFERENCES documents(sha256),
    page_no           INTEGER NOT NULL,
    tier              INTEGER NOT NULL,     -- 1 mention | 2 exploration | 3 commitment | 4 execution
    confidence        REAL NOT NULL,
    quote             TEXT NOT NULL,        -- verbatim, byte-identical to page text
    char_start        INTEGER NOT NULL,
    char_end          INTEGER NOT NULL,
    amount_cents      INTEGER,
    event_date        TEXT,
    fired_cues_json   TEXT NOT NULL,        -- the explanation, not a debug field
    extraction_method TEXT NOT NULL,        -- native | ocr
    UNIQUE (document_sha256, page_no, char_start, char_end, tier)
);

CREATE TABLE IF NOT EXISTS heal_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id        TEXT NOT NULL REFERENCES collectors(id),
    detected_at         TEXT NOT NULL,
    detect_signal       TEXT NOT NULL,      -- validation | zero_rows | skeleton_delta | null_spike
    diagnosis           TEXT,
    prompt              TEXT,
    outcome             TEXT NOT NULL,      -- promoted | rolled_back | failed
    non_regression_ok   INTEGER,            -- healed collector still parses the OLD layout
    attempts            INTEGER NOT NULL DEFAULT 1,
    duration_seconds    INTEGER,
    schema_version_from INTEGER,
    schema_version_to   INTEGER
);

CREATE TABLE IF NOT EXISTS benchmark_cases (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    axis           TEXT NOT NULL,           -- synthetic | cross_site | temporal
    mutation       TEXT NOT NULL,           -- class-rename | table-to-div | ...
    fixture_url    TEXT NOT NULL,
    golden_json    TEXT NOT NULL,
    heal_event_id  INTEGER REFERENCES heal_events(id),
    field_accuracy REAL,
    UNIQUE (axis, mutation)
);

CREATE INDEX IF NOT EXISTS idx_signals_record ON signals(record_id, event_date);
CREATE INDEX IF NOT EXISTS idx_signals_tier ON signals(tier);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id, published_date);
CREATE INDEX IF NOT EXISTS idx_pages_document ON pages(document_sha256);
