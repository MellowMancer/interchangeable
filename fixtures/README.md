# bdheal benchmark fixtures

The pages the self-healing benchmark runs against. Real sites do not redesign themselves on
cue, so the benchmark hosts a site it fully controls and breaks that instead.

## The data is synthetic — read this first

Every record in `data.json` is invented. The reference codes, component names and dates
describe nothing that exists, and every generated page carries a visible banner saying so.
Do not repurpose these pages to represent anything real.

## How it works

```
data.json  ──►  render.py  ──►  site/index.html          the base ("old") layout
                     │
                     └────────►  site/<mutation>.html    one page per bdheal mutation class
                     └────────►  site/manifest.json      pages, expected signals, goldens
```

One dataset is the single source of truth. The base page is rendered from it; each mutated
page is that same base page put through one of `bdheal`'s own generators in
`bench/mutate.py`. **The golden records are derived from the dataset, never transcribed** —
so a page and the records it is scored against cannot drift apart.

`site/` is generated but committed on purpose: a `git diff` of it between two renders is the
reviewable record of exactly what a mutation changed.

```bash
uv run --package bdheal python fixtures/render.py   # regenerate
fixtures/deploy.sh                                  # render + publish to gh-pages
```

## What each mutation is expected to do

Verified against the rendered site rather than asserted:

| Mutation | Skeleton hash | Extracted values | Expected to be caught by |
|---|---|---|---|
| `class_rename` | moves | unchanged | `skeleton` |
| `table_to_div` | moves | unchanged | `skeleton` |
| `column_reorder` | moves | unchanged | `skeleton` |
| `field_split_merge` | moves | unchanged | `skeleton` |
| `wrapper_nesting` | moves | unchanged | `skeleton` |
| `pagination` | moves | unchanged | `skeleton` |
| `url_pattern` | unchanged | `href` changes | `schema`, `null_rate` |
| `date_format` | unchanged | `updated` changes | `schema` |
| `link_label` | unchanged | `name` changes | **nothing — a declared gap** |

`link_label` is the honest one. The page's structure is untouched and the extracted name
silently becomes `Details` for every row. No detector in `bdheal` sees it, the benchmark
reports it as a coverage gap rather than quietly omitting it, and that is the finding.

## Collectors MUST be single-page

A `scraper create` pointed at a listing URL builds a **site crawler**, not a page
extractor. A probe collector built this way walked 1.05K pages and failed 999 of them to
return one record.

Every benchmark collector's description must say, explicitly: **extract from this page
only, follow no links, no pagination.** Check the page count of the first collector against
the Bright Data dashboard before running the remaining cases.

The `href` values on these pages (`/register/rf-001`, …) are **extracted as data and never
meant to be followed**. They deliberately resolve to nothing, and the pages carry
`<meta name="robots" content="nofollow">`, so a collector that ignores its single-page
instruction fails loudly here rather than quietly crawling. That is a tripwire, not a
guarantee — the description is what actually scopes the collector.

## Publishing

`deploy.sh` pushes `site/` straight to the `gh-pages` branch instead of using a Pages
Actions workflow, because Actions publishing needs the `workflow` OAuth scope that
`gh auth login` does not grant by default. A direct branch push needs only `repo`.

Pages serves through a CDN: **wait 30–60 seconds** after publishing before pointing a
collector at the site, or it reads the previous markup and the measurement is worthless.

Enable Pages once, per repository: Settings → Pages → deploy from branch → `gh-pages` / root.
