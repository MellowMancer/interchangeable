"""S1 and S2 against a stubbed label source — no network, no collector library."""

from typing import Any

import pytest

from ixq.domain import COMPARABLE, Product, Source, Substance
from ixq.pipeline.collect import collect, is_combination
from ixq.domain.sections import STORED_ONLY
from ixq.pipeline.fetch import SECTIONS, fetch
from ixq.pipeline.ports import Repository
from conftest import SOURCE_ID, SUBSTANCE_ID

SOURCE = Source(
    id=SOURCE_ID,
    name="Example Source",
    base_url="https://example.test",
    search_url="https://example.test/search?q={query}&limit=200",
    product_url="https://example.test/product/{external_id}",
)
SUBSTANCE = Substance(id=SUBSTANCE_ID, name="Example Substance")


class StubLabels:
    """Returns queued rows and records the URLs it was asked for."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.urls: list[str] = []

    def rows(self, collector_id: str, urls) -> list[dict[str, Any]]:
        self.urls.extend(urls)
        return self._rows


def _row(name: str, pid: str, company: str = "Acme Ltd") -> dict[str, Any]:
    return {
        "product_name": name,
        "product_url": f"https://example.test/product/{pid}/smpc",
        "company": company,
    }


def test_combination_products_are_excluded_concentrations_are_not() -> None:
    """A combination joins two substance names; a concentration joins a number and a unit."""
    assert is_combination("Alogliptin/Metformin Hydrochloride 12.5 mg/1000 mg")
    assert is_combination("Glimepiride/Metformin 3mg/1000mg tablet")
    assert not is_combination("Ramipril 2.5 mg/5 ml Oral solution")
    assert not is_combination("Ramipril 10 mg/5 ml Oral solution")
    assert not is_combination("Glucophage 500 mg film coated tablets")


def test_collect_keeps_single_substance_products_only(repository: Repository) -> None:
    labels = StubLabels(
        [
            _row("Example 10mg Tablets", "1001"),
            _row("Example 2.5 mg/5 ml Oral solution", "1002"),
            _row("Alogliptin/Example Hydrochloride", "1003"),
        ]
    )
    repository.save_source(SOURCE)

    products = collect(SUBSTANCE, SOURCE, "c_search", labels, repository)

    assert [p.external_id for p in products] == ["1001", "1002"]
    assert labels.urls == ["https://example.test/search?q=Example+Substance&limit=200"]


def test_search_queries_are_percent_encoded(repository: Repository) -> None:
    """A raw space makes a malformed URL, and a raw `&` truncates the query at that point."""
    repository.save_source(SOURCE)
    labels = StubLabels([])

    collect(Substance(id="x", name="Insulin glargine & co"), SOURCE, "c", labels, repository)

    assert labels.urls == [
        "https://example.test/search?q=Insulin+glargine+%26+co&limit=200"
    ]


def test_combination_products_named_with_and_are_excluded() -> None:
    """`Amlodipine and Valsartan` is a combination; the slash form is not the only one."""
    assert is_combination("Amlodipine and Valsartan 5 mg/160 mg film-coated tablets")
    assert not is_combination("Ramipril 2.5 mg/5 ml Oral solution")


def test_collect_is_idempotent_across_reruns(repository: Repository) -> None:
    """Re-collecting must update products, never duplicate them."""
    repository.save_source(SOURCE)
    labels = StubLabels([_row("Example 10mg Tablets", "1001")])

    collect(SUBSTANCE, SOURCE, "c_search", labels, repository)
    collect(SUBSTANCE, SOURCE, "c_search", labels, repository)

    assert len(repository.products_for_substance(SUBSTANCE_ID)) == 1


def test_collect_takes_the_holder_from_the_search_row(repository: Repository) -> None:
    """Search returns a clean company; the product page carries a postal address."""
    repository.save_source(SOURCE)
    labels = StubLabels([_row("Example 10mg Tablets", "1001", company="Sandoz Limited")])

    products = collect(SUBSTANCE, SOURCE, "c_search", labels, repository)

    assert products[0].ma_holder == "Sandoz Limited"


def test_collect_skips_rows_with_no_resolvable_id(repository: Repository) -> None:
    repository.save_source(SOURCE)
    labels = StubLabels([{"product_name": "Example 10mg Tablets", "product_url": ""}])

    assert collect(SUBSTANCE, SOURCE, "c_search", labels, repository) == []


def _seed(repository: Repository) -> Product:
    repository.save_source(SOURCE)
    repository.save_substance(SUBSTANCE)
    product = Product(
        source_id=SOURCE_ID,
        external_id="987",
        substance_id=SUBSTANCE_ID,
        name="Example 10mg Tablets",
    )
    repository.save_product(product)
    return product


PRODUCT_ROW = {
    "product_name": "Example 10mg Tablets",
    "section_4_3_contraindications": "Hypersensitivity to the active substance.",
    "section_4_4_warnings": "Use with caution in renal impairment.",
    "section_4_6_pregnancy_lactation": "Not recommended during pregnancy.",
}


def test_fetch_stores_every_section_verbatim(repository: Repository) -> None:
    product = _seed(repository)
    labels = StubLabels([PRODUCT_ROW])

    document = fetch(product, SOURCE, "c_product", labels, repository)

    assert document is not None
    sections = {s.code: s for s in repository.sections_for_document(document.sha256)}
    assert set(sections) == {"4.3", "4.4", "4.6"}
    assert sections["4.3"].text == PRODUCT_ROW["section_4_3_contraindications"]
    assert labels.urls == ["https://example.test/product/987"]


def test_fetch_is_content_addressed_and_idempotent(repository: Repository) -> None:
    """The same label fetched twice is one document, so re-runs cost nothing downstream."""
    product = _seed(repository)

    first = fetch(product, SOURCE, "c_product", StubLabels([PRODUCT_ROW]), repository)
    second = fetch(product, SOURCE, "c_product", StubLabels([dict(PRODUCT_ROW)]), repository)

    assert first is not None and second is not None
    assert first.sha256 == second.sha256


def test_fetch_reports_an_empty_result_rather_than_storing_a_hollow_document(
    repository: Repository,
) -> None:
    product = _seed(repository)

    assert fetch(product, SOURCE, "c_product", StubLabels([]), repository) is None


def test_fetch_skips_a_section_the_label_does_not_have(repository: Repository) -> None:
    """Not every label carries 4.6; a missing section is absent, not empty."""
    product = _seed(repository)
    row = dict(PRODUCT_ROW, section_4_6_pregnancy_lactation=None)

    document = fetch(product, SOURCE, "c_product", StubLabels([row]), repository)

    assert document is not None
    assert {s.code for s in repository.sections_for_document(document.sha256)} == {"4.3", "4.4"}


def test_a_revised_label_is_stored_alongside_the_previous_one(repository: Repository) -> None:
    """One URL yields a new document each time its label changes — that history is the point."""
    product = _seed(repository)
    revised = dict(PRODUCT_ROW, section_4_3_contraindications="Hypersensitivity. Renal failure.")

    first = fetch(product, SOURCE, "c_product", StubLabels([PRODUCT_ROW]), repository)
    second = fetch(product, SOURCE, "c_product", StubLabels([revised]), repository)

    assert first is not None and second is not None
    assert first.sha256 != second.sha256
    assert first.source_url == second.source_url


def test_digest_ignores_fields_that_are_not_the_label(repository: Repository) -> None:
    """A collector echoes its input; that must not give an unchanged label a new address."""
    product = _seed(repository)
    noisy = dict(PRODUCT_ROW, input={"url": "https://example.test/product/987"}, run_id="abc")

    plain = fetch(product, SOURCE, "c_product", StubLabels([PRODUCT_ROW]), repository)
    echoed = fetch(product, SOURCE, "c_product", StubLabels([noisy]), repository)

    assert plain is not None and echoed is not None
    assert plain.sha256 == echoed.sha256


def test_a_heal_that_renames_the_section_fields_is_a_break_not_an_empty_label(
    repository: Repository,
) -> None:
    """The row shape production actually produces — which the old guard could not reject.

    `HealerLabelSource` builds rows with `ProductRow.model_validate(...).model_dump()`, so
    every declared field is present as a key whatever the collector returned, and
    `extra="allow"` keeps a renamed key *alongside* them. Testing `field in row` was
    therefore always true and the guard was unfalsifiable; the earlier version of this
    test passed a bare `{"product_name": "X"}`, a shape no collector can emit.
    """
    from ixq.adapters.brightdata import ProductRow

    product = _seed(repository)
    renamed = ProductRow.model_validate(
        {"product_name": "X", "section_4_3_contra_indications": "Hypersensitivity."}
    ).model_dump()

    assert all(field in renamed for field in SECTIONS), "the shape the old guard passed"

    with pytest.raises(ValueError, match="no clinical section content"):
        fetch(product, SOURCE, "c_product", StubLabels([renamed]), repository)


def test_two_products_with_identical_labels_stay_two_documents(
    repository: Repository,
) -> None:
    """Generics from one contract manufacturer can be byte-identical.

    `documents.sha256` is the primary key with `ON CONFLICT DO NOTHING`, so a shared
    content address silently discards the second product's document — and `compare` then
    omits that manufacturer entirely, which reads as having no opinion rather than as
    data loss.
    """
    identical = {
        "product_name": "Same Label",
        "section_4_3_contraindications": "Hypersensitivity to the active substance.",
    }
    first = _seed(repository)
    second = Product(
        source_id=SOURCE.id,
        external_id="9999",
        substance_id=first.substance_id,
        name="Other 5mg Tablets",
        ma_holder="Other Ltd",
    )
    repository.save_product(second)

    a = fetch(first, SOURCE, "c_product", StubLabels([identical]), repository)
    b = fetch(second, SOURCE, "c_product", StubLabels([identical]), repository)

    assert a is not None and b is not None
    assert a.sha256 != b.sha256


@pytest.mark.parametrize(
    ("name", "combination"),
    [
        ("Cefotaxime 1g Powder and Solvent for Solution for Injection", False),
        ("Ceftriaxone Powder and Solvent for Solution for Infusion", False),
        ("Ramipril 2.5 mg/5 ml Oral solution", False),
        ("Tritace 5mg Tablets", False),
        ("Perindopril and Indapamide 4mg/1.25mg Tablets", True),
        ("Amlodipine/Valsartan 5mg/80mg Film-coated Tablets", True),
        # A combination that ALSO names its presentation. Counting presentation words
        # anywhere in the name admitted these into a single-substance comparison — a
        # worse error than the dropped `Powder and Solvent` the rule exists to prevent.
        ("Amoxicillin and Clavulanic Acid Powder for Oral Suspension", True),
        ("Amoxicillin and Clavulanic Acid Powder and Solvent for Suspension", True),
        ("Amlodipine/Valsartan Powder for Solution for Infusion", True),
    ],
)
def test_a_presentation_is_not_a_combination(name: str, combination: bool) -> None:
    """Judged on the words either side of the join, not on the name as a whole.

    Both directions are silent failures: a false positive drops a manufacturer from the
    roster, and a false negative puts a two-substance label in a column beside
    mono-substance ones.
    """
    assert is_combination(name) is combination


_APPEARANCE_CODE = next(s.code for s in STORED_ONLY if s.field == "section_3_pharmaceutical_form")

APPEARANCE_ROW = dict(
    PRODUCT_ROW, section_3_pharmaceutical_form="Pale red oblong tablet, 8 x 4 mm."
)


def test_fetch_stores_the_appearance_as_its_own_section(repository: Repository) -> None:
    """§3 is persisted like any other section — and is not one the comparison may read."""
    product = _seed(repository)

    document = fetch(product, SOURCE, "c_product", StubLabels([APPEARANCE_ROW]), repository)

    assert document is not None
    sections = {s.code: s.text for s in repository.sections_for_document(document.sha256)}
    assert sections[_APPEARANCE_CODE] == APPEARANCE_ROW["section_3_pharmaceutical_form"]
    assert _APPEARANCE_CODE not in COMPARABLE


def test_an_appearance_without_any_scanned_section_is_still_a_break(
    repository: Repository,
) -> None:
    """A row carrying only §3 is a moved collector, not a label with no contraindications."""
    product = _seed(repository)
    row = {"product_name": "X", "section_3_pharmaceutical_form": "White round tablet."}

    with pytest.raises(ValueError, match="no clinical section content"):
        fetch(product, SOURCE, "c_product", StubLabels([row]), repository)


def test_a_label_with_no_appearance_stores_none(repository: Repository) -> None:
    """Today's collector returns no §3. Nothing must appear where nothing was collected."""
    product = _seed(repository)

    document = fetch(product, SOURCE, "c_product", StubLabels([PRODUCT_ROW]), repository)

    assert document is not None
    codes = {s.code for s in repository.sections_for_document(document.sha256)}
    assert _APPEARANCE_CODE not in codes


def test_an_undeclared_appearance_field_survives_the_row_model() -> None:
    """`ProductRow` does not declare §3 — the collector does not return it yet.

    `extra="allow"` is what carries it through the moment the collector does, so the
    pipeline needs no change on the day that lands. Asserted rather than assumed: a
    stricter model config here would drop the field silently.
    """
    from ixq.adapters.brightdata import ProductRow

    dumped = ProductRow.model_validate(APPEARANCE_ROW).model_dump()

    assert dumped["section_3_pharmaceutical_form"] == "Pale red oblong tablet, 8 x 4 mm."

RECORD_ROW = PRODUCT_ROW | {
    "section_6_1_excipients": "Lactose monohydrate\nMaize starch",
    "emc_last_updated": "10 Jul 2026",
    "company_id": 3006,
    "ingredient_id": 1065,
    "atc_code": "C09AA05",
    "legal_status": "Prescription only medicine",
    "section_8_ma_number": "PL 16363/0356",
    "discontinued": False,
}
"""A row in the shape the healed collector actually returns, values from product 7142."""


def test_the_source_record_is_stored_beside_the_label(repository: Repository) -> None:
    """The fields exist to be read back, not merely accepted by the row model."""
    product = _seed(repository)
    fetch(product, SOURCE, "c_product", StubLabels([RECORD_ROW]), repository)

    stored = repository.documents_for_substance(SUBSTANCE_ID)[0]
    assert stored.holder_id == 3006
    assert stored.ingredient_id == 1065
    assert stored.atc_code == "C09AA05"
    assert stored.legal_status == "Prescription only medicine"
    assert stored.ma_number == "PL 16363/0356"
    assert stored.listing_updated == "10 Jul 2026"
    assert stored.discontinued is False


def test_excipients_are_stored_as_a_section_and_widen_what_was_scanned(
    repository: Repository,
) -> None:
    """Section 6.1 is a section like any other, so it is classified and enters `scanned`.

    Storing it without it reaching `scanned` would be the worse of both worlds: the text
    would be read but every absence would still be claimed against 4.3-4.6 alone.
    """
    product = _seed(repository)
    document = fetch(product, SOURCE, "c_product", StubLabels([RECORD_ROW]), repository)

    assert document is not None
    codes = [s.code for s in repository.sections_for_document(document.sha256)]
    assert "6.1" in codes
    scanned = repository.section_codes_for_substance(SUBSTANCE_ID)[document.sha256]
    assert "6.1" in scanned


def test_a_row_carrying_only_excipients_is_a_break(repository: Repository) -> None:
    """Section 6.1 alone must not satisfy the guard.

    It is the newest field in the mapping, so a partial rename that leaves it standing is
    exactly the case that would otherwise store a document with no comparable content.
    """
    product = _seed(repository)
    only_excipients = {"product_name": "X", "section_6_1_excipients": "Lactose monohydrate"}

    with pytest.raises(ValueError, match="no clinical section content"):
        fetch(product, SOURCE, "c_product", StubLabels([only_excipients]), repository)


def test_the_record_is_refreshed_on_re_fetch_without_forking_the_document(
    repository: Repository,
) -> None:
    """A product going discontinued must be recorded, not discarded as a duplicate.

    The listing columns are deliberately outside the content address, so an unchanged
    label keeps one document - but `ON CONFLICT DO NOTHING` would then throw the new
    status away, which is how a comparison keeps claiming a product is still sold.
    """
    product = _seed(repository)
    first = fetch(product, SOURCE, "c_product", StubLabels([RECORD_ROW]), repository)
    later = fetch(
        product,
        SOURCE,
        "c_product",
        StubLabels([RECORD_ROW | {"discontinued": True}]),
        repository,
    )

    assert first is not None and later is not None
    assert first.sha256 == later.sha256, "the label did not change, nor did its address"
    documents = repository.documents_for_substance(SUBSTANCE_ID)
    assert len(documents) == 1, "a status badge must not manufacture a revision"
    assert documents[0].discontinued is True


def test_a_missing_discontinued_flag_is_not_a_live_product(repository: Repository) -> None:
    """None and False are different claims: unknown versus observed-absent.

    Every document fetched before the field existed has None, and collapsing that to False
    would assert those products were actively marketed on evidence nobody collected.
    """
    product = _seed(repository)
    fetch(product, SOURCE, "c_product", StubLabels([PRODUCT_ROW]), repository)

    assert repository.documents_for_substance(SUBSTANCE_ID)[0].discontinued is None


STORED_ONLY_ROW = dict(
    PRODUCT_ROW,
    section_4_1_indications="Treatment of hypertension.",
    section_6_3_shelf_life="2 years",
    section_6_4_storage="Do not store above 25°C.",
)


def test_fetch_stores_the_sections_that_are_not_placements(repository: Repository) -> None:
    """§4.1, §6.3 and §6.4 are collected and kept — they describe rather than file."""
    product = _seed(repository)

    document = fetch(product, SOURCE, "c_product", StubLabels([STORED_ONLY_ROW]), repository)

    stored = {s.code: s.text for s in repository.sections_for_document(document.sha256)}
    assert stored["4.1"] == "Treatment of hypertension."
    assert stored["6.3"] == "2 years"
    assert stored["6.4"] == "Do not store above 25°C."


def test_none_of_the_stored_only_sections_is_comparable(repository: Repository) -> None:
    """The invariant every absence claim rests on: only placements enter the comparison.

    If one of these ever became a `Placement`, `compare()` would file a shelf life as
    though it were a safety section, and `scanned` would claim it was read for concepts.
    """
    for spec in STORED_ONLY:
        assert spec.code not in COMPARABLE


def test_a_row_of_only_stored_only_sections_is_still_a_break(repository: Repository) -> None:
    """A collector returning descriptions but no clinical section has moved, not gone quiet."""
    product = _seed(repository)
    row = {
        "product_name": "X",
        "section_4_1_indications": "Treatment of hypertension.",
        "section_6_3_shelf_life": "2 years",
    }

    with pytest.raises(ValueError, match="no clinical section content"):
        fetch(product, SOURCE, "c_product", StubLabels([row]), repository)
