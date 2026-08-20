"""Shared fixtures. Tests exercise the ports, not the concrete adapters.

Test data is deliberately corpus-neutral: nothing here names a real medicine, so the
fixtures keep working whatever roster is configured.
"""

from datetime import date
from pathlib import Path

import pytest

from preward.adapters.sqlite import SqliteRepository, connect
from preward.domain import Document, Product, Section, Source, Substance
from preward.pipeline.ports import Repository

SOURCE_ID = "example-source"
SUBSTANCE_ID = "example-substance"
PRODUCT_EXTERNAL_ID = "1001"
DOC_SHA = "a" * 64
SECTION = Section(
    code="4.3",
    heading="Contraindications",
    text="Hypersensitivity to the active substance. Severe renal impairment.",
)


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    """A Repository backed by a throwaway SQLite file, typed as the port."""
    return SqliteRepository(connect(tmp_path / "test.db"))


@pytest.fixture
def seeded_product(repository: Repository) -> Product:
    """A source, substance, product, document and section — enough to hang an occurrence off."""
    repository.save_source(
        Source(id=SOURCE_ID, name="Example Source", base_url="https://example.test", variant="A")
    )
    repository.save_substance(Substance(id=SUBSTANCE_ID, name="Example Substance"))
    product = repository.save_product(
        Product(
            source_id=SOURCE_ID,
            external_id=PRODUCT_EXTERNAL_ID,
            substance_id=SUBSTANCE_ID,
            name="Example 10mg Tablets",
            ma_holder="Example Holder Ltd",
        )
    )
    repository.save_document(
        Document(
            sha256=DOC_SHA,
            source_id=SOURCE_ID,
            product_external_id=PRODUCT_EXTERNAL_ID,
            source_url="https://example.test/product/1001",
            title="Example 10mg Tablets",
            last_updated=date(2025, 1, 6),
        )
    )
    repository.save_section(DOC_SHA, SECTION)
    return product


@pytest.fixture
def shipped_config_dir() -> Path:
    """The real config/ directory, so tests fail if the shipped YAML breaks."""
    return Path(__file__).resolve().parent.parent / "config"
