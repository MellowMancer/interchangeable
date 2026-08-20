"""The seam the UI reads. Shapes are the contract; the UI never opens SQLite."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ixq.domain import Document, Occurrence, Product, Section, Source, Substance
from ixq.pipeline.ports import Repository
from conftest import SOURCE_ID, SUBSTANCE_ID

SECTION_43 = "Hypersensitivity to the active substance."
SECTION_44 = "Caution in renal impairment."


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


def _corpus(repository: Repository) -> None:
    """Seeded inside a transaction — an open write holds a lock the app cannot read past."""
    with repository.transaction():
        _seed(repository)


def _seed(repository: Repository) -> None:
    repository.save_source(Source(id=SOURCE_ID, name="Example", base_url="https://example.test"))
    repository.save_substance(Substance(id=SUBSTANCE_ID, name="Ex"))
    for external_id, holder, revised in (("1", "Alpha Ltd", "07/07/2026"), ("2", "Beta Ltd", None)):
        repository.save_product(
            Product(
                source_id=SOURCE_ID,
                external_id=external_id,
                substance_id=SUBSTANCE_ID,
                name=f"Ex {external_id}",
                ma_holder=holder,
            )
        )
        sha = external_id.rjust(64, "0")
        repository.save_document(
            Document(
                sha256=sha,
                source_id=SOURCE_ID,
                product_external_id=external_id,
                source_url=f"https://example.test/product/{external_id}",
                last_updated=revised,
            )
        )
        repository.save_section(sha, Section(code="4.3", heading="C", text=SECTION_43))
        repository.save_section(sha, Section(code="4.4", heading="W", text=SECTION_44))
        repository.save_occurrence(
            Occurrence(
                document_sha256=sha,
                section_code="4.3",
                concept="hypersensitivity",
                quote=SECTION_43,
                char_start=0,
                char_end=len(SECTION_43),
            )
        )
    # only Alpha bars renal outright
    repository.save_occurrence(
        Occurrence(
            document_sha256="1".rjust(64, "0"),
            section_code="4.3",
            concept="renal",
            quote=SECTION_43,
            char_start=0,
            char_end=len(SECTION_43),
        )
    )


def test_health_is_live(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_the_roster_reports_how_much_has_been_collected(
    client: TestClient, repository: Repository
) -> None:
    _corpus(repository)

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
    _corpus(repository)

    assert client.get(f"/substances/{SUBSTANCE_ID}").json()["scanned"] == ["4.3", "4.4"]


def test_divergent_rows_come_first(client: TestClient, repository: Repository) -> None:
    _corpus(repository)

    rows = client.get(f"/substances/{SUBSTANCE_ID}").json()["rows"]

    assert rows[0]["concept"] == "renal" and rows[0]["diverges"] is True
    assert rows[1]["diverges"] is False


def test_every_present_cell_carries_verifiable_evidence(
    client: TestClient, repository: Repository
) -> None:
    """A claim a reader cannot check against the source is not worth showing."""
    _corpus(repository)

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
    _corpus(repository)

    products = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]

    assert {p["ma_holder"]: p["revised"] for p in products} == {
        "Alpha Ltd": "07/07/2026",
        "Beta Ltd": None,
    }


def test_an_uncollected_substance_matrix_is_a_404(client: TestClient) -> None:
    assert client.get("/substances/nonesuch").status_code == 404


def test_collectors_are_listed_with_their_role(client: TestClient) -> None:
    body = client.get("/collectors").json()

    assert body == [{"id": "c_abc", "kind": "product", "source": "Example"}]
