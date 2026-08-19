"""The one adapter that touches a real resource, exercised against a `tmp_path` file.

No test here names a path outside `tmp_path`, so the suite still runs with no database,
no application and no network (G1). Collector ids are caller-supplied and treated as
hostile: the injection test is the reason every statement binds its parameters.
"""

import ast
import inspect
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from conftest import FIXED_NOW, STUB_COLLECTOR_ID

from bdheal import store as store_module
from bdheal.models import Baseline, BenchCase, HealEvent
from bdheal.store import SqliteHealStore, connect
from bdheal.vocabulary import ExpectedSignal, FailureClass, HealStatus, MutationClass, SignalKind

EXPECTED_TABLES = {"bdheal_baselines", "bdheal_heal_events", "bdheal_bench_cases"}
SQL_INJECTION_ID = "x'); DROP TABLE heal_events;--"
RUN_ID = "run_0001"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A database file that does not exist yet, inside the test's own directory."""
    return tmp_path / "bdheal.sqlite3"


@pytest.fixture
def sqlite_store(db_path: Path) -> SqliteHealStore:
    """The adapter under test, on a fresh temp file."""
    return SqliteHealStore(connect(db_path))


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def _baseline(collector_id: str = STUB_COLLECTOR_ID) -> Baseline:
    return Baseline(
        collector_id=collector_id,
        captured_at=FIXED_NOW,
        row_count=42,
        null_rates={"title": 0.0, "published": 0.25},
        skeleton_hash="9f2b1c",
    )


def _heal_event(collector_id: str = STUB_COLLECTOR_ID, **overrides: object) -> HealEvent:
    fields: dict[str, object] = {
        "collector_id": collector_id,
        "status": HealStatus.AWAITING_APPROVAL,
        "created_at": FIXED_NOW,
        "prompt": "the table became a div; re-anchor on the row wrapper",
        "preview_result": {"rows": [{"title": "a", "url": "https://example.test/a"}]},
        "promoted": False,
        "failure_class": FailureClass.STRUCTURE_CHANGED,
        "template_id": "structure_changed_v1",
        "attempts": 2,
        "error": None,
    }
    return HealEvent(**(fields | overrides))


def _bench_case(case_id: str = "case_01", run_id: str = RUN_ID) -> BenchCase:
    return BenchCase(
        run_id=run_id,
        case_id=case_id,
        mutation=MutationClass.TABLE_TO_DIV,
        expected_signal=ExpectedSignal.SKELETON,
        caught_by=SignalKind.SKELETON,
        healed=True,
        field_accuracy=0.75,
        non_regression_passed=True,
        attempts=1,
        elapsed_s=12.5,
        completed_at=FIXED_NOW,
    )


def test_connect_creates_the_database_and_applies_the_packaged_schema(db_path: Path) -> None:
    """Criterion (a): a fresh temp file becomes a database with the three tables."""
    assert not db_path.exists()

    conn = connect(db_path)

    assert db_path.exists()
    assert EXPECTED_TABLES <= _table_names(conn)


def test_connect_is_idempotent_on_an_existing_database(db_path: Path) -> None:
    """Re-opening a store must not destroy what the last run wrote."""
    SqliteHealStore(connect(db_path)).save_baseline(_baseline())

    reopened = SqliteHealStore(connect(db_path))

    assert reopened.baseline(STUB_COLLECTOR_ID) == _baseline()


def test_the_schema_is_read_from_the_package_not_the_source_tree() -> None:
    """Criterion (a): `importlib.resources`, so a wheel behaves exactly like a checkout."""
    tree = ast.parse(inspect.getsource(store_module))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

    assert "resources.files" in inspect.getsource(store_module)
    assert "__file__" not in names


def test_a_baseline_round_trips_unchanged(sqlite_store: SqliteHealStore) -> None:
    """Criterion (b): row count, per-field null rates and skeleton hash all survive."""
    sqlite_store.save_baseline(_baseline())

    assert sqlite_store.baseline(STUB_COLLECTOR_ID) == _baseline()


def test_an_unknown_collector_has_no_baseline(sqlite_store: SqliteHealStore) -> None:
    """A collector's first-ever run has nothing to compare against."""
    assert sqlite_store.baseline("c_never_seen") is None


def test_saving_a_baseline_twice_keeps_only_the_newer_shape(
    sqlite_store: SqliteHealStore,
) -> None:
    """One baseline per collector: the known-good shape is replaced, never appended to."""
    sqlite_store.save_baseline(_baseline())
    newer = _baseline().model_copy(update={"row_count": 7, "skeleton_hash": "0000aa"})

    sqlite_store.save_baseline(newer)

    assert sqlite_store.baseline(STUB_COLLECTOR_ID) == newer


def test_a_heal_event_round_trips_with_its_gate_state(sqlite_store: SqliteHealStore) -> None:
    """Criterion (b): `status`, `prompt`, `preview_result` and `promoted` are preserved."""
    event = _heal_event()

    sqlite_store.save_heal_event(event)
    (stored,) = sqlite_store.heal_events(STUB_COLLECTOR_ID)

    assert stored.status == event.status
    assert stored.prompt == event.prompt
    assert stored.preview_result == event.preview_result
    assert stored.promoted == event.promoted
    assert stored == event.model_copy(update={"id": stored.id})


def test_a_promoted_heal_event_round_trips_as_promoted(sqlite_store: SqliteHealStore) -> None:
    """`promoted` is the rollback decision; it must not come back as an integer or None."""
    sqlite_store.save_heal_event(_heal_event(status=HealStatus.DONE, promoted=True))
    (stored,) = sqlite_store.heal_events(STUB_COLLECTOR_ID)

    assert stored.promoted is True
    assert stored.status == HealStatus.DONE


def test_a_saved_heal_event_is_returned_with_an_assigned_id(
    sqlite_store: SqliteHealStore,
) -> None:
    """The port hands back the stored event, so the caller need not re-read it."""
    first = sqlite_store.save_heal_event(_heal_event())
    second = sqlite_store.save_heal_event(_heal_event())

    assert first.id is not None
    assert second.id != first.id


def test_heal_events_are_oldest_first_and_scoped_to_their_collector(
    sqlite_store: SqliteHealStore,
) -> None:
    """The audit trail is per collector and in the order it happened."""
    sqlite_store.save_heal_event(_heal_event(prompt="first"))
    sqlite_store.save_heal_event(
        _heal_event(prompt="second", created_at=FIXED_NOW + timedelta(hours=1))
    )
    sqlite_store.save_heal_event(_heal_event(collector_id="c_other", prompt="elsewhere"))

    events = sqlite_store.heal_events(STUB_COLLECTOR_ID)

    assert [event.prompt for event in events] == ["first", "second"]


def test_a_collector_id_carrying_sql_is_stored_as_a_literal_string(
    sqlite_store: SqliteHealStore, db_path: Path
) -> None:
    """Criterion (c): bound parameters, so hostile input is data and never statement text."""
    sqlite_store.save_baseline(_baseline(SQL_INJECTION_ID))
    sqlite_store.save_heal_event(_heal_event(SQL_INJECTION_ID))

    stored_baseline = sqlite_store.baseline(SQL_INJECTION_ID)
    (stored_event,) = sqlite_store.heal_events(SQL_INJECTION_ID)

    assert stored_baseline is not None
    assert stored_baseline.collector_id == SQL_INJECTION_ID
    assert stored_event.collector_id == SQL_INJECTION_ID
    assert EXPECTED_TABLES <= _table_names(connect(db_path))


def test_finished_bench_cases_are_listed_for_their_run(sqlite_store: SqliteHealStore) -> None:
    """What the runner skips on resume: every case this run already finished."""
    sqlite_store.save_bench_case(_bench_case())
    sqlite_store.save_bench_case(_bench_case("case_02"))

    assert sqlite_store.completed_case_ids(RUN_ID) == ["case_01", "case_02"]


def test_saving_a_bench_case_twice_records_it_once(sqlite_store: SqliteHealStore) -> None:
    """A resumed run may re-save a case; it must not be counted twice."""
    sqlite_store.save_bench_case(_bench_case())
    sqlite_store.save_bench_case(_bench_case())

    assert sqlite_store.completed_case_ids(RUN_ID) == ["case_01"]


def test_completed_case_ids_are_scoped_to_their_run(sqlite_store: SqliteHealStore) -> None:
    """A new benchmark run starts empty, whatever earlier runs left behind."""
    sqlite_store.save_bench_case(_bench_case())

    assert sqlite_store.completed_case_ids("run_0002") == []
