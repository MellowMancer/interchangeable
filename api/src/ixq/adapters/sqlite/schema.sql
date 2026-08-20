-- Interchangeable? schema. Single source of truth, applied by adapters/sqlite on connect.
--
-- ⚠️ Create-only: every statement is IF NOT EXISTS, so a changed column is NOT migrated
-- into an existing database. `connect()` checks for known-stale shapes and says so.
-- Deliberately corpus-neutral: nothing here names a subject domain.
--
-- `bdheal` ships its own `bdheal_`-prefixed tables and may share this file. Nothing here
-- references them, and nothing there references these.

PRAGMA foreign_keys = ON;

-- Bumped whenever a column changes. `connect()` compares it, so the next change is
-- caught by the same one-line check rather than a new hardcoded column guard.
PRAGMA user_version = 1;

CREATE TABLE IF NOT EXISTS sources (
    id       TEXT PRIMARY KEY,              -- slug
    name     TEXT NOT NULL,
    base_url TEXT NOT NULL,
    variant  TEXT                           -- collector layout family, not a topic
);

-- A collector id survives healing, so it is a stable reference the pipeline holds
-- across layout changes rather than something to re-resolve each run.
CREATE TABLE IF NOT EXISTS collectors (
    id             TEXT PRIMARY KEY,        -- Bright Data collector id (c_...)
    source_id      TEXT NOT NULL REFERENCES sources(id),
    kind           TEXT NOT NULL,           -- product | search | sitemap | discovery
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_id, kind)                 -- one collector per role, so lookup is total
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

-- The active ingredient. Its id is ours, not any publisher's: the same ingredient is
-- named differently by every source, so the join key cannot be borrowed.
CREATE TABLE IF NOT EXISTS substances (
    id   TEXT PRIMARY KEY,                  -- slug
    name TEXT NOT NULL
);

-- One authorised product of one substance. Products of the same substance from different
-- holders are what this project compares, so the holder is a column, not part of a name.
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT NOT NULL REFERENCES sources(id),
    external_id  TEXT NOT NULL,             -- the id the source assigns
    substance_id TEXT NOT NULL REFERENCES substances(id),
    name         TEXT NOT NULL,
    ma_holder    TEXT,
    UNIQUE (source_id, external_id)
);

CREATE TABLE IF NOT EXISTS documents (
    sha256              TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL REFERENCES sources(id),
    product_external_id TEXT NOT NULL,      -- natural key, so fetch order does not matter
    source_url          TEXT NOT NULL,
    title               TEXT,
    fetched_at          TEXT NOT NULL
);
-- Deliberately no UNIQUE on (source_id, source_url): one URL yields a new document every
-- time its label is revised, and that history is the point of the project.

-- Sections are stored verbatim. Every quote shown is a slice of `text`, so normalising it
-- here would break the offsets in `occurrences`.
CREATE TABLE IF NOT EXISTS sections (
    document_sha256 TEXT NOT NULL REFERENCES documents(sha256),
    code            TEXT NOT NULL,          -- the publisher's own numbering, e.g. 4.3
    heading         TEXT NOT NULL,
    text            TEXT NOT NULL,
    PRIMARY KEY (document_sha256, code)
);

-- The provenance contract. `quote` must equal the section text at [char_start, char_end).
CREATE TABLE IF NOT EXISTS occurrences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_sha256 TEXT NOT NULL,
    section_code    TEXT NOT NULL,
    concept         TEXT NOT NULL,          -- 'unclassified' is a real, reportable value
    quote           TEXT NOT NULL,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    FOREIGN KEY (document_sha256, section_code) REFERENCES sections(document_sha256, code),
    UNIQUE (document_sha256, section_code, concept, char_start, char_end)
);

CREATE INDEX IF NOT EXISTS idx_products_substance ON products(substance_id);
CREATE INDEX IF NOT EXISTS idx_documents_product ON documents(source_id, product_external_id);
CREATE INDEX IF NOT EXISTS idx_occurrences_document ON occurrences(document_sha256);
CREATE INDEX IF NOT EXISTS idx_occurrences_concept ON occurrences(concept);
