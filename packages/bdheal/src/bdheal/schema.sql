-- bdheal's own persistence. Ships inside the package and is applied by store.connect().
--
-- Every table is prefixed `bdheal_` so the package can share a SQLite file with a host
-- application that already owns tables of its own (the Interchangeable? app has a `heal_events`
-- of a different shape). Nothing here references an application table: bdheal does not
-- own collectors, it is told about them.

PRAGMA foreign_keys = ON;

-- The last known-good shape of one collector's output. Detect compares against this.
CREATE TABLE IF NOT EXISTS bdheal_baselines (
    collector_id    TEXT PRIMARY KEY,
    captured_at     TEXT NOT NULL,          -- ISO 8601, UTC
    row_count       INTEGER NOT NULL,
    null_rates_json TEXT NOT NULL,          -- {field: 0.0..1.0}
    skeleton_hash   TEXT                    -- NULL when no page HTML was available
);

-- One row per terminal heal outcome, promotion and rejection alike. The audit trail.
CREATE TABLE IF NOT EXISTS bdheal_heal_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id        TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    status              TEXT NOT NULL,      -- awaiting_approval | done | rejected | failed
    failure_class       TEXT,
    template_id         TEXT,
    prompt              TEXT,               -- never contains a credential (G6)
    preview_result_json TEXT,
    promoted            INTEGER NOT NULL DEFAULT 0,
    attempts            INTEGER NOT NULL DEFAULT 1,
    error               TEXT
);

-- Benchmark case outcomes, written as each case finishes so a multi-hour run resumes.
--
-- Nothing here may drop this table. A pre-release `DROP TABLE IF EXISTS` lived here while
-- `run_benchmark` was unimplemented, to carry a column rename no row had yet been written
-- under; now that cases are written, it would delete every completed case each time the
-- store was opened, and a restart would re-run the whole benchmark it exists to resume.
-- A column change from here on needs an ALTER.
CREATE TABLE IF NOT EXISTS bdheal_bench_cases (
    run_id                TEXT NOT NULL,
    case_id               TEXT NOT NULL,
    mutation              TEXT NOT NULL,
    expected_signals      TEXT NOT NULL,    -- comma-joined SignalKind set; "" is a declared gap
    caught_by             TEXT,             -- NULL is a coverage gap, not a failure
    fired_kinds           TEXT NOT NULL DEFAULT '',  -- every kind that fired, not just the credited one
    healed                INTEGER NOT NULL DEFAULT 0,
    field_accuracy        REAL,
    non_regression_passed INTEGER,
    attempts              INTEGER NOT NULL DEFAULT 0,
    elapsed_s             REAL NOT NULL DEFAULT 0,
    completed_at          TEXT,
    PRIMARY KEY (run_id, case_id)
);

CREATE INDEX IF NOT EXISTS idx_bdheal_heal_events_collector
    ON bdheal_heal_events(collector_id, created_at);
