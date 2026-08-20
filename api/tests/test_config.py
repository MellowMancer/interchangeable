"""Config is data, so its failure modes are data failures: absent, empty, or malformed."""

from pathlib import Path

import pytest

from ixq.adapters.config import load_concepts, load_sources, load_substances
from ixq.domain import UNCLASSIFIED, Concept


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


def test_missing_file_yields_nothing(tmp_path: Path) -> None:
    """A partial config is a real state — a roster can exist before a lexicon does."""
    assert load_substances(tmp_path / "absent.yaml") == []
    assert load_concepts(tmp_path / "absent.yaml") == []
    assert load_sources(tmp_path / "absent.yaml") == []


def test_empty_roster_is_not_an_error(tmp_path: Path) -> None:
    assert load_substances(_write(tmp_path, "s.yaml", "substances: []\n")) == []


def test_substances_load_in_file_order(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "substances.yaml",
        "substances:\n  - {id: ramipril, name: Ramipril}\n  - {id: metformin, name: Metformin}\n",
    )

    loaded = load_substances(path)

    assert [s.id for s in loaded] == ["ramipril", "metformin"]
    assert loaded[0].name == "Ramipril"


def test_concepts_load_in_file_order(tmp_path: Path) -> None:
    """Order is the published matrix's row order, so it must not depend on a dict shuffle."""
    path = _write(
        tmp_path,
        "concepts.yaml",
        "concepts:\n  pregnancy: [pregnan]\n  renal: [renal, kidney]\n  hepatic: [liver]\n",
    )

    assert [c.name for c in load_concepts(path)] == ["pregnancy", "renal", "hepatic"]


def test_concept_patterns_are_lowercased_on_load(tmp_path: Path) -> None:
    """A mixed-case pattern would silently never match, since matching lowercases."""
    path = _write(tmp_path, "concepts.yaml", "concepts:\n  renal: [Renal, GFR]\n")

    assert load_concepts(path)[0].patterns == ("renal", "gfr")


def test_concept_matches_case_insensitively_on_stems() -> None:
    concept = Concept(name="pregnancy", patterns=("pregnan",))

    assert concept.matches("Contraindicated in PREGNANT women")
    assert concept.matches("during pregnancy")
    assert not concept.matches("severe renal impairment")


def test_concept_rejects_the_reserved_unclassified_name() -> None:
    with pytest.raises(ValueError, match="reserved"):
        Concept(name=UNCLASSIFIED, patterns=("anything",))


def test_concept_requires_at_least_one_pattern() -> None:
    with pytest.raises(ValueError, match="at least one pattern"):
        Concept(name="renal", patterns=())


def test_shipped_config_parses(shipped_config_dir: Path) -> None:
    """The committed YAML must stay loadable — it is the corpus definition."""
    sources = load_sources(shipped_config_dir / "sources.yaml")
    substances = load_substances(shipped_config_dir / "substances.yaml")
    concepts = load_concepts(shipped_config_dir / "concepts.yaml")

    assert [s.id for s in sources] == ["emc"]
    assert "ramipril" in {s.id for s in substances}
    assert {"pregnancy", "renal", "hepatic"} <= {c.name for c in concepts}
