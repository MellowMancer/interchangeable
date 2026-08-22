"""FastAPI application. The seam between the pipeline and the UI.

The UI never opens SQLite: every shape it renders is a response model declared here, so
the domain can change without breaking a screen and vice versa.
"""

import re
from collections.abc import Iterator, Mapping, Sequence

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from bdheal.models import FailureClass, HealStatus
from bdheal.ports import HealStore
from bdheal.store import SqliteHealStore
from bdheal.store import connect as heal_connect

from ixq.adapters.config import load_collectors, load_sources, load_substances
from ixq.adapters.sqlite import SqliteRepository, connect
from ixq.domain import (
    Section,
    clauses,
    prepared,
    Document,
    Occurrence,
    Placement,
    Product,
    described_in,
    in_context,
    variant,
)
from ixq.domain.sections import INDICATIONS_CODE, VALUE_SECTIONS
from ixq.pipeline.diverge import PRECEDENCE, Comparison, ConceptRow, compare
from ixq.pipeline.ports import Repository, SubstanceCounts
from ixq.settings import bench_database_path, config_dir, database_path, heal_database_path

app = FastAPI(title="Interchangeable?")

def repository() -> Iterator[Repository]:
    """A repository per request, so no two requests share a connection.

    FastAPI runs sync endpoints in a threadpool, so a connection cached for the process
    is used from whichever worker picks up the request and raises. Opening per request
    costs well under a millisecond and confines each connection to one request — not to
    one thread: this dependency's setup and the endpoint body run in different workers,
    which is why `connect` passes `check_same_thread=False`.
    """
    conn = connect(database_path())
    try:
        yield SqliteRepository(conn)
    finally:
        conn.close()


def heal_store() -> Iterator[HealStore]:
    """The `bdheal` store per request, thread-confined for the same reason as `repository`."""
    conn = heal_connect(heal_database_path())
    try:
        yield SqliteHealStore(conn)
    finally:
        conn.close()


def bench_store() -> Iterator[HealStore]:
    """The benchmark's own store, thread-confined for the same reason as `repository`."""
    conn = heal_connect(bench_database_path())
    try:
        yield SqliteHealStore(conn)
    finally:
        conn.close()


class DivergencePreview(BaseModel):
    """One disagreement, named but not evidenced.

    Concept and placements only. The index screen previews every substance at once, so
    quotes are deliberately absent: they would multiply the payload by the corpus and are
    one click away on the comparison itself.
    """

    concept: str
    placements: list[str]


class SubstanceSummary(BaseModel):
    """A row of the landing list."""

    id: str
    name: str
    products: int
    concepts: int
    divergent: int
    divergences: list[DivergencePreview] = []
    labels: list[str] = []
    """Product names and MA holders on this substance's current labels.

    Carried so the roster can be searched by the thing a reader actually holds — a box
    saying Zentiva or Ramipril 5mg Tablets — rather than only by the active substance.
    Names, not counts: the search is over what is written on a label.
    """


class Evidence(BaseModel):
    """Why a cell says what it says. Verifiable against the source document."""

    quote: str
    section_code: str
    char_start: int
    char_end: int
    source_url: str


class Cell(BaseModel):
    """One manufacturer's position on one concept."""

    product_external_id: str
    placement: Placement
    evidence: Evidence | None = None


class Row(BaseModel):
    """One concept across every manufacturer."""

    concept: str
    diverges: bool
    cells: list[Cell]


class AppearanceView(BaseModel):
    """What one manufacturer says its product looks like, and what parsed out of it.

    `source_text` is §3 verbatim and is always present, so a description the parser could
    not read is still published — the same rule `unclassified` obeys for clauses. What a
    consumer draws from `shape` and `colours` is a drawing derived from that text and
    must be presented as one: no photograph of any product in this corpus exists.

    `length_mm` and `width_mm` are `None` on a label that states no dimensions. That is
    unknown, never a size to be borrowed from a product that does state one.
    """

    source_text: str
    shape: str | None = None
    colours: list[str] = []
    length_mm: float | None = None
    width_mm: float | None = None
    imprints: list[str] = []
    unparsed: list[str] = []
    """What could not be read, named. Empty is "fully parsed", not "nothing to say"."""


class ProductColumn(BaseModel):
    """A column of the matrix, with the context needed to read it."""

    external_id: str
    name: str
    variant: str | None = None
    """Strength and form, e.g. `2.5mg Capsules`. `None` when the name does not carry both.

    A manufacturer may authorise several strengths of one substance, each with its own
    label. Heading those columns by manufacturer alone makes them identical to read.
    """

    ma_holder: str | None = None
    holder_id: int | None = None
    """The source's own id for the holder. Two spellings of one company share one id."""

    revised: str | None = None
    listing_updated: str | None = None
    """When the source last touched its record — not when the publisher revised the text.

    Both are shown because they disagree by years, and a reader told only one of them
    cannot know which question the staleness they are looking at answers.
    """

    atc_code: str | None = None
    """Two products with different ATC codes are not the same medicine, and the comparison
    should be able to say so rather than let the reader assume otherwise."""

    legal_status: str | None = None
    ma_number: str | None = None
    discontinued: bool | None = None
    """`None` means the label was fetched before this was collected — not that it is live."""

    source_url: str | None = None
    scanned: list[str] = []
    """Sections read for *this* label. An absence in this column means absent from these.

    Per column rather than per matrix: a product whose §4.5 came back empty was never
    scanned for 4.5, and saying otherwise claims a scope that does not exist for it.
    """

    appearance: AppearanceView | None = None
    """§3, when the label has one stored. Product metadata, never part of the comparison.

    Carried on the column because it is per product and it is small — a line of prose and
    a handful of parsed fields, once per manufacturer. What must not be attached here is
    anything that scales with the *rows*: that is the regression `counts_by_substance`
    exists to undo, and this does not do it.

    Deliberately absent from `scanned`, which is the scope every absence claim is measured
    against. §3 is not somewhere a safety concept could have been found.
    """


class ClauseCoverage(BaseModel):
    """How many stored clauses the lexicon matched, and how many it did not.

    Two counts, never a ratio: a percentage would read as a claim about the lexicon's
    recall in general, which one substance cannot support.
    """

    classified: int
    unclassified: int


class IndicationStatement(BaseModel):
    """One indication, and how deeply the label itself nested it.

    Depth is read from the marker the publisher wrote, never inferred from the sentence.
    §4.1 is routinely two levels — a heading like "Treatment of renal disease:" followed
    by the nephropathies it covers — and flattening them states that a label lists nine
    equal indications when it lists five, two of which are qualified.
    """

    text: str
    depth: int


class IndicationGroup(BaseModel):
    """One §4.1 wording, and the manufacturers whose labels carry it.

    A list rather than a single description because the labels are not guaranteed to
    agree, and picking one silently would present one holder's licence as the substance's.
    Across the substances checked they agree in wording that normalises to the same text
    six times in seven, so this is usually one group — and when it is not, the split is
    the point.
    """

    statements: list[IndicationStatement]
    manufacturers: list[str]


class ValueGroup(BaseModel):
    """One wording of a value section, and the manufacturers whose labels carry it."""

    text: str
    manufacturers: list[str]


class ValueSection(BaseModel):
    """One value section across a substance's labels, grouped by the exact words used.

    Byte-identical grouping, and no interpretation on top of it. "Do not store above 25°C"
    and "Store below 25°C" state the same requirement, so a system that called that a
    divergence would be asserting something false about a medicine — while "24 months"
    beside "3 years" is a real difference any reader can see unaided. So every distinct
    text is published verbatim and the reader judges it.

    What this reports is therefore how many ways these labels word a section, never that
    they require different things. `collected` against `total` is carried for the same
    reason absence is everywhere else here: a section only three labels state is not a
    section the other four are silent about.
    """

    code: str
    heading: str
    groups: list[ValueGroup]
    collected: int
    total: int


class ContextWindow(BaseModel):
    """The stored section text around one quote, with the quote's span inside it.

    A window rather than the whole section, and never on the matrix. `GET
    /substances/{id}` carries every cell of every row, so section bodies there would be
    read once per concept per product on every navigation — the regression
    `counts_by_substance` exists to undo. One concept across a substance, or one label's
    concepts, are both bounded reads.

    Offsets are relative to `text`, so the screen highlights by slicing. Re-finding the
    quote by searching the window instead marks the wrong instance wherever a clause
    repeats within a section, and the highlight then sits on a sentence the cell does not
    quote. The absolute offsets stay on `Evidence`, and `char_start - quote_start` is
    where this window begins in the section.

    `truncated_start` and `truncated_end` say which ends were cut. Unmarked, a window
    that stops mid-sentence reads as a section that ends there — an invitation to
    conclude the label says nothing further, which is the one claim this project refuses
    to make.
    """

    text: str
    quote_start: int
    quote_end: int
    truncated_start: bool
    truncated_end: bool
    section_length: int


class ConceptCell(Cell):
    """A matrix cell with the label text its quote was sliced from.

    `context` is `None` in exactly the cases `evidence` is. A cell with no match has no
    text to surround, and an empty window rendered in the same frame as a real one would
    make an absence look like something that was read and found wanting. What an absence
    is defensible against is `scanned` on the column, never a window.
    """

    context: ContextWindow | None = None


class ConceptDetail(BaseModel):
    """One concept across every manufacturer, each quote shown where it was found.

    Its own endpoint rather than a field on `Matrix`: the matrix answers for every
    concept at once, so section text attached there is paid for the whole grid to render
    the one cell a reader opened.

    Self-contained, so the screen makes one request. The columns travel with the cells
    because `absent` cannot be read without the sections scanned for that column, and
    fetching the matrix alongside for them would give back everything the split saved.
    """

    substance_id: str
    substance_name: str
    concept: str
    diverges: bool
    products: list[ProductColumn]
    cells: list[ConceptCell]


class ProductConcept(BaseModel):
    """Where one concept sits in one label, with the sentence that put it there.

    The quote travels with the text around it, because on its own a clause is often not a
    statement: "They will, however, decrease the effects of anticholinesterases" says
    nothing without the sentence it answers. The concept screen made the same judgement.
    """

    concept: str
    placement: Placement
    evidence: Evidence | None = None
    context: ContextWindow | None = None


class ValueStatement(BaseModel):
    """One value section as a single label states it."""

    code: str
    heading: str
    text: str


class ProductDetail(BaseModel):
    """One label, addressable on its own.

    The project's claim is that every statement can be checked against its source, and
    until this existed a label had no URL: a product was only ever a column inside a
    comparison, so a finding could be read but not cited.

    Self-contained, like `ConceptDetail`: the siblings travel with it because "what else
    is this substance dispensed as" is the question a reader arrives with, and fetching
    the substance alongside to answer it would give back what the split saved.
    """

    substance_id: str
    substance_name: str
    product: ProductColumn
    siblings: list[ProductColumn]
    indications: list[IndicationStatement]
    concepts: list[ProductConcept]
    values: list[ValueStatement]


class Matrix(BaseModel):
    """The comparison for one substance.

    Each column carries the sections read for it — required reading, not metadata:
    `absent` means absent from those sections, and a reader cannot judge an absence
    without knowing what was looked at.
    """

    substance_id: str
    substance_name: str
    """Carried here so a screen showing one concept needs only this response.

    The roster endpoint recomputes every substance's comparison to produce its counts, so
    fetching it for a display name costs the whole roster to render one back-link.
    """

    products: list[ProductColumn]
    rows: list[Row]
    indications: list[IndicationGroup]
    """What the labels state this substance is for, grouped by wording.

    Shown, never diffed. §4.1 is a description of the substance rather than a place a
    safety concept is filed, so a difference here is reported as different wording and
    never as a divergence — the comparison's vocabulary does not reach it.
    """

    values: list[ValueSection]
    """§6.3 and §6.4, grouped by wording rather than placed.

    A shelf life is a value a label states once, not a place a concept can be filed, so it
    is never given a `Placement` and never enters the divergence matrix. Reported beside
    it instead, because two labels for the same substance disagreeing on whether it needs
    refrigerating is an interchangeability finding in its own right.
    """

    clauses: ClauseCoverage
    """The recall gap, carried with the comparison it belongs to.

    Two counts rather than a ratio: a percentage would read as a claim about the lexicon's
    recall in general, which one substance's corpus cannot support.
    """


CONTEXT_RADIUS = 200
"""Characters of section text shown either side of a quote.

Enough to carry the sentence a clause sits between and the one before it — which is what
makes "They will, however, decrease the effects of…" a statement — and no more. At twice
this the window stopped being context and became the section, and the quote it exists to
frame was the smaller half of what a reader had to read.
"""


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/substances", response_model=list[SubstanceSummary])
def substances(repo: Repository = Depends(repository)) -> list[SubstanceSummary]:
    """The roster, with how much of it has actually been collected.

    Counted in storage rather than by building each comparison. Every screen reads this,
    so the previous shape — one full `compare()` per substance, reading all the section
    text and quotes to return three integers — was paid on every navigation.
    """
    counted = repo.counts_by_substance()
    diverging = repo.divergences_by_substance()
    named = repo.labels_by_substance()
    empty = SubstanceCounts(products=0, concepts=0, divergent=0)
    return [
        SubstanceSummary(
            id=substance.id,
            name=substance.name,
            products=(counts := counted.get(substance.id, empty)).products,
            concepts=counts.concepts,
            divergent=counts.divergent,
            divergences=[
                DivergencePreview(concept=d.concept, placements=list(d.placements))
                for d in diverging.get(substance.id, ())
            ],
            labels=list(named.get(substance.id, ())),
        )
        for substance in load_substances(config_dir() / "substances.yaml")
    ]


@app.get("/substances/{substance_id}", response_model=Matrix)
def matrix(substance_id: str, repo: Repository = Depends(repository)) -> Matrix:
    """The comparison, with the evidence for every cell that has any."""
    result = compare(substance_id, repo)
    if not result.products:
        raise HTTPException(404, f"no labels stored for {substance_id!r}")

    by_product = {d.product_external_id: d for d in result.documents}

    counted = repo.clause_counts(substance_id)
    return Matrix(
        substance_id=result.substance_id,
        substance_name=_substance_name(substance_id),
        products=_columns(result, repo.appearances_for_substance(substance_id)),
        indications=_indications(result, repo.indications_for_substance(substance_id)),
        values=_value_sections(result, repo.value_sections_for_substance(substance_id)),
        clauses=ClauseCoverage(
            classified=counted.classified, unclassified=counted.unclassified
        ),
        rows=[
            Row(
                concept=row.concept,
                diverges=row.diverges,
                cells=[
                    Cell(
                        product_external_id=p.external_id,
                        placement=row.placements[p.external_id],
                        evidence=_evidence(
                            row.evidence.get(p.external_id),
                            by_product.get(p.external_id),
                        ),
                    )
                    for p in result.products
                ],
            )
            for row in sorted(result.rows, key=lambda r: (not r.diverges, r.concept))
        ],
    )


def _column(
    product: Product,
    document: Document | None,
    scanned: Sequence[str],
    described: str | None,
) -> ProductColumn:
    """One column of the matrix: the product, and what the current label says about it.

    `document` is optional because a product can be collected before its label is fetched.
    Every field it supplies is then None — the column still appears, because a product
    with no label is a gap the reader should see rather than a row to hide.
    """
    return ProductColumn(
        external_id=product.external_id,
        name=product.name,
        variant=variant(product.name),
        ma_holder=product.ma_holder,
        holder_id=document.holder_id if document else None,
        revised=document.last_updated if document else None,
        listing_updated=document.listing_updated if document else None,
        atc_code=_atc(document.atc_code) if document else None,
        legal_status=document.legal_status if document else None,
        ma_number=document.ma_number if document else None,
        discontinued=document.discontinued if document else None,
        source_url=document.source_url if document else None,
        scanned=list(scanned),
        appearance=_appearance(described),
    )


ATC_CODE = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
"""The WHO shape: anatomical letter, two digits, two therapeutic letters, two digits.

Checked because the collector does not always return one. Across the metronidazole labels
one product's `atc_code` is "Morningside Healthcare Ltd See contact details" — a company
block read out of the wrong element. Served as a code it becomes a third distinct value in
`Classification`, which then warns that these products may not be alternatives to one
another. That is a clinical-sounding claim produced by a parsing error.
"""


def _atc(code: str | None) -> str | None:
    """An ATC code, or None when what was collected is not one."""
    return code if code and ATC_CODE.fullmatch(code.strip()) else None


def _evidence(occurrence: Occurrence | None, document: Document | None) -> Evidence | None:
    """The quote behind one cell.

    Both arguments come from the caller's own loop over `(product, concept)`. Nothing is
    looked up again: `compare` already paired every occurrence with the document it
    belongs to, and re-deriving that pairing here is how a placement and its quote came
    from two different revisions of the same label.
    """
    if occurrence is None or document is None:
        return None
    return Evidence(
        quote=occurrence.quote,
        section_code=occurrence.section_code,
        char_start=occurrence.char_start,
        char_end=occurrence.char_end,
        source_url=document.source_url,
    )


def _columns(result: Comparison, described: Mapping[str, str]) -> list[ProductColumn]:
    """The columns of a comparison, each carrying the sections scanned for its own label.

    `described` is keyed by document sha, not by product, so the appearance shown is the
    one belonging to the revision the comparison is built from. Keyed by product it could
    survive a revision the rest of the column has moved past, and the reader would be
    looking at a picture of a product the current label no longer describes.
    """
    by_product = {d.product_external_id: d for d in result.documents}

    def column(product: Product) -> ProductColumn:
        document = by_product.get(product.external_id)
        return _column(
            product,
            document,
            result.scanned.get(product.external_id, ()),
            described.get(document.sha256) if document else None,
        )

    return [column(product) for product in result.products]


def _binding(placement: Placement) -> int:
    """How binding a placement is, with absence ranked below every section."""
    return PRECEDENCE.index(placement) if placement in PRECEDENCE else len(PRECEDENCE)


#: Every character a publisher uses to open a list item, of either level.
_MARKERS = "•·▪▫◦●○‣⁃∙*-–—"


def _marker(text: str, start: int) -> str | None:
    """The list marker immediately before the clause at `start`, if it has one."""
    before = text[max(0, start - 8) : start].rstrip()
    if not before:
        return None
    if before[-1] in _MARKERS:
        return before[-1]
    # A lone "o" is a bullet; the same letter ending a word is not.
    standalone = len(before) == 1 or before[-2].isspace()
    return "o" if before[-1] in "oO" and standalone else None


def _nesting(markers: Sequence[str | None]) -> list[int]:
    """How deeply the label nested each clause, read from the markers it wrote.

    Depth is **relative to the document**, never absolute. Publishers are internally
    consistent and disagree with each other: across four ramipril labels the outer level
    is written "-", "-", "-" and "▪", and the inner one an em space then "•", a newline
    then "•", a bare "o", and an em space then "o". A rule that named particular
    characters as nested read one label's top level as its second.

    So whatever marker opens the section is its top level, and anything else is one deeper.
    A section with a single marker throughout is flat, which is what it looks like.
    """
    top = next((mark for mark in markers if mark is not None), None)
    return [0 if mark is None or mark == top else 1 for mark in markers]


def _statements(text: str | None) -> list[IndicationStatement]:
    """§4.1 split into its statements, each carrying the nesting the label wrote.

    Shared by the matrix and a product's own page, so one label's indications cannot read
    differently depending on which screen reached them.
    """
    if not text:
        return []
    section = Section(code=INDICATIONS_CODE, heading="Therapeutic indications", text=text)
    found = clauses(section)
    depths = _nesting([_marker(text, clause.start) for clause in found])
    return [
        IndicationStatement(text=clause.text, depth=depth)
        for clause, depth in zip(found, depths, strict=True)
    ]


def _indications(result: Comparison, stated: Mapping[str, str]) -> list[IndicationGroup]:
    """§4.1 across a substance's current labels, grouped by what they actually say.

    Grouped on `prepared()` — the same normalisation concept matching uses — reduced
    further to its words. Two ramipril labels state the identical indications and differ
    by a single stray full stop left where a cross-reference was removed; grouping on
    punctuation would split them and imply a disagreement that is not there.

    Comparing words, not bytes, is the right granularity for a description: the claim made
    is that these labels state the same indications, not that they are byte-identical. The
    statements shown are one member's verbatim text, never merged or rewritten.
    """
    by_product = {d.product_external_id: d for d in result.documents}
    groups: dict[str, tuple[list[str], list[str]]] = {}

    for product in result.products:
        document = by_product.get(product.external_id)
        text = stated.get(document.sha256) if document else None
        if not text:
            continue
        statements = _statements(text)
        words = prepared(" ".join(s.text for s in statements))
        # Punctuation first, whitespace after: dropping a full stop leaves the space it
        # sat between, and collapsing before the strip leaves two where there was one.
        key = " ".join("".join(c if c.isalnum() else " " for c in words).split())
        held = groups.setdefault(key, (statements, []))
        # A holder with several products contributes once: "Sandoz, Sandoz" reads as two
        # manufacturers agreeing when it is one label listed twice.
        name = product.ma_holder or product.external_id
        if name not in held[1]:
            held[1].append(name)

    return [
        IndicationGroup(statements=statements, manufacturers=manufacturers)
        for statements, manufacturers in groups.values()
    ]


def _value_sections(
    result: Comparison, stated: Mapping[str, Mapping[str, str]]
) -> list[ValueSection]:
    """§6.3 and §6.4 across a substance's current labels, grouped by exact wording.

    Byte-exact, unlike `_indications`, and the difference is deliberate. An indication set
    is a claim about meaning, so normalising punctuation before comparing is right there.
    A shelf life is a stated value, and normalising it would mean deciding that "24 months"
    and "2 years" are the same — a units judgement this makes no attempt at, because the
    confounds are real: values are given in months or years, some labels state one figure
    per pack type, and §6.4 sometimes defers back to §6.3.

    Leading and trailing whitespace is stripped, which cannot merge two different
    statements, and nothing else is touched.
    """
    by_product = {d.product_external_id: d for d in result.documents}
    sections: list[ValueSection] = []

    for spec in VALUE_SECTIONS:
        groups: dict[str, list[str]] = {}
        for product in result.products:
            document = by_product.get(product.external_id)
            text = stated.get(document.sha256, {}).get(spec.code) if document else None
            if not text or not text.strip():
                continue
            # Deduped like `_indications`: a holder shipping two strengths with identical
            # text is one manufacturer saying one thing, not two agreeing.
            named = groups.setdefault(text.strip(), [])
            holder = product.ma_holder or product.external_id
            if holder not in named:
                named.append(holder)

        if not groups:
            continue
        sections.append(
            ValueSection(
                code=spec.code,
                heading=spec.heading,
                groups=[
                    ValueGroup(text=text, manufacturers=manufacturers)
                    for text, manufacturers in groups.items()
                ],
                collected=sum(len(m) for m in groups.values()),
                total=len(result.products),
            )
        )
    return sections


def _appearance(section_text: str | None) -> AppearanceView | None:
    """§3 parsed for display, or None when no §3 is stored for this label.

    None is "nothing was collected", which is not "described but not drawn" — a label
    nobody has fetched a description for must render as no claim at all, never as a gap
    in the manufacturer's own labelling.
    """
    if section_text is None:
        return None
    found = described_in(section_text)
    return AppearanceView(
        source_text=found.source_text,
        shape=found.shape.value if found.shape else None,
        colours=list(found.colours),
        length_mm=found.length_mm,
        width_mm=found.width_mm,
        imprints=list(found.imprints),
        unparsed=list(found.unparsed),
    )


def _substance_name(substance_id: str) -> str:
    """The display name from the configured roster, or the id when it names no such one."""
    names = {s.id: s.name for s in load_substances(config_dir() / "substances.yaml")}
    return names.get(substance_id, substance_id)


@app.get("/products/{product_external_id}", response_model=ProductDetail)
def product(
    product_external_id: str, repo: Repository = Depends(repository)
) -> ProductDetail:
    """One label: what it is, where it files each concept, and what it is stored with.

    Built from the same `compare` the matrix uses rather than from a query of its own, so
    a placement here and the same placement in the comparison cannot disagree — and the
    evidence stays paired with the revision it was taken from.
    """
    substance_id = repo.substance_of(product_external_id)
    if substance_id is None:
        raise HTTPException(404, f"no product {product_external_id!r} is stored")

    result = compare(substance_id, repo)
    columns = _columns(result, repo.appearances_for_substance(substance_id))
    mine = next((c for c in columns if c.external_id == product_external_id), None)
    if mine is None:
        raise HTTPException(404, f"no label stored for {product_external_id!r}")

    document = next(
        (d for d in result.documents if d.product_external_id == product_external_id), None
    )
    stated = repo.indications_for_substance(substance_id)
    values = repo.value_sections_for_substance(substance_id)
    held = values.get(document.sha256, {}) if document else {}

    return ProductDetail(
        substance_id=substance_id,
        substance_name=_substance_name(substance_id),
        product=mine,
        siblings=[c for c in columns if c.external_id != product_external_id],
        indications=_statements(stated.get(document.sha256)) if document else [],
        concepts=sorted(
            (
                ProductConcept(
                    concept=row.concept,
                    placement=row.placements[product_external_id],
                    evidence=_evidence(row.evidence.get(product_external_id), document),
                    context=_context(row.evidence.get(product_external_id), repo),
                )
                for row in result.rows
            ),
            # Absence last: `PRECEDENCE` ranks the sections a concept can be filed in,
            # and absence is not one of them.
            key=lambda c: (_binding(c.placement), c.concept),
        ),
        values=[
            ValueStatement(code=spec.code, heading=spec.heading, text=held[spec.code].strip())
            for spec in VALUE_SECTIONS
            if held.get(spec.code, "").strip()
        ],
    )


@app.get("/substances/{substance_id}/concepts/{concept}", response_model=ConceptDetail)
def concept(
    substance_id: str, concept: str, repo: Repository = Depends(repository)
) -> ConceptDetail:
    """One concept's row, each quote surrounded by the stored text it was sliced from.

    Section text is read here and nowhere else. Reading it in the matrix instead would
    attach a label body to every cell of every row — the shape `counts_by_substance` was
    introduced to undo, where one screen paid for the whole corpus to show one thing.
    Bounded here by the products of one substance, so the cost tracks what is on screen.

    A concept nothing matched is a 404 against *the sections scanned*, never a statement
    that the labels omit it.
    """
    result = compare(substance_id, repo)
    if not result.products:
        raise HTTPException(404, f"no labels stored for {substance_id!r}")

    row = next((r for r in result.rows if r.concept == concept), None)
    if row is None:
        raise HTTPException(
            404, f"{concept!r} was not matched in any section scanned for {substance_id!r}"
        )

    by_product = {d.product_external_id: d for d in result.documents}
    return ConceptDetail(
        substance_id=result.substance_id,
        substance_name=_substance_name(substance_id),
        concept=row.concept,
        diverges=row.diverges,
        products=_columns(result, repo.appearances_for_substance(substance_id)),
        cells=[
            _concept_cell(row, p.external_id, by_product.get(p.external_id), repo)
            for p in result.products
        ],
    )


def _concept_cell(
    row: ConceptRow, external_id: str, document: Document | None, repo: Repository
) -> ConceptCell:
    """One manufacturer's cell, with the surroundings of the quote that set it.

    The window is built only where the evidence is, so the two can never disagree about
    whether this cell has a source: a window beside a missing quote would dress an
    absence up as something read and rejected.
    """
    occurrence = row.evidence.get(external_id)
    evidence = _evidence(occurrence, document)
    return ConceptCell(
        product_external_id=external_id,
        placement=row.placements[external_id],
        evidence=evidence,
        context=_context(occurrence, repo) if evidence else None,
    )


def _context(occurrence: Occurrence | None, repo: Repository) -> ContextWindow | None:
    """The stored section text around one quote, read one section at a time.

    Fetched by the occurrence's own document and code rather than by re-deriving them:
    those are the coordinates the quote was sliced at, so the window cannot come from a
    section other than the one the offsets address.
    """
    if occurrence is None:
        return None
    text = repo.section_text(occurrence.document_sha256, occurrence.section_code)
    if text is None:
        return None
    found = in_context(text, occurrence, CONTEXT_RADIUS)
    return ContextWindow(
        text=found.text,
        quote_start=found.quote_start,
        quote_end=found.quote_end,
        truncated_start=found.truncated_start,
        truncated_end=found.truncated_end,
        section_length=found.section_length,
    )


class Heal(BaseModel):
    """One trip through the Bright Data heal gate, as the reliability screen shows it."""

    status: HealStatus
    created_at: str
    promoted: bool
    failure_class: FailureClass | None = None
    attempts: int
    error: str | None = None


class CollectorHealth(BaseModel):
    """A collector's configuration and what `bdheal` remembers about it.

    `baseline_captured_at` is `None` before a collector's first run — that is "not yet
    observed", not "healthy". The screen must not render the two the same way.
    """

    id: str
    kind: str
    source: str
    baseline_captured_at: str | None = None
    baseline_row_count: int | None = None
    heals: list[Heal] = []


@app.get("/collectors", response_model=list[CollectorHealth])
def collectors(store: HealStore = Depends(heal_store)) -> list[CollectorHealth]:
    """What is configured to collect, and how each one has been holding up."""
    sources = {s.id: s.name for s in load_sources(config_dir() / "sources.yaml")}
    health = []
    for collector in load_collectors(config_dir() / "collectors.yaml"):
        baseline = store.baseline(collector.id)
        health.append(
            CollectorHealth(
                id=collector.id,
                kind=collector.kind.value,
                source=sources.get(collector.source_id, collector.source_id),
                baseline_captured_at=baseline.captured_at.isoformat() if baseline else None,
                baseline_row_count=baseline.row_count if baseline else None,
                heals=[
                    Heal(
                        status=event.status,
                        created_at=event.created_at.isoformat(),
                        promoted=event.promoted,
                        failure_class=event.failure_class,
                        attempts=event.attempts,
                        error=event.error,
                    )
                    for event in reversed(store.heal_events(collector.id))
                ],
            )
        )
    return health


class BenchCase(BaseModel):
    """One mutation case's outcome on the controlled fixture site.

    Every field is reported, including the ones that record a failure. A case the
    detector missed, or caught but could not repair, is the coverage gap the benchmark
    exists to publish — filtering to the successes would make this endpoint a claim
    rather than a measurement.

    `caught_by` is `None` when nothing fired. `healed` false with `field_accuracy` and
    `non_regression_passed` both `None` means the repair was never scored, which is not
    the same as scoring zero.
    """

    case_id: str
    mutation: str
    expected_signals: list[str]
    caught_by: str | None = None
    fired_kinds: list[str] = []
    healed: bool
    field_accuracy: float | None = None
    non_regression_passed: bool | None = None
    attempts: int
    elapsed_s: float
    completed_at: str | None = None


class BenchRun(BaseModel):
    """One benchmark run, with every case it recorded."""

    run_id: str
    cases: list[BenchCase]


@app.get("/benchmark", response_model=list[BenchRun])
def benchmark(store: HealStore = Depends(bench_store)) -> list[BenchRun]:
    """How the heal loop scored against a site broken on cue.

    `medicines.org.uk` cannot be mutated to order, so the repair loop is measured against
    a fixture site instead. Read from `bench.db`, never from `bdheal.db`: a rehearsal and
    a production incident must not arrive through the same route.

    Every run is returned, oldest first, rather than one named here. Naming a run would
    let this endpoint publish the flattering half of a benchmark whose other half is
    sitting in the same file.
    """
    return [
        BenchRun(
            run_id=run_id,
            cases=[
                BenchCase(
                    case_id=case.case_id,
                    mutation=case.mutation.value,
                    expected_signals=sorted(s.value for s in case.expected_signals),
                    caught_by=case.caught_by.value if case.caught_by else None,
                    fired_kinds=sorted(s.value for s in case.fired_kinds),
                    healed=case.healed,
                    field_accuracy=case.field_accuracy,
                    non_regression_passed=case.non_regression_passed,
                    attempts=case.attempts,
                    elapsed_s=case.elapsed_s,
                    completed_at=case.completed_at.isoformat() if case.completed_at else None,
                )
                for case in store.bench_cases(run_id)
            ],
        )
        for run_id in store.bench_runs()
    ]
