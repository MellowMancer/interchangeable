"""Exit criterion: an Occurrence round-trips through the Repository port intact."""

from preward.domain import Document, Product, Section, Substance, found_in
from preward.pipeline.ports import Repository
from conftest import DOC_SHA, PRODUCT_EXTERNAL_ID, SECTION, SOURCE_ID, SUBSTANCE_ID


def test_product_save_assigns_id(seeded_product: Product) -> None:
    assert seeded_product.id is not None


def test_product_save_is_idempotent(repository: Repository, seeded_product: Product) -> None:
    """Re-collecting the same product must update it, not duplicate it."""
    again = repository.save_product(
        Product(
            source_id=SOURCE_ID,
            external_id=PRODUCT_EXTERNAL_ID,
            substance_id=SUBSTANCE_ID,
            name="Example 10mg Tablets (renamed)",
            ma_holder="Example Holder Ltd",
        )
    )

    assert again.id == seeded_product.id
    assert [p.name for p in repository.products_for_substance(SUBSTANCE_ID)] == [
        "Example 10mg Tablets (renamed)"
    ]


def test_occurrence_round_trips_with_its_offsets(
    repository: Repository, seeded_product: Product
) -> None:
    saved = repository.save_occurrence(found_in(SECTION, DOC_SHA, "renal", 42, 65))

    loaded = repository.occurrences_for_substance(SUBSTANCE_ID)

    assert len(loaded) == 1
    assert loaded[0].id == saved.id
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
