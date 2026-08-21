-- Interchangeable? schema. Single source of truth, applied by adapters/sqlite on connect.
--
-- ⚠️ Create-only, and there is no migration runner. Every statement is IF NOT EXISTS, so
-- a changed column is never applied to an existing database. `connect()` reads
-- `user_version` before applying this file and refuses one it does not recognise.
--
-- Bumping the version is therefore a decision about existing data, not a formality. The
-- file holds the collected corpus — hundreds of billable fetches that `init` does not
-- restore — and bdheal's baselines and heal events, which are history no command
-- regenerates. A bump that changes a column needs the rows copied into a fresh database
-- by hand; "delete it and re-run init" is not a free recovery.
-- Deliberately corpus-neutral: nothing here names a subject domain.
--
-- `bdheal` keeps its tables in its own database (`bdheal.db`), not this one. Nothing here
-- references them and nothing there references these, so sharing a file bought only a
-- shared version stamp — which meant a bump here could refuse or rebuild heal history
-- that had not changed and cannot be regenerated.

PRAGMA foreign_keys = ON;

-- Bumped whenever a column changes. `connect()` reads it BEFORE applying this file and
-- refuses a database it does not recognise. Applying the schema first would rewrite the
-- stamp to the expected value and make the check unfalsifiable, which is what it did.
PRAGMA user_version = 4;

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
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_id, kind)                 -- one collector per role, so lookup is total
);

-- Run history lives in `bdheal_heal_events` and `bdheal_baselines`, which the engine
-- actually writes. A second, unwritten copy here duplicated `skeleton_hash` and `status`
-- and was never populated by anything.

-- The active ingredient. Its id is ours, not any publisher's: the same ingredient is
-- named differently by every source, so the join key cannot be borrowed.
CREATE TABLE IF NOT EXISTS substances (
    id   TEXT PRIMARY KEY,                  -- slug
    name TEXT NOT NULL
);

-- One authorised product of one substance. Products of the same substance from different
-- holders are what this project compares, so the holder is a column, not part of a name.
CREATE TABLE IF NOT EXISTS products (
    source_id    TEXT NOT NULL REFERENCES sources(id),
    external_id  TEXT NOT NULL,             -- the id the source assigns
    substance_id TEXT NOT NULL REFERENCES substances(id),
    name         TEXT NOT NULL,
    ma_holder    TEXT,
    PRIMARY KEY (source_id, external_id)    -- the real identity; no surrogate is referenced
);

CREATE TABLE IF NOT EXISTS documents (
    sha256              TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL REFERENCES sources(id),
    product_external_id TEXT NOT NULL,      -- natural key, so fetch order does not matter
    source_url          TEXT NOT NULL,
    title               TEXT,
    active_substance    TEXT,               -- as the label states it, not as we filed it
    last_updated        TEXT,               -- month precision, as published (section 10)
    fetched_at          TEXT NOT NULL,
    -- Below: the source's own record around the label, not the label. Updated in place on
    -- re-fetch rather than addressed by `sha256`, because a listing has one current state
    -- and putting a status badge in a content address forks a revision out of nothing.
    listing_updated     TEXT,               -- when the source touched its record
    holder_id           INTEGER,            -- the source's id for the holder; ma_holder is free text
    ingredient_id       INTEGER,            -- the source's id for the active ingredient
    atc_code            TEXT,
    legal_status        TEXT,
    ma_number           TEXT,               -- the regulator's id, unlike product_external_id
    discontinued        INTEGER,            -- 0/1; NULL means the fetch predates the field
    -- A document must belong to a product that exists. Without this a fetch could store a
    -- label against an id no product carries, and the comparison would silently omit it.
    FOREIGN KEY (source_id, product_external_id) REFERENCES products(source_id, external_id)
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
