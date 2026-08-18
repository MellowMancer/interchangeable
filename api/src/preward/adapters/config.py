"""Loads operator-tunable configuration from YAML into domain entities."""

from pathlib import Path

import yaml

from preward.domain import Source


def load_sources(path: Path) -> list[Source]:
    """Read the source roster. Returns an empty list when no corpus is configured."""
    raw = yaml.safe_load(path.read_text()) or {}
    return [
        Source(
            id=entry["id"],
            name=entry["name"],
            base_url=entry["base_url"],
            variant=entry.get("variant"),
        )
        for entry in (raw.get("sources") or [])
    ]
