"""The memo of collector ids must not outlive the page those collectors were built against.

A collector is created *against a URL*, and Bright Data re-derives it from that same URL
when it heals — so an id remembered from an earlier base page silently heals itself against
whatever that URL serves now. This is the guard for the run that cost, and it needs no
network: `collector_ids` only calls the studio for ids it decides to build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FIXTURES))

from benchmark import collector_ids  # noqa: E402

BASE = "https://example.test/base.html"
MOVED = "https://example.test/index.html"
CASES = ["class_rename", "control"]


class StubStudio:
    """Hands back a predictable id and records every build it was asked for."""

    def __init__(self) -> None:
        self.built: list[str] = []

    def create(self, url: str, description: str, name: str | None = None) -> str:
        self.built.append(name or "")
        return f"c_{len(self.built):016d}"


def test_a_memo_built_against_another_page_is_not_reused(tmp_path: Path) -> None:
    """The failure this exists for: the base page was renamed and the ids outlived it.

    Reusing them made every heal repair a collector against the fixture index, which
    published a heal rate of 0.00 with nothing in the report saying why.
    """
    path = tmp_path / "collectors.json"
    studio = StubStudio()
    collector_ids(path, studio, MOVED, CASES)
    built_first = list(studio.built)

    collector_ids(path, studio, BASE, CASES)

    assert built_first == studio.built[: len(built_first)]
    assert len(studio.built) == 2 * len(CASES), "every collector is rebuilt for the new page"
    assert json.loads(path.read_text())["base_url"] == BASE


def test_a_memo_built_against_this_page_is_reused(tmp_path: Path) -> None:
    """The guard must not throw away ids that are still valid — a rebuild is billable."""
    path = tmp_path / "collectors.json"
    studio = StubStudio()
    first = collector_ids(path, studio, BASE, CASES)

    again = collector_ids(path, studio, BASE, CASES)

    assert again == first
    assert len(studio.built) == len(CASES), "nothing was rebuilt"


def test_a_memo_with_no_recorded_page_is_discarded(tmp_path: Path) -> None:
    """The shape written before this guard existed. It cannot prove where it came from."""
    path = tmp_path / "collectors.json"
    path.write_text(json.dumps({"class_rename": "c_old", "control": "c_older"}))
    studio = StubStudio()

    known = collector_ids(path, studio, BASE, CASES)

    assert "c_old" not in known.values()
    assert len(studio.built) == len(CASES)


def test_every_id_is_written_before_the_next_is_built(tmp_path: Path) -> None:
    """Bright Data has no programmatic delete, so an id lost to a crash is an orphan."""
    path = tmp_path / "collectors.json"

    class CrashingStudio(StubStudio):
        def create(self, url: str, description: str, name: str | None = None) -> str:
            if len(self.built) == 1:
                raise RuntimeError("network died mid-run")
            return super().create(url, description, name)

    try:
        collector_ids(path, CrashingStudio(), BASE, CASES)
    except RuntimeError:
        pass

    memo = json.loads(path.read_text())
    assert len(memo["collectors"]) == 1, "the id built before the crash survived it"
    assert memo["base_url"] == BASE
