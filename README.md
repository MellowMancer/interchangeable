# rf-pre

Early-signal intelligence for municipal capital projects.

Public agencies decide to build things long before they publish a solicitation.
That intent is visible in council agendas, capital facilities plans, and staff
reports — sometimes years ahead. This project reads those public documents and
turns them into scored, sourced signals.

**Scope:** Washington State, water and wastewater.

## Signal ladder

| Tier | Signal |
|---|---|
| 1 | Casual mention |
| 2 | Feasibility study or comprehensive plan commissioned |
| 3 | Budgeted line item in a capital plan |
| 4 | Design or construction contract awarded |

Every signal carries a verbatim quote, a link to the source document, a page
reference, and the meeting date. Provenance is a requirement, not a feature.

## Approach

Agency documents are public by law but scattered across vendor platforms with
inconsistent structure and no common interface. The collection layer is built
to notice when a source changes shape and repair itself, so the pipeline keeps
running without hand-maintenance per agency.

## Status

Early. Corpus selection and pipeline validation in progress. Nothing here is
production-ready.
