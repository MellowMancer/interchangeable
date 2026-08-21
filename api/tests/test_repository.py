"""Exit criterion: an Occurrence round-trips through the Repository port intact."""

import sqlite3
from pathlib import Path

import pytest

from ixq.adapters.sqlite.repository import SCHEMA_VERSION, connect
from ixq.domain import (
    UNCLASSIFIED,
    Collector,
    CollectorKind,
    Document,
    Placement,
    Product,
    Section,
    Source,
    Substance,
    appearance,
    found_in,
)
from ixq.pipeline.ports import ClauseCounts, Repository
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


def test_one_sections_text_can_be_read_without_the_rest_of_the_label(
    repository: Repository, seeded_product: Product
) -> None:
    """Showing a quote in context needs the one body it was sliced from, not four of them."""
    text = repository.section_text(DOC_SHA, SECTION.code)

    assert text == SECTION.text
    assert text[42:65] == "Severe renal impairment"


def test_a_section_the_document_never_had_reads_as_none_rather_than_empty(
    repository: Repository, seeded_product: Product
) -> None:
    """Never stored and stored empty are different claims about what was scanned."""
    assert repository.section_text(DOC_SHA, "4.5") is None


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


def test_previewed_divergences_agree_with_building_the_comparison(
    repository: Repository,
) -> None:
    """The roster previews concepts it never compares. It must not advertise the wrong ones.

    Same justification as the counts above: the index screen names a substance's
    disagreements from SQL, and a card that promised a concept the comparison does not
    show would be a lie told to whoever chose not to click.
    """
    from conftest import divergent_corpus
    from ixq.pipeline.diverge import compare

    divergent_corpus(repository)

    previewed = repository.divergences_by_substance()[SUBSTANCE_ID]
    built = compare(SUBSTANCE_ID, repository)

    assert {d.concept for d in previewed} == {row.concept for row in built.divergent}
    for preview in previewed:
        row = next(r for r in built.rows if r.concept == preview.concept)
        assert set(preview.placements) == {p.value for p in row.placements.values()} | (
            {Placement.ABSENT.value} if len(row.placements) < len(built.products) else set()
        )


def test_a_lone_product_has_nothing_to_disagree_with(
    repository: Repository, seeded_product: Product
) -> None:
    """One manufacturer cannot diverge from itself, and must not be previewed as if it had."""
    repository.save_occurrence(found_in(SECTION, DOC_SHA, "renal", 0, 20))

    assert repository.divergences_by_substance().get(SUBSTANCE_ID, ()) == ()


def test_clause_counts_split_what_the_lexicon_matched_from_what_it_missed(
    repository: Repository, seeded_product: Product
) -> None:
    """The recall gap is published as counts, so the counting must be right."""
    repository.save_occurrence(found_in(SECTION, DOC_SHA, "renal", 0, 20))
    repository.save_occurrence(found_in(SECTION, DOC_SHA, UNCLASSIFIED, 20, 40))
    repository.save_occurrence(found_in(SECTION, DOC_SHA, UNCLASSIFIED, 40, 60))

    counted = repository.clause_counts(SUBSTANCE_ID)

    assert counted.classified == 1
    assert counted.unclassified == 2


def test_clause_counts_are_zero_for_a_substance_with_nothing_stored(
    repository: Repository,
) -> None:
    """Nothing collected is nothing counted, never a gap of unknown size."""
    assert repository.clause_counts("nonesuch") == ClauseCounts(classified=0, unclassified=0)


def _describe(repository: Repository, text: str) -> None:
    """Store the seeded document's §3, the way `fetch` will once the collector returns it."""
    repository.save_section(
        DOC_SHA,
        Section(code=appearance.SECTION_CODE, heading="Pharmaceutical form", text=text),
    )


def test_the_appearance_comes_back_keyed_by_the_document_it_belongs_to(
    repository: Repository, seeded_product: Product
) -> None:
    """Keyed by document, so a revised label cannot show the previous one's description."""
    described = "Orange/White size '4' hard gelatin capsules."
    _describe(repository, described)

    assert repository.appearances_for_substance(SUBSTANCE_ID) == {DOC_SHA: described}


def test_a_label_with_no_appearance_stored_is_absent_not_empty(
    repository: Repository, seeded_product: Product
) -> None:
    """"Nobody described it" and "described as nothing" are different claims."""
    assert repository.appearances_for_substance(SUBSTANCE_ID) == {}


def test_the_appearance_query_reads_no_other_section(
    repository: Repository, seeded_product: Product
) -> None:
    """§4.4 runs to kilobytes; this must never be a way to drag one back."""
    _describe(repository, "Red tablet.")

    assert list(repository.appearances_for_substance(SUBSTANCE_ID).values()) == ["Red tablet."]


def _revision(repository: Repository, sha: str, fetched_at: str, concept: str) -> None:
    """A revision of the seeded product, carrying one concept of its own.

    `fetched_at` is stamped by SQL, so every revision written inside one test shares a
    second and the ordering would fall to the sha tiebreak. Setting it explicitly makes
    which revision is current a property of the test rather than of its literals.
    """
    repository.save_document(
        Document(
            sha256=sha,
            source_id=SOURCE_ID,
            product_external_id=PRODUCT_EXTERNAL_ID,
            source_url="https://example.test/product/1001",
        )
    )
    repository._conn.execute(  # noqa: SLF001 — the column is stamped in SQL, not by the entity
        "UPDATE documents SET fetched_at = ? WHERE sha256 = ?", (fetched_at, sha)
    )
    repository.save_section(sha, SECTION)
    repository.save_occurrence(found_in(SECTION, sha, concept, 0, 20))


def test_the_roster_reads_the_current_revision_not_every_one(
    repository: Repository, seeded_product: Product
) -> None:
    """The roster must describe the comparison it links to, not the history behind it.

    One URL yields a new document every time its label is revised, and that history is
    kept on purpose. `compare()` reduces it to the newest per product; a count that joined
    every revision advertised concepts the matrix does not show — and agreed only while
    newer revisions happened to be supersets of older ones.
    """
    # The fixture's own document is stamped `now`, so it would outrank any date written
    # here. Ordering all three explicitly is what makes "current" mean the newest.
    repository._conn.execute(  # noqa: SLF001
        "UPDATE documents SET fetched_at = ? WHERE sha256 = ?", ("2026-01-01 00:00:00", DOC_SHA)
    )
    _revision(repository, "b" * 64, "2026-02-01 00:00:00", "renal")
    _revision(repository, "c" * 64, "2026-03-01 00:00:00", "hepatic")

    counted = repository.counts_by_substance()[SUBSTANCE_ID]
    clauses = repository.clause_counts(SUBSTANCE_ID)

    assert counted.concepts == 1, "the superseded revision's concept must not be counted"
    assert clauses.classified == 1, "the recall gap must describe the current revision only"


def test_the_roster_leaves_the_recall_gap_out_of_its_divergence_count(
    repository: Repository, seeded_product: Product
) -> None:
    """`unclassified` is a parser gap, and the screen holds it out of the concept list.

    Counting it as divergent made the card's header exceed the list printed beneath it.
    """
    repository.save_occurrence(found_in(SECTION, DOC_SHA, UNCLASSIFIED, 0, 20))

    counted = repository.counts_by_substance()[SUBSTANCE_ID]
    previews = repository.divergences_by_substance().get(SUBSTANCE_ID, ())

    assert all(p.concept != UNCLASSIFIED for p in previews)
    assert counted.divergent == len(previews), "header and body must describe one set"
