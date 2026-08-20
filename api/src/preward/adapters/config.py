"""Loads operator-tunable configuration from YAML into domain entities."""

from pathlib import Path

import yaml

from preward.domain import Concept, Source, Substance


def _read(path: Path) -> dict:
    """Parsed YAML, or an empty mapping when the file is absent or blank.

    A partial config is a real operating state — a roster can be configured before a
    lexicon is — so a missing file yields nothing rather than raising.
    """
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def load_sources(path: Path) -> list[Source]:
    """Read the source roster. Returns an empty list when no corpus is configured."""
    return [
        Source(
            id=entry["id"],
            name=entry["name"],
            base_url=entry["base_url"],
            variant=entry.get("variant"),
        )
        for entry in (_read(path).get("sources") or [])
    ]


def load_substances(path: Path) -> list[Substance]:
    """Read the substance roster — the active ingredients to compare across products."""
    return [
        Substance(id=entry["id"], name=entry["name"])
        for entry in (_read(path).get("substances") or [])
    ]


def load_concepts(path: Path) -> list[Concept]:
    """Read the concept lexicon, in file order so the published matrix is stable."""
    return [
        Concept(name=name, patterns=tuple(patterns))
        for name, patterns in (_read(path).get("concepts") or {}).items()
    ]
