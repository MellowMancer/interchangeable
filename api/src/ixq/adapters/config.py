"""Loads operator-tunable configuration from YAML into domain entities."""

from pathlib import Path

import yaml

from ixq.domain import Collector, CollectorKind, Concept, Source, Substance


def _read(path: Path) -> dict:
    """Parsed YAML, or an empty mapping when the file is absent or blank.

    A partial config is a real operating state — a roster can be configured before a
    lexicon is — so a missing file yields nothing rather than raising.
    """
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _entries(path: Path, key: str) -> list[dict]:
    """The rows under one top-level key, or none when the file or key is absent."""
    return _read(path).get(key) or []


def load_sources(path: Path) -> list[Source]:
    """Read the source roster. Returns an empty list when no corpus is configured."""
    return [
        Source(
            id=entry["id"],
            name=entry["name"],
            base_url=entry["base_url"],
            variant=entry.get("variant"),
            search_url=entry.get("search_url"),
            product_url=entry.get("product_url"),
        )
        for entry in _entries(path, "sources")
    ]


def load_substances(path: Path) -> list[Substance]:
    """Read the substance roster — the active ingredients to compare across products."""
    return [
        Substance(id=entry["id"], name=entry["name"])
        for entry in _entries(path, "substances")
    ]


def load_concepts(path: Path) -> list[Concept]:
    """Read the concept lexicon, in file order so the published matrix is stable."""
    return [
        Concept(name=name, patterns=_patterns(name, raw))
        for name, raw in (_read(path).get("concepts") or {}).items()
    ]


def _patterns(name: str, raw: object) -> tuple[str, ...]:
    """Patterns as a tuple of strings, or a clear error.

    A bare scalar — `renal: renal` — would otherwise be iterated character by character
    into single-letter patterns that match nearly every clause, corrupting the whole
    comparison with no error anywhere.
    """
    if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
        raise ValueError(f"concept {name!r} needs a list of string patterns, got {raw!r}")
    return tuple(raw)


def load_collectors(path: Path) -> list[Collector]:
    """Read the collector roster — the Scraper Studio ids the pipeline drives."""
    return [
        Collector(
            id=entry["id"],
            source_id=entry["source_id"],
            kind=CollectorKind(entry["kind"]),
            anchor_url=entry.get("anchor_url"),
            old_layout_url=entry.get("old_layout_url"),
        )
        for entry in _entries(path, "collectors")
    ]
