"""Shared fixtures. Tests exercise the ports, not the concrete adapters.

Test data is deliberately corpus-neutral: nothing here should need editing when a
subject domain is finally chosen.
"""

from datetime import date
from pathlib import Path

import pytest

from preward.adapters.sqlite import SqliteRepository, connect
from preward.domain import Document, Record, Source
from preward.pipeline.ports import Repository

SOURCE_ID = "example-source"
DOC_SHA = "a" * 64


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    """A Repository backed by a throwaway SQLite file, typed as the port."""
    return SqliteRepository(connect(tmp_path / "test.db"))


@pytest.fixture
def seeded_record(repository: Repository) -> Record:
    """A source, document and record, so signals have something to hang off."""
    repository.save_source(
        Source(id=SOURCE_ID, name="Example Source", base_url="https://example.test", variant="A")
    )
    repository.save_document(
        Document(
            sha256=DOC_SHA,
            source_id=SOURCE_ID,
            source_url="https://example.test/doc.pdf",
            title="Example Document",
            published_date=date(2025, 1, 6),
        )
    )
    return repository.save_record(
        Record(source_id=SOURCE_ID, name="Example Record", designation="REC-2024-01")
    )


@pytest.fixture
def shipped_config_dir() -> Path:
    """The real config/ directory, so tests fail if the shipped YAML breaks."""
    return Path(__file__).resolve().parent.parent / "config"
