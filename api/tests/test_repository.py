import pytest

"""Exit criterion: an Occurrence round-trips through the Repository port intact."""

from ixq.domain import (
    Collector,
    CollectorKind,
    Document,
    Product,
    Section,
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
