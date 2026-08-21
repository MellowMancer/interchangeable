# What the site does not show

Gaps in the **presentation layer**, recorded 2026-08-21 against the routes then live.
`docs/EMC_FIELDS.md` is the authority on what can be *collected*; this is the authority on
what is collected and never reaches a reader.

Every claim below was checked against the code, not inferred. Where a field or function is
named, it exists and is unused — those are the cheapest starting points, because the data
side is already done.

## What exists today

Five routes: `/` (roster, search, one hero finding), `/substances/[id]` (the matrix,
indications, revision timeline, recall gap, provenance), `/substances/[id]/concepts/
[concept]` (evidence per manufacturer), `/collectors` (reliability and benchmark), and
`/reading` (the vocabulary).

Everything about a finding is scoped to **one substance at a time**. That is the shape of
the gaps below: the corpus holds entities the UI has no page for.

**Not a gap — deliberately good.** The honesty layer is covered in four independent places:
`SectionCoverage` chips draw uncollected sections dashed, `Provenance` names the sections
read, each absent cell says "not the same as the label being silent", and `RecallGap`
publishes two counts rather than a flattering percentage. Do not simplify these.

---

## 1. The manufacturer has no page

A column *is* a manufacturer, and there is no way to click one.

- `ProductColumn.holder_id` is served by the API and read by **nothing** — typed at
  `web/src/lib/api.ts:52`, zero call sites. Canonical holder identity already exists,
  because a company id cannot be misspelt the way `ma_holder` free text can.
- `manufacturer()` (`api.ts:208`) is only ever called inside one substance's response.

**What it would say.** Every product a holder makes, across every substance — and then the
finding that needs more than one substance to exist: *is this manufacturer systematically
stricter or looser than its competitors?* "Files in §4.3 where the others file in §4.4, in
7 of 9 shared concepts" is a claim that requires no new collection and that nothing else
publishes.

**Why it is first.** The data side is finished. This is a route, a query grouping by
`holder_id`, and a page.

## 2. The site does not answer the question people arrive with

Nobody arrives wanting an N-column matrix. They arrive with *"my pharmacy switched my
brand — what is different?"*

Every view is all-columns-at-once: `DivergenceTable`, `PlacementSpectrum`, and the concept
page's stacked list. Nothing compares exactly two products.

- `groupByWording` (`web/src/lib/finding.ts:174`) groups products by shared wording and is
  **exported, never rendered** — dead code pointing straight at this feature.
- `identicalWording` (`finding.ts:125`) already annotates "identical wording to X, Y", so
  the byte-comparison half is written and working.

**What it would say.** Two products, only what differs, in the labels' own words —
including where they are byte-identical, which is itself the answer most of the time and
is reassuring rather than dull.

## 3. A label is not addressable

There is no `/products/[id]`. A product exists only as a column inside a comparison.

This is not merely navigation. The project's whole claim is that every statement can be
checked against its source, and **there is currently no URL for a single label**. A finding
cannot be cited.

Everything needed is stored: the verbatim sections, `ma_number` (the regulator's id, unlike
the source's surrogate `external_id`), `atc_code`, `legal_status`, `holder_id`,
`listing_updated`, the §3 appearance, and every occurrence with its character offsets.

**Also the home for two fields served and rendered nowhere:** `ProductColumn.legal_status`
and `ProductColumn.listing_updated` (`api.ts:56,58`). The second matters — it answers "when
did the source last touch this record", which is a different question from `revised`, and
the UI currently shows only one of the two.

## 5. Findings are buried one substance deep

Numbered 5 to match the discussion it came from; item 4 was revision history, deferred
separately because it needs time to pass before it shows anything.

- The home page features exactly **one** finding, chosen by `featuredSubstance`
  (`finding.ts:41`).
- The concept route is nested under a substance, and `ConceptDetail` is scoped to a single
  `substance_id` (`api/src/ixq/api/main.py:308`). Home search matches concept names but
  returns *substances*.

**What it would say.** Two things:

1. A ranked feed of the strongest disagreements **corpus-wide** — the right front door once
   the roster is 50 substances rather than 8.
2. `/concepts/[concept]` unscoped: does `pregnancy` diverge for every substance or only for
   ramipril? Which concepts are *systematically* contested?

The second is a meta-finding that gets stronger as the corpus grows, and it cannot be seen
from any page that exists.

---

## Deferred, and why

**Revision history.** The schema keeps every revision on purpose — `documents` has no
unique constraint on `(source_id, source_url)`, and the comment in `schema.sql` says that
history "is the point of the project". Nothing renders it. `RevisionTimeline` compares
staleness *across manufacturers*, not change *within* one label.

"In July this manufacturer moved sacubitril from a warning to a contraindication" is the
highest-ceiling output this design can produce. It is deferred only because it needs the
same products fetched again over time before there is anything to draw — which is a reason
to start collecting now, not a reason to postpone the collection.

## Smaller, and real

- **The excipient question as a filter, not a cell.** §6.1 is stored. "Which of these is
  lactose-free?" is a genuine question with a genuine answer and no page. It filters
  products; it is not a row of the matrix.
- **No corpus-wide numbers.** Recall is per-substance only. Nothing states overall coverage
  or that roughly five of the SmPC's twenty sections are read.
- **Filtering exists on one screen.** Home search only. No filter by placement,
  manufacturer, ATC code, or discontinued status anywhere.
- **The MCP server is invisible.** `ixq-mcp` (`api/pyproject.toml:33`) exposes the
  comparison to any MCP client and is mentioned only in the README. It needs no language
  model of ours — see below — so the cost of surfacing it is a paragraph.

## A note on the MCP server, since it is easy to misread

`api/src/ixq/api/mcp_server.py` imports `mcp`, `ixq.adapters.sqlite`, `ixq.domain` and
`ixq.pipeline.diverge`. **No model, no API key, no inference.** It is a protocol server
over the same deterministic pipeline the website reads; the language model lives in
whatever client connects to it, and its operator pays for it.

Surfacing it does not compromise "no language model sits in the data path", because the
data path is unchanged — the model is a *consumer* of the output, on the far side of the
seam.
