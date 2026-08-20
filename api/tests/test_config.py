"""Config is data, so its failure modes are data failures: absent, empty, or malformed."""

from pathlib import Path

import pytest

from ixq.adapters.config import (
    load_collectors,
    load_concepts,
    load_sources,
    load_substances,
)
from ixq.domain import UNCLASSIFIED, CollectorKind, Concept


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


def test_collectors_load_with_their_kind(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "collectors.yaml",
        "collectors:\n  - {id: c_abc123, source_id: emc, kind: product}\n",
    )

    loaded = load_collectors(path)

    assert loaded[0].id == "c_abc123"
    assert loaded[0].kind is CollectorKind.PRODUCT


def test_unknown_collector_kind_is_rejected(tmp_path: Path) -> None:
    """A typo'd role must fail loudly rather than persist an unusable collector."""
    path = _write(tmp_path, "c.yaml", "collectors:\n  - {id: c_a, source_id: emc, kind: nonsense}\n")

    with pytest.raises(ValueError):
        load_collectors(path)


def test_shipped_collectors_parse(shipped_config_dir: Path) -> None:
    """The committed collector ids must stay loadable — the pipeline drives them."""
    collectors = load_collectors(shipped_config_dir / "collectors.yaml")

    assert CollectorKind.PRODUCT in {c.kind for c in collectors}
    assert all(c.id.startswith("c_") for c in collectors)


# Real contraindication clauses, each with the concept it must be tagged as. Every one
# was a measured miss before the lexicon was widened against 47 live labels — they are
# here so a future trim cannot quietly reopen the gap.
CLAUSES = [
    ("Diabetic pre-coma.", "glycaemic_emergency"),
    ("Haemorrhagic stroke", "bleeding"),
    ("History of angioedema (hereditary, idiopathic or due to ACE inhibitors)", "angioedema"),
    ("known QT-interval prolongation or congenital long QT syndrome", "qt_prolongation"),
    ("Thyrotoxicosis", "thyroid"),
    ("Live virus immunisation.", "immunisation"),
    ("rare hereditary problems of galactose intolerance", "excipient_intolerance"),
    ("Extracorporeal treatments leading to contact of blood", "extracorporeal"),
    ("Severe hypotension.", "hypotension"),
    ("Shock (including cardiogenic shock).", "shock"),
    ("obstruction of the outflow tract of the left ventricle", "cardiac_outflow"),
    ("Intravascular administration of iodinated contrast agents", "contrast_agent"),
    ("Severe renal failure (GFR < 30 mL/min).", "renal"),
    ("Hepatic insufficiency, acute alcohol intoxication", "hepatic"),
]


@pytest.mark.parametrize("clause,expected", CLAUSES)
def test_lexicon_covers_real_contraindication_clauses(
    shipped_config_dir: Path, clause: str, expected: str
) -> None:
    concepts = {c.name: c for c in load_concepts(shipped_config_dir / "concepts.yaml")}
    assert expected in concepts, f"{expected!r} is no longer a configured concept"
    assert concepts[expected].matches(clause)


def test_bleeding_matches_the_stem_not_the_whole_word(shipped_config_dir: Path) -> None:
    """`haemorrhage` as a pattern misses `haemorrhagic` — patterns are stems by contract."""
    concepts = {c.name: c for c in load_concepts(shipped_config_dir / "concepts.yaml")}
    assert concepts["bleeding"].matches("Haemorrhagic stroke")
    assert concepts["bleeding"].matches("risk of haemorrhage")


def test_a_scalar_pattern_list_is_rejected(tmp_path: Path) -> None:
    """`renal: renal` would iterate to single letters that match nearly every clause."""
    path = _write(tmp_path, "c.yaml", "concepts:\n  renal: renal\n")

    with pytest.raises(ValueError, match="list of string patterns"):
        load_concepts(path)


def test_a_non_string_pattern_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "c.yaml", "concepts:\n  renal: [renal, 5]\n")

    with pytest.raises(ValueError, match="list of string patterns"):
        load_concepts(path)
