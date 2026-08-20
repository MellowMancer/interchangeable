"""The agent-facing seam. Answers must carry the scanned-sections caveat, never bare booleans."""

from pathlib import Path

import pytest

from conftest import SUBSTANCE_ID, divergent_corpus
from ixq.api.mcp_server import divergences, label_says
from ixq.pipeline.ports import Repository


@pytest.fixture
def repository(tmp_path: Path, monkeypatch) -> Repository:
    """A corpus on the exact file the MCP tools will open for themselves."""
    from ixq.adapters.sqlite import SqliteRepository, connect

    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    return SqliteRepository(connect(tmp_path / "interchangeable.db"))


def test_a_concept_only_one_manufacturer_bars_is_reported_as_divergent(
    repository: Repository,
) -> None:
    divergent_corpus(repository)

    answer = label_says(SUBSTANCE_ID, "renal")

    assert answer["found"] is True
    assert answer["diverges"] is True
    placements = {m["name"]: m["placement"] for m in answer["manufacturers"]}
    assert placements == {"Alpha Ltd": "4.3", "Beta Ltd": "absent"}


def test_an_agreed_concept_does_not_diverge(repository: Repository) -> None:
    divergent_corpus(repository)

    assert label_says(SUBSTANCE_ID, "hypersensitivity")["diverges"] is False


def test_an_unmatched_concept_is_a_recall_gap_not_a_denial(repository: Repository) -> None:
    """`found: False` must never be readable as 'the labels do not say this'."""
    divergent_corpus(repository)

    answer = label_says(SUBSTANCE_ID, "porphyria")

    assert answer["found"] is False
    assert "not evidence it is absent" in answer["note"]
    assert answer["known_concepts"] == ["hypersensitivity", "renal"]


def test_every_answer_names_the_sections_actually_scanned(repository: Repository) -> None:
    divergent_corpus(repository)

    answer = label_says(SUBSTANCE_ID, "renal")
    assert [m["sections_read"] for m in answer["manufacturers"]] == [
        ["4.3", "4.4"],
        ["4.3", "4.4"],
    ]
    assert [m["sections_read"] for m in divergences(SUBSTANCE_ID)["manufacturers"]] == [
        ["4.3", "4.4"],
        ["4.3", "4.4"],
    ]


def test_divergences_carry_revision_dates_so_staleness_is_separable(
    repository: Repository,
) -> None:
    """A one-sided finding may be an out-of-date label rather than a real disagreement."""
    divergent_corpus(repository)

    body = divergences(SUBSTANCE_ID)

    assert {m["name"]: m["revised"] for m in body["manufacturers"]} == {
        "Alpha Ltd": "07/07/2026",
        "Beta Ltd": None,
    }
    assert [d["concept"] for d in body["divergent_concepts"]] == ["renal"]
    assert body["agreed_concepts"] == ["hypersensitivity"]


def test_an_unknown_substance_errors_rather_than_reporting_no_divergence(
    repository: Repository,
) -> None:
    assert "no labels stored" in divergences("nonesuch")["error"]
    assert "no labels stored" in label_says("nonesuch", "renal")["error"]
