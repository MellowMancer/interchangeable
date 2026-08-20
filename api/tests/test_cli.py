"""The `ixq init` contract: a database exists afterwards, with the rosters loaded.

Deliberately builds its own config rather than reading the shipped one, so these stay
true whatever corpus is configured.
"""

from pathlib import Path

from typer.testing import CliRunner

from ixq.cli import DB_NAME, app

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
