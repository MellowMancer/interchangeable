"""The `ixq init` contract: a database exists afterwards, with the rosters loaded.

Deliberately builds its own config rather than reading the shipped one, so these stay
true whatever corpus is configured.
"""

from pathlib import Path

from typer.testing import CliRunner

from ixq.cli import app
from ixq.settings import DB_NAME

runner = CliRunner()

ROSTER = """
sources:
  - id: alpha
    name: Alpha Source
    base_url: https://alpha.test
    variant: A
  - id: beta
    name: Beta Source
    base_url: https://beta.test
"""


def test_init_creates_database_and_loads_roster(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(ROSTER)

    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IXQ_CONFIG_DIR", str(config_dir))

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / DB_NAME).exists()
    assert "2 sources" in result.output


def test_init_succeeds_with_no_corpus_configured(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text("sources: []\n")

    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IXQ_CONFIG_DIR", str(config_dir))

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    assert "0 sources" in result.output


ROSTER_EMC = """
sources:
  - id: emc
    name: Example Compendium
    base_url: https://example.test
    search_url: https://example.test/search?q={query}&limit=200
    product_url: https://example.test/product/{external_id}
"""
SUBSTANCES = "substances:\n  - {id: ramipril, name: Ramipril}\n"
COLLECTORS = (
    "collectors:\n"
    "  - {id: c_search, source_id: emc, kind: search}\n"
    "  - {id: c_product, source_id: emc, kind: product}\n"
)
CONCEPTS = "concepts:\n  renal: [renal]\n  hypersensitivity: [hypersensitiv]\n"

SEARCH_ROWS = [
    {"product_name": "Ramipril 1.25mg Tablets", "product_url": "https://example.test/product/10944",
     "company": "Sandoz Limited"},
    {"product_name": "Ramipril 2.5 mg/5 ml Oral solution", "product_url": "https://example.test/product/100143",
     "company": "Rosemont"},
    {"product_name": "Alogliptin/Ramipril Tablets", "product_url": "https://example.test/product/5234",
     "company": "Combo Ltd"},
]
PRODUCT_ROW = {
    "product_name": "Ramipril 1.25mg Tablets",
    "section_4_3_contraindications": "Hypersensitivity to the active substance.\nSevere renal failure.",
}


class FakeLabels:
    def rows(self, collector_id, urls):
        return SEARCH_ROWS if collector_id == "c_search" else [PRODUCT_ROW]


def _config(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "sources.yaml").write_text(ROSTER_EMC)
    (config_dir / "substances.yaml").write_text(SUBSTANCES)
    (config_dir / "collectors.yaml").write_text(COLLECTORS)
    (config_dir / "concepts.yaml").write_text(CONCEPTS)
    return config_dir


def test_run_collects_fetches_and_classifies_into_the_database(
    tmp_path: Path, monkeypatch
) -> None:
    """The whole pipeline, end to end, with the collector seam faked."""
    import sqlite3

    from ixq import cli

    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IXQ_CONFIG_DIR", str(_config(tmp_path)))
    monkeypatch.setattr(cli, "label_source", lambda *a, **k: FakeLabels())

    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    conn = sqlite3.connect(tmp_path / DB_NAME)
    counts = {
        t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in ("products", "documents", "sections", "occurrences")
    }
    # the combination product is excluded; the oral solution is not
    assert counts["products"] == 2
    assert counts["documents"] == 1 and counts["sections"] == 1
    assert counts["occurrences"] >= 2
    assert {row[0] for row in conn.execute("SELECT DISTINCT concept FROM occurrences")} == {
        "renal",
        "hypersensitivity",
    }


def test_run_caps_products_so_a_first_run_is_cheap(tmp_path: Path, monkeypatch) -> None:
    """Every collector call is billable, so the cap has to actually bind."""
    import sqlite3

    from ixq import cli

    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IXQ_CONFIG_DIR", str(_config(tmp_path)))
    monkeypatch.setattr(cli, "label_source", lambda *a, **k: FakeLabels())

    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["run", "--products", "1"])

    assert result.exit_code == 0, result.output
    conn = sqlite3.connect(tmp_path / DB_NAME)
    assert conn.execute("SELECT count(*) FROM products").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] == 1


def test_run_refuses_a_substance_that_is_not_in_the_roster(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("IXQ_CONFIG_DIR", str(_config(tmp_path)))

    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["run", "--substance", "nonesuch"])

    assert result.exit_code != 0
