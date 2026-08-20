"""The seam the UI reads. Shapes are the contract; the UI never opens SQLite."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ixq.pipeline.ports import Repository
from conftest import SECTION_43, SOURCE_ID, SUBSTANCE_ID, divergent_corpus


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    """A repository on the same file the app will open, so no connection is shared."""
    from ixq.adapters.sqlite import SqliteRepository, connect

    return SqliteRepository(connect(tmp_path / "interchangeable.db"))


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """The app against a throwaway database, wired exactly as it is in production."""
    from ixq.api import main

    config = tmp_path / "config"
    config.mkdir()
    (config / "substances.yaml").write_text(f"substances:\n  - {{id: {SUBSTANCE_ID}, name: Ex}}\n")
    (config / "sources.yaml").write_text(f"sources:\n  - {{id: {SOURCE_ID}, name: Example, base_url: 'https://example.test'}}\n")
    (config / "collectors.yaml").write_text(
        f"collectors:\n  - {{id: c_abc, source_id: {SOURCE_ID}, kind: product}}\n"
    )
    monkeypatch.setenv("IXQ_CONFIG_DIR", str(config))
    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    return TestClient(main.app)


def test_health_is_live(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_the_roster_reports_how_much_has_been_collected(
    client: TestClient, repository: Repository
) -> None:
    divergent_corpus(repository)

    body = client.get("/substances").json()

    assert body == [
        {"id": SUBSTANCE_ID, "name": "Ex", "products": 2, "concepts": 2, "divergent": 1}
    ]


def test_a_substance_with_nothing_collected_is_not_an_error(client: TestClient) -> None:
    """The roster lists what is configured; zero collected is a real state, not a 404."""
    body = client.get("/substances").json()

    assert body[0]["products"] == 0


def test_the_matrix_carries_the_scanned_sections(
    client: TestClient, repository: Repository
) -> None:
    """`absent` is unreadable without them, so they are part of the response, not metadata."""
    divergent_corpus(repository)

    columns = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]

    assert [c["scanned"] for c in columns] == [["4.3", "4.4"], ["4.3", "4.4"]]


def test_divergent_rows_come_first(client: TestClient, repository: Repository) -> None:
    divergent_corpus(repository)

    rows = client.get(f"/substances/{SUBSTANCE_ID}").json()["rows"]

    assert rows[0]["concept"] == "renal" and rows[0]["diverges"] is True
    assert rows[1]["diverges"] is False


def test_every_present_cell_carries_verifiable_evidence(
    client: TestClient, repository: Repository
) -> None:
    """A claim a reader cannot check against the source is not worth showing."""
    divergent_corpus(repository)

    rows = client.get(f"/substances/{SUBSTANCE_ID}").json()["rows"]
    renal = next(r for r in rows if r["concept"] == "renal")
    present = next(c for c in renal["cells"] if c["placement"] != "absent")
    missing = next(c for c in renal["cells"] if c["placement"] == "absent")

    assert present["evidence"]["quote"] == SECTION_43
    assert present["evidence"]["section_code"] == "4.3"
    assert present["evidence"]["source_url"].endswith("/product/1")
    assert missing["evidence"] is None


def test_columns_carry_the_revision_date(client: TestClient, repository: Repository) -> None:
    """A difference may be staleness rather than disagreement; the reader needs the date."""
    divergent_corpus(repository)

    products = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]

    assert {p["ma_holder"]: p["revised"] for p in products} == {
        "Alpha Ltd": "07/07/2026",
        "Beta Ltd": None,
    }


def test_an_uncollected_substance_matrix_is_a_404(client: TestClient) -> None:
    assert client.get("/substances/nonesuch").status_code == 404


def test_collectors_are_listed_with_their_role(client: TestClient) -> None:
    body = client.get("/collectors").json()

    assert body == [
        {
            "id": "c_abc",
            "kind": "product",
            "source": "Example",
            "baseline_captured_at": None,
            "baseline_row_count": None,
            "heals": [],
        }
    ]


def test_a_collector_that_has_never_run_reports_no_baseline_rather_than_health(
    client: TestClient,
) -> None:
    """`None` is 'not yet observed'. Rendering it as healthy would invent an observation."""
    assert client.get("/collectors").json()[0]["baseline_captured_at"] is None


def test_a_collectors_heal_history_is_reported_newest_first(client: TestClient) -> None:
    from datetime import UTC, datetime

    from bdheal.models import HealEvent, HealStatus
    from bdheal.store import SqliteHealStore
    from bdheal.store import connect as heal_connect
    from ixq.settings import heal_database_path

    store = SqliteHealStore(heal_connect(heal_database_path()))
    for day, status in ((1, HealStatus.AWAITING_APPROVAL), (2, HealStatus.DONE)):
        store.save_heal_event(
            HealEvent(
                collector_id="c_abc",
                status=status,
                created_at=datetime(2026, 8, day, tzinfo=UTC),
                promoted=status is HealStatus.DONE,
            )
        )

    heals = client.get("/collectors").json()[0]["heals"]

    assert [h["status"] for h in heals] == [HealStatus.DONE, HealStatus.AWAITING_APPROVAL]
    assert heals[0]["promoted"] is True
