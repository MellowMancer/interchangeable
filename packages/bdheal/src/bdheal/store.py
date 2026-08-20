"""The `HealStore` adapter — baselines, heal events and benchmark state in one SQLite file.

The schema ships inside the package and is loaded with `importlib.resources`, not a path
walked up from `__file__`, so the store works the same from a wheel as from a checkout.
Every statement binds its parameters: collector ids are caller-supplied strings.
"""

import json
import sqlite3
from datetime import datetime
from importlib import resources
from pathlib import Path

from bdheal.models import Baseline, BenchCase, HealEvent
from bdheal.vocabulary import SignalKind

SCHEMA_FILE = "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and the packaged schema applied."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_schema_sql())
    return conn


class SqliteHealStore:
    """Persistence backed by a single SQLite file. The app may substitute its own."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_baseline(self, baseline: Baseline) -> None:
        """Insert or replace the known-good shape for one collector."""
        self._conn.execute(
            "INSERT INTO bdheal_baselines "
            "(collector_id, captured_at, row_count, null_rates_json, skeleton_hash) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(collector_id) DO UPDATE SET "
            "captured_at = excluded.captured_at, row_count = excluded.row_count, "
            "null_rates_json = excluded.null_rates_json, "
            "skeleton_hash = excluded.skeleton_hash",
            (
                baseline.collector_id,
                baseline.captured_at.isoformat(),
                baseline.row_count,
                json.dumps(baseline.null_rates),
                baseline.skeleton_hash,
            ),
        )
        self._conn.commit()

    def baseline(self, collector_id: str) -> Baseline | None:
        """The stored baseline, or `None` on a collector's first-ever run."""
        row = self._conn.execute(
            "SELECT * FROM bdheal_baselines WHERE collector_id = ?", (collector_id,)
        ).fetchone()
        return _to_baseline(row) if row else None

    def save_heal_event(self, event: HealEvent) -> HealEvent:
        """Append a heal event, returning it with its assigned id."""
        cur = self._conn.execute(
            "INSERT INTO bdheal_heal_events "
            "(collector_id, created_at, status, failure_class, template_id, prompt, "
            " preview_result_json, promoted, attempts, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (
                event.collector_id,
                event.created_at.isoformat(),
                event.status,
                event.failure_class,
                event.template_id,
                event.prompt,
                _dump_json(event.preview_result),
                int(event.promoted),
                event.attempts,
                event.error,
            ),
        )
        event_id = cur.fetchone()["id"]
        self._conn.commit()
        return event.model_copy(update={"id": event_id})

    def heal_events(self, collector_id: str) -> list[HealEvent]:
        """Every heal event for a collector, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM bdheal_heal_events WHERE collector_id = ? ORDER BY created_at, id",
            (collector_id,),
        ).fetchall()
        return [_to_heal_event(row) for row in rows]

    def save_bench_case(self, case: BenchCase) -> None:
        """Insert or replace one benchmark case outcome. Idempotent, so a resume is safe."""
        self._conn.execute(
            "INSERT INTO bdheal_bench_cases "
            "(run_id, case_id, mutation, expected_signals, caught_by, fired_kinds, healed, "
            " field_accuracy, non_regression_passed, attempts, elapsed_s, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id, case_id) DO UPDATE SET "
            "mutation = excluded.mutation, expected_signals = excluded.expected_signals, "
            "caught_by = excluded.caught_by, fired_kinds = excluded.fired_kinds, "
            "healed = excluded.healed, "
            "field_accuracy = excluded.field_accuracy, "
            "non_regression_passed = excluded.non_regression_passed, "
            "attempts = excluded.attempts, elapsed_s = excluded.elapsed_s, "
            "completed_at = excluded.completed_at",
            (
                case.run_id,
                case.case_id,
                case.mutation,
                _join_kinds(case.expected_signals),
                case.caught_by,
                _join_kinds(case.fired_kinds),
                int(case.healed),
                case.field_accuracy,
                _nullable_int(case.non_regression_passed),
                case.attempts,
                case.elapsed_s,
                _iso(case.completed_at),
            ),
        )
        self._conn.commit()

    def completed_case_ids(self, run_id: str) -> list[str]:
        """The case ids already finished in this run. The runner skips these."""
        rows = self._conn.execute(
            "SELECT case_id FROM bdheal_bench_cases WHERE run_id = ? ORDER BY case_id",
            (run_id,),
        ).fetchall()
        return [row["case_id"] for row in rows]

    def bench_cases(self, run_id: str) -> list[BenchCase]:
        """Every finished case in this run, so a restarted process can publish its metrics."""
        rows = self._conn.execute(
            "SELECT * FROM bdheal_bench_cases WHERE run_id = ? ORDER BY case_id",
            (run_id,),
        ).fetchall()
        return [_to_bench_case(row) for row in rows]


def _schema_sql() -> str:
    """The packaged DDL, read from the installed package rather than the source tree."""
    return resources.files("bdheal").joinpath(SCHEMA_FILE).read_text()


def _join_kinds(kinds: frozenset[SignalKind]) -> str:
    """A declared detector set as one sorted, comma-joined column value.

    Sorted so the stored text is stable for a given set, and the empty string is a real
    value — a class no detector catches, which the benchmark publishes as a gap.
    """
    return ",".join(sorted(kinds))


def _split_kinds(value: str) -> frozenset[SignalKind]:
    """The inverse of `_join_kinds`.

    `""` is a real stored value — a class its generator declared nothing catches — and
    `"".split(",")` yields `[""]`, so the empty column is answered before it is split. A
    set holding one empty string would read back as a declaration nothing can satisfy.
    """
    return frozenset(SignalKind(kind) for kind in value.split(",")) if value else frozenset()


def _iso(moment: datetime | None) -> str | None:
    """A timestamp as SQLite stores it: ISO 8601 text, or NULL."""
    return moment.isoformat() if moment else None


def _dump_json(payload: dict | None) -> str | None:
    """A JSON column's value, keeping absence distinct from an empty object."""
    return json.dumps(payload) if payload is not None else None


def _load_json(payload: str | None) -> dict | None:
    """The inverse of `_dump_json`."""
    return json.loads(payload) if payload is not None else None


def _nullable_int(flag: bool | None) -> int | None:
    """A tri-state boolean column: true, false, or "not decided yet"."""
    return int(flag) if flag is not None else None


def _to_baseline(row: sqlite3.Row) -> Baseline:
    """Rebuild a baseline from its row; pydantic parses the ISO timestamp."""
    return Baseline(
        collector_id=row["collector_id"],
        captured_at=row["captured_at"],
        row_count=row["row_count"],
        null_rates=json.loads(row["null_rates_json"]),
        skeleton_hash=row["skeleton_hash"],
    )


def _to_heal_event(row: sqlite3.Row) -> HealEvent:
    """Rebuild a heal event from its row, gate state and audit fields intact."""
    return HealEvent(
        id=row["id"],
        collector_id=row["collector_id"],
        created_at=row["created_at"],
        status=row["status"],
        failure_class=row["failure_class"],
        template_id=row["template_id"],
        prompt=row["prompt"],
        preview_result=_load_json(row["preview_result_json"]),
        promoted=bool(row["promoted"]),
        attempts=row["attempts"],
        error=row["error"],
    )


def _to_bench_case(row: sqlite3.Row) -> BenchCase:
    """Rebuild a benchmark case from its row; pydantic parses the timestamp and the enums."""
    return BenchCase(
        run_id=row["run_id"],
        case_id=row["case_id"],
        mutation=row["mutation"],
        expected_signals=_split_kinds(row["expected_signals"]),
        caught_by=row["caught_by"],
        fired_kinds=_split_kinds(row["fired_kinds"]),
        healed=bool(row["healed"]),
        field_accuracy=row["field_accuracy"],
        non_regression_passed=_nullable_bool(row["non_regression_passed"]),
        attempts=row["attempts"],
        elapsed_s=row["elapsed_s"],
        completed_at=row["completed_at"],
    )


def _nullable_bool(flag: int | None) -> bool | None:
    """The inverse of `_nullable_int`: "not decided yet" stays undecided."""
    return bool(flag) if flag is not None else None
