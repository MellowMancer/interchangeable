"""Shared fixtures. Tests exercise the ports, not the concrete adapters.

Test data is deliberately corpus-neutral: nothing here names a real medicine, so the
fixtures keep working whatever roster is configured.
"""

from pathlib import Path

import pytest

from ixq.adapters.sqlite import SqliteRepository, connect
from ixq.domain import Document, Occurrence, Product, Section, Source, Substance
from ixq.pipeline.ports import Repository

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
    product = Product(
        source_id=SOURCE_ID,
        external_id=PRODUCT_EXTERNAL_ID,
        substance_id=SUBSTANCE_ID,
        name="Example 10mg Tablets",
        ma_holder="Example Holder Ltd",
    )
    repository.save_product(product)
    repository.save_document(
        Document(
            sha256=DOC_SHA,
            source_id=SOURCE_ID,
            product_external_id=PRODUCT_EXTERNAL_ID,
            source_url="https://example.test/product/1001",
            title="Example 10mg Tablets",
        )
    )
    repository.save_section(DOC_SHA, SECTION)
    return product


@pytest.fixture
def shipped_config_dir() -> Path:
    """The real config/ directory, so tests fail if the shipped YAML breaks."""
    return Path(__file__).resolve().parent.parent / "config"


SECTION_43 = "Hypersensitivity to the active substance."
SECTION_44 = "Caution in renal impairment."


def divergent_corpus(repository: Repository) -> None:
    """Two products that agree on one concept and diverge on another.

    Seeded inside a transaction — an open write holds a lock a reader cannot get past.
    """
    with repository.transaction():
        _seed(repository)


def _seed(repository: Repository) -> None:
    repository.save_source(Source(id=SOURCE_ID, name="Example", base_url="https://example.test"))
    repository.save_substance(Substance(id=SUBSTANCE_ID, name="Ex"))
    for external_id, holder, revised in (("1", "Alpha Ltd", "07/07/2026"), ("2", "Beta Ltd", None)):
        repository.save_product(
            Product(
                source_id=SOURCE_ID,
                external_id=external_id,
                substance_id=SUBSTANCE_ID,
                name=f"Ex {external_id}",
                ma_holder=holder,
            )
        )
        sha = external_id.rjust(64, "0")
        repository.save_document(
            Document(
                sha256=sha,
                source_id=SOURCE_ID,
                product_external_id=external_id,
                source_url=f"https://example.test/product/{external_id}",
                last_updated=revised,
            )
        )
        repository.save_section(sha, Section(code="4.3", heading="C", text=SECTION_43))
        repository.save_section(sha, Section(code="4.4", heading="W", text=SECTION_44))
        repository.save_occurrence(
            Occurrence(
                document_sha256=sha,
                section_code="4.3",
                concept="hypersensitivity",
                quote=SECTION_43,
                char_start=0,
                char_end=len(SECTION_43),
            )
        )
    # only Alpha bars renal outright
    repository.save_occurrence(
        Occurrence(
            document_sha256="1".rjust(64, "0"),
            section_code="4.3",
            concept="renal",
            quote=SECTION_43,
            char_start=0,
            char_end=len(SECTION_43),
        )
    )


def _corpus_database() -> Path | None:
    """The collected database, wherever pytest was invoked from.

    `database_path()` resolves `data/` against the working directory, so a suite run from
    `api/` silently skipped every corpus guard — the tests whose whole purpose is to catch
    what unit tests cannot. Walking up for the repo root makes them run either way.
    """
    from ixq.settings import DB_NAME, database_path

    if database_path().exists():
        return database_path()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / DB_NAME
        if candidate.exists():
            return candidate
    return None


@pytest.fixture
def corpus_sections() -> list[Section]:
    """Every stored section, or a skip when nothing has been collected."""
    import sqlite3

    path = _corpus_database()
    if path is None:
        pytest.skip("no corpus collected")
    conn = sqlite3.connect(path)
    try:
        return [
            Section(code=code, heading=heading, text=text)
            for code, heading, text in conn.execute(
                "SELECT code, heading, text FROM sections"
            )
        ]
    finally:
        conn.close()
