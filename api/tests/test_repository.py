"""Exit criterion: an Occurrence round-trips through the Repository port intact."""

import sqlite3
from pathlib import Path

import pytest

from ixq.adapters.sqlite.repository import SCHEMA_VERSION, connect
from ixq.domain import (
    Collector,
    CollectorKind,
    Document,
    Product,
    Section,
    Source,
    Substance,
    found_in,
)
from ixq.pipeline.ports import Repository
from conftest import DOC_SHA, PRODUCT_EXTERNAL_ID, SECTION, SOURCE_ID, SUBSTANCE_ID


def test_a_stored_product_equals_the_one_that_was_built(
    repository: Repository, seeded_product: Product
) -> None:
    """No surrogate id on the entity, so a fresh product and a stored one compare equal."""
    assert repository.products_for_substance(SUBSTANCE_ID) == [seeded_product]


def test_product_save_is_idempotent(repository: Repository, seeded_product: Product) -> None:
    """Re-collecting the same product must update it, not duplicate it."""
    repository.save_product(
        Product(
            source_id=SOURCE_ID,
            external_id=PRODUCT_EXTERNAL_ID,
            substance_id=SUBSTANCE_ID,
            name="Example 10mg Tablets (renamed)",
            ma_holder="Example Holder Ltd",
        )
    )

    assert [p.name for p in repository.products_for_substance(SUBSTANCE_ID)] == [
        "Example 10mg Tablets (renamed)"
    ]


def test_occurrence_round_trips_with_its_offsets(
    repository: Repository, seeded_product: Product
) -> None:
    saved = found_in(SECTION, DOC_SHA, "renal", 42, 65)
    repository.save_occurrence(saved)

    loaded = repository.occurrences_for_substance(SUBSTANCE_ID)

    assert loaded == [saved]
    assert loaded[0].quote == "Severe renal impairment"
    assert (loaded[0].char_start, loaded[0].char_end) == (42, 65)
    assert loaded[0].section_code == "4.3"


def test_occurrences_gather_across_every_product_of_a_substance(
    repository: Repository, seeded_product: Product
) -> None:
    """The matrix is per substance, so a second manufacturer's rows must join in."""
    other_external_id = "1002"
    other_sha = "b" * 64
    repository.save_product(
        Product(
            source_id=SOURCE_ID,
            external_id=other_external_id,
            substance_id=SUBSTANCE_ID,
            name="Example 5mg Tablets",
            ma_holder="Another Holder Ltd",
        )
    )
    repository.save_document(
        Document(
            sha256=other_sha,
            source_id=SOURCE_ID,
            product_external_id=other_external_id,
            source_url="https://example.test/product/1002",
        )
    )
    other_section = Section(code="4.3", heading="Contraindications", text="Hypersensitivity only.")
    repository.save_section(other_sha, other_section)

    repository.save_occurrence(found_in(SECTION, DOC_SHA, "renal", 42, 65))
    repository.save_occurrence(found_in(other_section, other_sha, "hypersensitivity", 0, 16))

    loaded = repository.occurrences_for_substance(SUBSTANCE_ID)

    assert {o.concept for o in loaded} == {"renal", "hypersensitivity"}
    assert {o.document_sha256 for o in loaded} == {DOC_SHA, other_sha}


def test_sections_come_back_verbatim(repository: Repository, seeded_product: Product) -> None:
    """Quotes are slices of stored text, so any normalisation here breaks every offset."""
    sections = repository.sections_for_document(DOC_SHA)

    assert len(sections) == 1
    assert sections[0].text == SECTION.text


def test_substance_and_source_survive_a_reload(
    repository: Repository, seeded_product: Product
) -> None:
    repository.save_substance(Substance(id=SUBSTANCE_ID, name="Renamed Substance"))

    products = repository.products_for_substance(SUBSTANCE_ID)

    assert [p.substance_id for p in products] == [SUBSTANCE_ID]


def test_collector_round_trips_by_role(repository: Repository, seeded_product: Product) -> None:
    """The pipeline looks collectors up by role, so that lookup is the contract."""
    repository.save_collector(
        Collector(id="c_abc123", source_id=SOURCE_ID, kind=CollectorKind.PRODUCT)
    )

    found = repository.collector_for(SOURCE_ID, CollectorKind.PRODUCT)

    assert found is not None
    assert found.id == "c_abc123"
    assert repository.collector_for(SOURCE_ID, CollectorKind.SEARCH) is None


def test_one_collector_per_role_is_enforced_by_the_store(
    repository: Repository, seeded_product: Product
) -> None:
    """Lookup is by role, so two collectors sharing a role would make it non-deterministic."""
    import sqlite3

    repository.save_collector(
        Collector(id="c_first", source_id=SOURCE_ID, kind=CollectorKind.PRODUCT)
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.save_collector(
            Collector(id="c_second", source_id=SOURCE_ID, kind=CollectorKind.PRODUCT)
        )


def test_a_failed_transaction_leaves_nothing_behind(repository: Repository) -> None:
    """A document's sections and occurrences belong together — half of them is worse than none."""
    with pytest.raises(RuntimeError):
        with repository.transaction():
            repository.save_substance(Substance(id="rolled-back", name="Rolled Back"))
            raise RuntimeError("boom")

    assert repository.products_for_substance("rolled-back") == []


def test_a_database_from_an_older_schema_is_refused_at_open_time(tmp_path: Path) -> None:
    """The guard that was dead: the schema used to be applied before the version was read.

    `PRAGMA user_version = N` is unconditional, so applying the file first stamped the
    expected value and the comparison could never fail. A database still carrying a
    renamed column then opened cleanly and failed on the first write, far from the cause —
    exactly what this is meant to prevent.
    """
    stale = tmp_path / "stale.db"
    conn = sqlite3.connect(stale)
    conn.executescript(
        "PRAGMA user_version = 1;"
        "CREATE TABLE collectors (id TEXT PRIMARY KEY, source_id TEXT, source_kind TEXT);"
    )
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="schema version 1"):
        connect(stale)


def test_a_fresh_database_is_created_rather_than_refused(tmp_path: Path) -> None:
    """Version 0 means never initialised, which is the one case that should apply DDL."""
    conn = connect(tmp_path / "new.db")

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_reopening_does_not_reapply_the_schema(tmp_path: Path) -> None:
    """DDL in the request path takes a write lock on every read, and fsyncs the header."""
    path = tmp_path / "twice.db"
    connect(path).close()

    conn = sqlite3.connect(path)
    conn.execute("BEGIN")
    conn.execute("CREATE TABLE sentinel (x)")  # a lock a schema rewrite would collide with
    try:
        connect(path).close()  # must not need the write lock
    finally:
        conn.rollback()
        conn.close()


def test_a_document_for_a_product_that_does_not_exist_is_refused(
    repository: Repository,
) -> None:
    """Without the foreign key the label is stored and the manufacturer silently vanishes.

    `compare` keeps only products that have a document, so an orphan document is not a
    loud failure — it is a column missing from the comparison with nothing to explain it.
    """
    repository.save_source(Source(id=SOURCE_ID, name="S", base_url="https://example.test"))

    with pytest.raises(sqlite3.IntegrityError):
        with repository.transaction():
            repository.save_document(
                Document(
                    sha256="f" * 64,
                    source_id=SOURCE_ID,
                    product_external_id="no-such-product",
                    source_url="https://example.test/x",
                )
            )


def test_counted_in_sql_agrees_with_building_the_comparison(
    repository: Repository,
) -> None:
    """The whole justification for counting in storage: the answer must not change.

    `/substances` used to build a full `compare()` per substance to read three integers
    off it. If these two ever disagree the roster is quietly lying about a substance
    nobody opened.
    """
    from conftest import divergent_corpus
    from ixq.pipeline.diverge import compare

    divergent_corpus(repository)

    counted = repository.counts_by_substance()[SUBSTANCE_ID]
    built = compare(SUBSTANCE_ID, repository)

    assert counted.products == len(built.products)
    assert counted.concepts == len(built.rows)
    assert counted.divergent == len(built.divergent)


def test_a_substance_with_nothing_collected_is_absent_not_zero(
    repository: Repository,
) -> None:
    """The caller holds the roster; storage only reports what it has."""
    repository.save_source(Source(id=SOURCE_ID, name="S", base_url="https://example.test"))
    repository.save_substance(Substance(id=SUBSTANCE_ID, name="Ex"))

    assert repository.counts_by_substance() == {}


def test_placement_codes_sort_in_precedence_order() -> None:
    """`counts_by_substance` uses MIN(section_code) to collapse to the strongest placement.

    That is only correct while the codes sort lexicographically in the same order
    `PRECEDENCE` ranks them. The coupling is invisible in both places, and a placement code
    that broke it — a `4.10`, or a non-numeric code — would change the roster's counts with
    every test still green.
    """
    from ixq.pipeline.diverge import PRECEDENCE

    ranked = [placement.value for placement in PRECEDENCE]

    assert ranked == sorted(ranked), f"MIN() would no longer pick the strongest: {ranked}"


def test_section_codes_come_back_without_the_section_text(
    repository: Repository, seeded_product: Product
) -> None:
    """`compare` needs the codes to say what was scanned; it never needs the bodies.

    Asking for whole sections meant one query per document, each returning the full label
    text, to build a set of four short strings.
    """
    codes = repository.section_codes_for_substance(SUBSTANCE_ID)

    assert codes == {DOC_SHA: (SECTION.code,)}


def test_section_codes_are_grouped_per_document(repository: Repository) -> None:
    """Two products' codes must not pool: an absence is only defensible per label."""
    from conftest import divergent_corpus

    divergent_corpus(repository)

    codes = repository.section_codes_for_substance(SUBSTANCE_ID)

    assert len(codes) == 2
    assert all(found == ("4.3", "4.4") for found in codes.values())
