"""The seam the UI reads. Shapes are the contract; the UI never opens SQLite."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ixq.domain import Section
from ixq.pipeline.ports import Repository
from conftest import SECTION_43, SOURCE_ID, SUBSTANCE_ID, divergent_corpus


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    """A repository on the same file the app will open, so no connection is shared."""
    from ixq.adapters.sqlite import SqliteRepository, connect

    return SqliteRepository(connect(tmp_path / "interchangeable.db"))


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    """The app against a throwaway database, wired exactly as it is in production."""
    from ixq.api import main

    config = tmp_path / "config"
    config.mkdir()
    (config / "substances.yaml").write_text(f"substances:\n  - {{id: {SUBSTANCE_ID}, name: Ex}}\n")
    (config / "sources.yaml").write_text(f"sources:\n  - {{id: {SOURCE_ID}, name: Example, base_url: 'https://example.test'}}\n")
    (config / "collectors.yaml").write_text(
        f"collectors:\n  - {{id: c_abc, source_id: {SOURCE_ID}, kind: product}}\n"
    )
    monkeypatch.setenv("IXQ_CONFIG_DIR", str(config))
    monkeypatch.setenv("IXQ_DATA_DIR", str(tmp_path))
    return TestClient(main.app)


def test_health_is_live(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_the_roster_reports_how_much_has_been_collected(
    client: TestClient, repository: Repository
) -> None:
    divergent_corpus(repository)

    body = client.get("/substances").json()

    assert body == [
        {
            "id": SUBSTANCE_ID,
            "name": "Ex",
            "products": 2,
            "concepts": 2,
            "divergent": 1,
            "divergences": [{"concept": "renal", "placements": ["4.3", "absent"]}],
            "labels": ["Ex 1", "Alpha Ltd", "Ex 2", "Beta Ltd"],
        }
    ]


def test_a_substance_with_nothing_collected_is_not_an_error(client: TestClient) -> None:
    """The roster lists what is configured; zero collected is a real state, not a 404."""
    body = client.get("/substances").json()

    assert body[0]["products"] == 0


def test_the_matrix_carries_the_scanned_sections(
    client: TestClient, repository: Repository
) -> None:
    """`absent` is unreadable without them, so they are part of the response, not metadata."""
    divergent_corpus(repository)

    columns = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]

    assert [c["scanned"] for c in columns] == [["4.3", "4.4"], ["4.3", "4.4"]]


def test_divergent_rows_come_first(client: TestClient, repository: Repository) -> None:
    divergent_corpus(repository)

    rows = client.get(f"/substances/{SUBSTANCE_ID}").json()["rows"]

    assert rows[0]["concept"] == "renal" and rows[0]["diverges"] is True
    assert rows[1]["diverges"] is False


def test_every_present_cell_carries_verifiable_evidence(
    client: TestClient, repository: Repository
) -> None:
    """A claim a reader cannot check against the source is not worth showing."""
    divergent_corpus(repository)

    rows = client.get(f"/substances/{SUBSTANCE_ID}").json()["rows"]
    renal = next(r for r in rows if r["concept"] == "renal")
    present = next(c for c in renal["cells"] if c["placement"] != "absent")
    missing = next(c for c in renal["cells"] if c["placement"] == "absent")

    assert present["evidence"]["quote"] == SECTION_43
    assert present["evidence"]["section_code"] == "4.3"
    assert present["evidence"]["source_url"].endswith("/product/1")
    assert missing["evidence"] is None


def test_columns_carry_the_revision_date(client: TestClient, repository: Repository) -> None:
    """A difference may be staleness rather than disagreement; the reader needs the date."""
    divergent_corpus(repository)

    products = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]

    assert {p["ma_holder"]: p["revised"] for p in products} == {
        "Alpha Ltd": "07/07/2026",
        "Beta Ltd": None,
    }


def test_an_uncollected_substance_matrix_is_a_404(client: TestClient) -> None:
    assert client.get("/substances/nonesuch").status_code == 404


def test_a_quote_arrives_inside_the_section_text_it_was_sliced_from(
    client: TestClient, repository: Repository
) -> None:
    """The core claim, made checkable: the window really does hold the quote it reports."""
    divergent_corpus(repository)

    body = client.get(f"/substances/{SUBSTANCE_ID}/concepts/renal").json()
    cell = next(c for c in body["cells"] if c["evidence"])
    window = cell["context"]

    assert window["text"][window["quote_start"] : window["quote_end"]] == cell["evidence"]["quote"]
    assert window["text"] in SECTION_43


def test_a_windows_relative_offsets_agree_with_the_absolute_ones(
    client: TestClient, repository: Repository
) -> None:
    """`char_start - quote_start` is where the window opens; if it drifts the highlight lies."""
    divergent_corpus(repository)

    body = client.get(f"/substances/{SUBSTANCE_ID}/concepts/renal").json()
    cell = next(c for c in body["cells"] if c["evidence"])
    evidence, window = cell["evidence"], cell["context"]

    opens_at = evidence["char_start"] - window["quote_start"]
    assert SECTION_43[opens_at : opens_at + len(window["text"])] == window["text"]
    assert evidence["char_end"] - evidence["char_start"] == window["quote_end"] - window["quote_start"]


def test_a_window_holding_the_whole_section_is_not_reported_as_cut(
    client: TestClient, repository: Repository
) -> None:
    """A truncation flag set on an untruncated window would invent text nobody withheld."""
    divergent_corpus(repository)

    body = client.get(f"/substances/{SUBSTANCE_ID}/concepts/renal").json()
    window = next(c for c in body["cells"] if c["evidence"])["context"]

    assert window["text"] == SECTION_43
    assert (window["truncated_start"], window["truncated_end"]) == (False, False)


def test_a_cell_with_no_evidence_has_no_context_window(
    client: TestClient, repository: Repository
) -> None:
    """An empty window would frame an absence exactly like a clause that was read."""
    divergent_corpus(repository)

    body = client.get(f"/substances/{SUBSTANCE_ID}/concepts/renal").json()
    absent = next(c for c in body["cells"] if c["placement"] == "absent")

    assert absent["evidence"] is None
    assert absent["context"] is None


def test_the_concept_response_carries_the_sections_scanned_for_each_label(
    client: TestClient, repository: Repository
) -> None:
    """An absence travels with its scope, so this screen needs no second request for it."""
    divergent_corpus(repository)

    body = client.get(f"/substances/{SUBSTANCE_ID}/concepts/renal").json()

    assert body["substance_name"] == "Ex"
    assert body["diverges"] is True
    assert [p["scanned"] for p in body["products"]] == [["4.3", "4.4"], ["4.3", "4.4"]]


def test_a_concept_matched_in_no_scanned_section_is_a_404(
    client: TestClient, repository: Repository
) -> None:
    """404 against the sections scanned — never a claim that the labels omit the concept."""
    divergent_corpus(repository)

    response = client.get(f"/substances/{SUBSTANCE_ID}/concepts/nonesuch")

    assert response.status_code == 404
    assert "scanned" in response.json()["detail"]


def test_an_uncollected_substance_concept_is_a_404(client: TestClient) -> None:
    assert client.get("/substances/nonesuch/concepts/renal").status_code == 404


def test_the_matrix_does_not_carry_section_text(
    client: TestClient, repository: Repository
) -> None:
    """The regression `counts_by_substance` exists to undo, guarded on the other endpoint.

    Every cell of every row would gain a multi-kilobyte label body, paid on every
    navigation, for the one cell a reader eventually opens.
    """
    divergent_corpus(repository)

    rows = client.get(f"/substances/{SUBSTANCE_ID}").json()["rows"]

    assert all(set(cell) == {"product_external_id", "placement", "evidence"}
               for row in rows for cell in row["cells"])


def test_collectors_are_listed_with_their_role(client: TestClient) -> None:
    body = client.get("/collectors").json()

    assert body == [
        {
            "id": "c_abc",
            "kind": "product",
            "source": "Example",
            "baseline_captured_at": None,
            "baseline_row_count": None,
            "heals": [],
        }
    ]


def test_a_collector_that_has_never_run_reports_no_baseline_rather_than_health(
    client: TestClient,
) -> None:
    """`None` is 'not yet observed'. Rendering it as healthy would invent an observation."""
    assert client.get("/collectors").json()[0]["baseline_captured_at"] is None


def test_a_collectors_heal_history_is_reported_newest_first(client: TestClient) -> None:
    from datetime import UTC, datetime

    from bdheal.models import HealEvent, HealStatus
    from bdheal.store import SqliteHealStore
    from bdheal.store import connect as heal_connect
    from ixq.settings import heal_database_path

    store = SqliteHealStore(heal_connect(heal_database_path()))
    for day, status in ((1, HealStatus.AWAITING_APPROVAL), (2, HealStatus.DONE)):
        store.save_heal_event(
            HealEvent(
                collector_id="c_abc",
                status=status,
                created_at=datetime(2026, 8, day, tzinfo=UTC),
                promoted=status is HealStatus.DONE,
            )
        )

    heals = client.get("/collectors").json()[0]["heals"]

    assert [h["status"] for h in heals] == [HealStatus.DONE, HealStatus.AWAITING_APPROVAL]
    assert heals[0]["promoted"] is True


def test_the_benchmark_reports_failures_alongside_successes(client: TestClient) -> None:
    """A benchmark that published only the cases that worked would be a claim, not a measurement."""
    from datetime import UTC, datetime

    from bdheal.models import BenchCase, MutationClass, SignalKind
    from bdheal.store import SqliteHealStore
    from bdheal.store import connect as heal_connect
    from ixq.settings import bench_database_path

    store = SqliteHealStore(heal_connect(bench_database_path()))
    store.save_bench_case(
        BenchCase(
            run_id="r1",
            case_id="missed",
            mutation=MutationClass.CLASS_RENAME,
            expected_signals=frozenset({SignalKind.SKELETON}),
            completed_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )
    store.save_bench_case(
        BenchCase(
            run_id="r1",
            case_id="repaired",
            mutation=MutationClass.WRAPPER_NESTING,
            expected_signals=frozenset({SignalKind.SKELETON}),
            caught_by=SignalKind.SKELETON,
            fired_kinds=frozenset({SignalKind.SKELETON}),
            healed=True,
            field_accuracy=1.0,
            non_regression_passed=True,
            attempts=1,
            completed_at=datetime(2026, 8, 2, tzinfo=UTC),
        )
    )

    cases = client.get("/benchmark").json()[0]["cases"]

    assert [c["case_id"] for c in cases] == ["missed", "repaired"]
    assert cases[0]["caught_by"] is None
    assert cases[0]["healed"] is False
    assert cases[1]["field_accuracy"] == 1.0
    assert cases[1]["non_regression_passed"] is True


def test_an_unscored_benchmark_case_is_null_rather_than_zero(client: TestClient) -> None:
    """Never scored and scored zero differ, and the screen must be able to tell them apart."""
    from datetime import UTC, datetime

    from bdheal.models import BenchCase, MutationClass, SignalKind
    from bdheal.store import SqliteHealStore
    from bdheal.store import connect as heal_connect
    from ixq.settings import bench_database_path

    store = SqliteHealStore(heal_connect(bench_database_path()))
    store.save_bench_case(
        BenchCase(
            run_id="r1",
            case_id="detected-not-repaired",
            mutation=MutationClass.TABLE_TO_DIV,
            expected_signals=frozenset({SignalKind.SKELETON}),
            caught_by=SignalKind.SKELETON,
            attempts=1,
            completed_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )

    case = client.get("/benchmark").json()[0]["cases"][0]

    assert case["field_accuracy"] is None
    assert case["non_regression_passed"] is None


def test_every_benchmark_run_is_returned_not_only_the_newest(client: TestClient) -> None:
    """Naming one run would let the endpoint publish the flattering half of a benchmark."""
    from datetime import UTC, datetime

    from bdheal.models import BenchCase, MutationClass, SignalKind
    from bdheal.store import SqliteHealStore
    from bdheal.store import connect as heal_connect
    from ixq.settings import bench_database_path

    store = SqliteHealStore(heal_connect(bench_database_path()))
    for run_id, day in (("later", 2), ("earlier", 1)):
        store.save_bench_case(
            BenchCase(
                run_id=run_id,
                case_id="case",
                mutation=MutationClass.CLASS_RENAME,
                expected_signals=frozenset({SignalKind.SKELETON}),
                completed_at=datetime(2026, 8, day, tzinfo=UTC),
            )
        )

    assert [run["run_id"] for run in client.get("/benchmark").json()] == ["earlier", "later"]


def test_the_benchmark_reads_its_own_store_not_the_heal_store(client: TestClient) -> None:
    """A rehearsal and a production incident must not arrive through the same route."""
    from datetime import UTC, datetime

    from bdheal.models import BenchCase, MutationClass, SignalKind
    from bdheal.store import SqliteHealStore
    from bdheal.store import connect as heal_connect
    from ixq.settings import heal_database_path

    store = SqliteHealStore(heal_connect(heal_database_path()))
    store.save_bench_case(
        BenchCase(
            run_id="r1",
            case_id="written-to-the-wrong-file",
            mutation=MutationClass.CLASS_RENAME,
            expected_signals=frozenset({SignalKind.SKELETON}),
            completed_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
    )

    assert client.get("/benchmark").json() == []


def test_the_matrix_carries_the_recall_gap_as_counts(
    client: TestClient, repository: Repository
) -> None:
    """Two numbers, never a ratio: one substance cannot support a claim about recall."""
    divergent_corpus(repository)

    clauses = client.get(f"/substances/{SUBSTANCE_ID}").json()["clauses"]

    assert set(clauses) == {"classified", "unclassified"}
    assert clauses["classified"] > 0


def test_a_context_window_reports_the_length_of_the_section_it_came_from(
    client: TestClient, repository: Repository
) -> None:
    """Without it a clause at the end of a section is indistinguishable from one at the start."""
    divergent_corpus(repository)

    rows = client.get(f"/substances/{SUBSTANCE_ID}").json()["rows"]
    concept = next(r["concept"] for r in rows if any(c["evidence"] for c in r["cells"]))
    cells = client.get(f"/substances/{SUBSTANCE_ID}/concepts/{concept}").json()["cells"]
    context = next(c["context"] for c in cells if c["context"])

    assert context["section_length"] >= len(context["text"])
    assert context["section_length"] >= context["quote_end"]


def _describe(repository: Repository, sha: str, text: str) -> None:
    """Store one label's §3, the way `fetch` will once the collector returns it."""
    from ixq.domain import Section, appearance

    with repository.transaction():
        repository.save_section(
            sha, Section(code=appearance.SECTION_CODE, heading="Pharmaceutical form", text=text)
        )


def test_a_column_carries_the_appearance_its_label_describes(
    client: TestClient, repository: Repository
) -> None:
    """Parsed at the seam, so the UI draws from data and never parses prose itself."""
    divergent_corpus(repository)
    _describe(
        repository,
        "1".rjust(64, "0"),
        "Orange/White size '4' hard gelatin capsules imprinted with 'D' on orange cap "
        "and '41' on white body with black edible ink",
    )

    columns = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]
    described = next(c for c in columns if c["external_id"] == "1")["appearance"]

    assert described["colours"] == ["orange", "white"]
    assert described["shape"] == "capsule"
    assert described["imprints"] == ["D", "41"]
    assert described["length_mm"] is None, "this label states no dimensions"
    assert described["unparsed"] == []


def test_an_appearance_that_could_not_be_drawn_still_publishes_its_text(
    client: TestClient, repository: Repository
) -> None:
    """The `unclassified` rule, applied to prose: a gap is visible, never dropped."""
    divergent_corpus(repository)
    _describe(repository, "1".rjust(64, "0"), "A clear, colourless solution.")

    columns = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]
    described = next(c for c in columns if c["external_id"] == "1")["appearance"]

    assert described["source_text"] == "A clear, colourless solution."
    assert described["unparsed"] == ["shape", "colour"]


def test_a_label_with_no_appearance_collected_carries_none(
    client: TestClient, repository: Repository
) -> None:
    """The state the corpus is in today. Nothing renders where nothing was collected."""
    divergent_corpus(repository)

    columns = client.get(f"/substances/{SUBSTANCE_ID}").json()["products"]

    assert [c["appearance"] for c in columns] == [None, None]


def test_the_appearance_section_stays_out_of_the_scanned_scope(
    client: TestClient, repository: Repository
) -> None:
    """The constraint the whole comparison rests on, asserted at the seam the UI reads."""
    divergent_corpus(repository)
    _describe(repository, "1".rjust(64, "0"), "Orange/White capsule.")

    body = client.get(f"/substances/{SUBSTANCE_ID}").json()

    assert all("3" not in column["scanned"] for column in body["products"])
    assert all(cell["placement"] != "3" for row in body["rows"] for cell in row["cells"])


def test_the_concept_screen_carries_the_appearance_too(
    client: TestClient, repository: Repository
) -> None:
    """Both screens read `ProductColumn`, so neither can drift from the other."""
    divergent_corpus(repository)
    _describe(repository, "1".rjust(64, "0"), "Pale red oblong tablet, 8 x 4 mm.")

    columns = client.get(f"/substances/{SUBSTANCE_ID}/concepts/renal").json()["products"]
    described = next(c for c in columns if c["external_id"] == "1")["appearance"]

    assert (described["length_mm"], described["width_mm"]) == (8.0, 4.0)


def test_indications_are_grouped_by_what_the_labels_state(
    client: TestClient, repository: Repository
) -> None:
    """§4.1 describes the substance, so labels wording it alike become one description."""
    divergent_corpus(repository)
    # The API reads through its own connection, so these must be committed, not pending.
    with repository.transaction():
        for sha, text in (
            ("1".rjust(64, "0"), "- Treatment of hypertension. - Renal disease."),
            ("2".rjust(64, "0"), "- Treatment of hypertension.\n\n- Renal disease"),
        ):
            repository.save_section(
                sha, Section(code="4.1", heading="Therapeutic indications", text=text)
            )

    groups = client.get(f"/substances/{SUBSTANCE_ID}").json()["indications"]

    assert len(groups) == 1, "spacing and a full stop are not a difference of indication"
    assert [s["text"] for s in groups[0]["statements"]] == [
        "Treatment of hypertension.",
        "Renal disease.",
    ]
    assert len(groups[0]["manufacturers"]) == 2


def test_labels_stating_different_indications_are_not_merged(
    client: TestClient, repository: Repository
) -> None:
    """The rare real case: one holder's licence is narrower, and that must survive.

    Picking one wording to stand for the substance would hide exactly the finding that
    makes §4.1 worth showing at all.
    """
    divergent_corpus(repository)
    with repository.transaction():
        for sha, text in (
            ("1".rjust(64, "0"), "- Treatment of hypertension. - Paediatric use in children over 1 year."),
            ("2".rjust(64, "0"), "- Treatment of hypertension."),
        ):
            repository.save_section(
                sha, Section(code="4.1", heading="Therapeutic indications", text=text)
            )

    groups = client.get(f"/substances/{SUBSTANCE_ID}").json()["indications"]

    assert len(groups) == 2
    assert {len(g["statements"]) for g in groups} == {1, 2}


def _state_values(repository: Repository, stated: dict[str, tuple[str, str]]) -> None:
    """Give each label a §6.3 and a §6.4, committed so the API's connection sees them."""
    with repository.transaction():
        for sha, (shelf_life, storage) in stated.items():
            repository.save_section(
                sha, Section(code="6.3", heading="Shelf life", text=shelf_life)
            )
            repository.save_section(
                sha,
                Section(
                    code="6.4", heading="Special precautions for storage", text=storage
                ),
            )


def test_labels_wording_a_value_section_alike_become_one_group(
    client: TestClient, repository: Repository
) -> None:
    """Generics copy an SmPC verbatim, and two copies of one sentence are one statement."""
    divergent_corpus(repository)
    _state_values(
        repository,
        {
            "1".rjust(64, "0"): ("  24 months  ", "Do not store above 25 °C."),
            "2".rjust(64, "0"): ("24 months", "Do not store above 25 °C."),
        },
    )

    values = client.get(f"/substances/{SUBSTANCE_ID}").json()["values"]
    shelf_life = next(section for section in values if section["code"] == "6.3")

    assert len(shelf_life["groups"]) == 1, "surrounding whitespace is not a difference"
    assert len(shelf_life["groups"][0]["manufacturers"]) == 2


def test_labels_stating_different_values_are_never_merged(
    client: TestClient, repository: Repository
) -> None:
    """The finding itself: one label needs refrigerating and another needs nothing."""
    divergent_corpus(repository)
    _state_values(
        repository,
        {
            "1".rjust(64, "0"): ("24 months", "Store in a refrigerator (2-8°C)."),
            "2".rjust(64, "0"): (
                "3 years",
                "This medicinal product does not require any special storage conditions.",
            ),
        },
    )

    values = client.get(f"/substances/{SUBSTANCE_ID}").json()["values"]

    assert {section["code"] for section in values} == {"6.3", "6.4"}
    for section in values:
        assert len(section["groups"]) == 2
        assert all(len(group["manufacturers"]) == 1 for group in section["groups"])


def test_a_value_section_reports_how_many_labels_stated_it(
    client: TestClient, repository: Repository
) -> None:
    """Three labels stating a shelf life is not four labels having none."""
    divergent_corpus(repository)
    _state_values(repository, {"1".rjust(64, "0"): ("24 months", "Do not freeze.")})

    values = client.get(f"/substances/{SUBSTANCE_ID}").json()["values"]

    assert all(section["collected"] == 1 for section in values)
    assert all(section["total"] > section["collected"] for section in values)


def test_a_value_section_is_never_a_placement(
    client: TestClient, repository: Repository
) -> None:
    """The invariant the whole design rests on.

    `Placement` doubles as the vocabulary of comparable section codes, so a value section
    leaking into it would file a shelf life as though it were a safety concept — and would
    silently widen `scanned`, which is what every absence claim is measured against.
    """
    divergent_corpus(repository)
    _state_values(
        repository, {"1".rjust(64, "0"): ("24 months", "Store below 25 °C.")}
    )

    body = client.get(f"/substances/{SUBSTANCE_ID}").json()

    assert all(
        code not in column["scanned"] for column in body["products"] for code in ("6.3", "6.4")
    )
    assert all(
        cell["placement"] not in ("6.3", "6.4")
        for row in body["rows"]
        for cell in row["cells"]
    )


def test_the_roster_carries_the_names_on_a_box(
    client: TestClient, repository: Repository
) -> None:
    """A reader searches for what they were handed, which is rarely the substance name.

    The product and its holder are what a box says, so the roster carries both. Current
    revisions only — a name from a superseded revision is one nobody would recognise.
    """
    divergent_corpus(repository)

    roster = client.get("/substances").json()
    found = next(row for row in roster if row["id"] == SUBSTANCE_ID)

    assert found["labels"], "a collected substance must be searchable by its labels"
    assert len(found["labels"]) >= found["products"]


def test_indications_keep_the_nesting_the_label_wrote(
    client: TestClient, repository: Repository
) -> None:
    """Publishers indent §4.1, and flattening it overstates what a licence covers.

    Three labels in the real corpus mark a nested item three different ways — an em space
    then a bullet, a newline then a bullet, and the bare letter "o" — so the rule reads
    which kind of marker sits before a clause, never which character.
    """
    divergent_corpus(repository)
    with repository.transaction():
        for sha, text in (
            (
                "1".rjust(64, "0"),
                "- Treatment of renal disease:\n\no Incipient nephropathy,\n"
                " • Manifest nephropathy.\n- Treatment of hypertension.",
            ),
        ):
            repository.save_section(
                sha, Section(code="4.1", heading="Therapeutic indications", text=text)
            )

    groups = client.get(f"/substances/{SUBSTANCE_ID}").json()["indications"]
    depths = [(s["text"][:20], s["depth"]) for s in groups[0]["statements"]]

    assert [depth for _, depth in depths] == [0, 1, 1, 0], depths
