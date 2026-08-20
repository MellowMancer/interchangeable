"""S5. The matrix, and the discipline that keeps `absent` honest."""

from ixq.domain import Document, Occurrence, Placement, Product, Section, Source, Substance
from ixq.pipeline.diverge import compare
from ixq.pipeline.ports import Repository
from conftest import SOURCE_ID, SUBSTANCE_ID

SECTION_43 = "Hypersensitivity to the active substance."
SECTION_44 = "Use with caution in renal impairment."


def _label(repository: Repository, external_id: str, holder: str, sections: dict[str, str]) -> str:
    repository.save_product(
        Product(
            source_id=SOURCE_ID,
            external_id=external_id,
            substance_id=SUBSTANCE_ID,
            name=f"Example {external_id}",
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
        )
    )
    for code, text in sections.items():
        repository.save_section(sha, Section(code=code, heading=code, text=text))
    return sha


def _occurrence(repository: Repository, sha: str, code: str, concept: str, text: str) -> None:
    repository.save_occurrence(
        Occurrence(
            document_sha256=sha,
            section_code=code,
            concept=concept,
            quote=text,
            char_start=0,
            char_end=len(text),
        )
    )


def _seed_source(repository: Repository) -> None:
    repository.save_source(
        Source(id=SOURCE_ID, name="Example", base_url="https://example.test")
    )
    repository.save_substance(Substance(id=SUBSTANCE_ID, name="Example"))


def _two_manufacturers(repository: Repository) -> None:
    _seed_source(repository)
    a = _label(repository, "1001", "Alpha Ltd", {"4.3": SECTION_43, "4.4": SECTION_44})
    b = _label(repository, "1002", "Beta Ltd", {"4.3": SECTION_43, "4.4": SECTION_44})
    _occurrence(repository, a, "4.3", "hypersensitivity", SECTION_43)
    _occurrence(repository, b, "4.3", "hypersensitivity", SECTION_43)
    _occurrence(repository, a, "4.3", "renal", SECTION_43)   # Alpha bars it outright
    _occurrence(repository, b, "4.4", "renal", SECTION_44)   # Beta only warns


def test_agreement_is_not_divergence(repository: Repository) -> None:
    _two_manufacturers(repository)

    result = compare(SUBSTANCE_ID, repository)
    shared = next(r for r in result.rows if r.concept == "hypersensitivity")

    assert not shared.diverges
    assert set(shared.placements.values()) == {Placement.CONTRAINDICATION}


def test_the_same_concept_in_different_sections_is_a_divergence(
    repository: Repository,
) -> None:
    """Contraindicated by one manufacturer and merely cautioned by another is the finding."""
    _two_manufacturers(repository)

    row = next(r for r in compare(SUBSTANCE_ID, repository).rows if r.concept == "renal")

    assert row.diverges
    assert row.placements["1001"] is Placement.CONTRAINDICATION
    assert row.placements["1002"] is Placement.WARNING


def test_divergent_rows_are_surfaced_separately(repository: Repository) -> None:
    _two_manufacturers(repository)

    result = compare(SUBSTANCE_ID, repository)

    assert [r.concept for r in result.divergent] == ["renal"]


def test_a_concept_absent_from_one_label_reports_absent(repository: Repository) -> None:
    _seed_source(repository)
    a = _label(repository, "1001", "Alpha Ltd", {"4.3": SECTION_43})
    _label(repository, "1002", "Beta Ltd", {"4.3": SECTION_43})
    _occurrence(repository, a, "4.3", "washout", SECTION_43)

    row = next(r for r in compare(SUBSTANCE_ID, repository).rows if r.concept == "washout")

    assert row.placements["1001"] is Placement.CONTRAINDICATION
    assert row.placements["1002"] is Placement.ABSENT
    assert row.diverges


def test_the_scanned_sections_travel_with_the_comparison(repository: Repository) -> None:
    """`absent` means absent from these sections — a reader cannot judge it without them."""
    _two_manufacturers(repository)

    assert compare(SUBSTANCE_ID, repository).scanned == ("4.3", "4.4")


def test_the_strongest_placement_wins_when_a_concept_appears_twice(
    repository: Repository,
) -> None:
    """Showing the warning when the label also contraindicates would understate it."""
    _seed_source(repository)
    a = _label(repository, "1001", "Alpha Ltd", {"4.3": SECTION_43, "4.4": SECTION_44})
    _occurrence(repository, a, "4.4", "renal", SECTION_44)
    _occurrence(repository, a, "4.3", "renal", SECTION_43)

    row = next(r for r in compare(SUBSTANCE_ID, repository).rows if r.concept == "renal")

    assert row.placements["1001"] is Placement.CONTRAINDICATION


def test_a_substance_with_no_labels_compares_to_nothing(repository: Repository) -> None:
    _seed_source(repository)

    result = compare(SUBSTANCE_ID, repository)

    assert result.rows == () and result.products == () and result.scanned == ()
