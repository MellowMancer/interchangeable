"""The `HealStore` adapter — baselines, heal events and benchmark state in one SQLite file.

The schema ships inside the package and is loaded with `importlib.resources`, not a path
walked up from `__file__`, so the store works the same from a wheel as from a checkout.
Every statement binds its parameters: collector ids are caller-supplied strings.
"""

import sqlite3
from importlib import resources
from pathlib import Path

from bdheal.models import Baseline, BenchCase, HealEvent

SCHEMA_FILE = "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and the packaged schema applied."""
    raise NotImplementedError


class SqliteHealStore:
    """Persistence backed by a single SQLite file. The app may substitute its own."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_baseline(self, baseline: Baseline) -> None:
        """Insert or replace the known-good shape for one collector."""
        raise NotImplementedError

    def baseline(self, collector_id: str) -> Baseline | None:
        """The stored baseline, or `None` on a collector's first-ever run."""
        raise NotImplementedError

    def save_heal_event(self, event: HealEvent) -> HealEvent:
        """Append a heal event, returning it with its assigned id."""
        raise NotImplementedError

    def heal_events(self, collector_id: str) -> list[HealEvent]:
        """Every heal event for a collector, oldest first."""
        raise NotImplementedError

    def save_bench_case(self, case: BenchCase) -> None:
        """Insert or replace one benchmark case outcome. Idempotent, so a resume is safe."""
        raise NotImplementedError

    def completed_case_ids(self, run_id: str) -> list[str]:
        """The case ids already finished in this run. The runner skips these."""
        raise NotImplementedError


def _schema_sql() -> str:
    """The packaged DDL, read from the installed package rather than the source tree."""
    return resources.files("bdheal").joinpath(SCHEMA_FILE).read_text()
