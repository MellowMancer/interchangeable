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
                     └────────►  site/pages.html         a human index of the above
                     └────────►  site/manifest.json      pages, expected signals, goldens
```

`pages.html` is the only page here meant to be clicked. It links to every fixture and no
fixture links back, so a collector anchored on a fixture can never reach it and the
single-page rule below is untouched. It is not a benchmark page and is absent from the
manifest.

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
| `class_rename` | moves | unchanged | `skeleton`, `row_count` |
| `table_to_div` | moves | unchanged | `skeleton`, `row_count` |
| `column_reorder` | moves | unchanged | `skeleton` |
| `field_split_merge` | moves | unchanged | `skeleton` |
| `wrapper_nesting` | moves | unchanged | `skeleton` |
| `pagination` | moves | **only the first page survives** | `skeleton`, `row_count` |
| `url_pattern` | unchanged | `href` changes | `schema`, `null_rate` |
| `date_format` | unchanged | `updated` changes | `schema`, `null_rate` |
| `link_label` | unchanged | `name` changes | **nothing — a declared gap** |

`pagination` is the only class that drops data rather than moving it: the listing is split and the rows beyond the first page genuinely stop arriving, so its golden is the first half of the dataset. It is also the only class that exercises the volume detector — nothing else in the set changes the row count.

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

The `href` values on these pages are **extracted as data and never meant to be
followed**. They deliberately resolve to nothing, and the pages carry
`<meta name="robots" content="nofollow">`, so a collector that ignores its single-page
instruction fails loudly here rather than quietly crawling. That is a tripwire, not a
guarantee — the description is what actually scopes the collector.

`base_path` in `data.json` is what keeps the tripwire inside this site. A root-relative
`/register/rf-001` resolves against the *account* root on a project Pages site, so it fails
on a site these fixtures do not own; `/interchangeable/register/rf-001` fails within the
published one. Change `base_path` when publishing anywhere else — it is applied once, before
anything is rendered or scored, so the pages and the goldens cannot disagree about it.

**One page escapes that containment, and it is the honest exception:** `url_pattern` exists
to move links onto another prefix, and `MOVED_PATH_PREFIX` goes on the front, so its links
read `/v2/interchangeable/…` and land outside the site again. A mutation whose whole subject
is links moving somewhere else cannot also keep them where they were.

## Checks

```bash
uv run --package bdheal pytest fixtures/tests            # goldens, offline
```

Three things, none of which `render.py` can establish about itself: that re-rendering
reproduces the committed `site/` byte-for-byte, that **parsing each page back yields the
golden it is scored against**, and that the manifest's declared signals still match
`MUTATIONS`. The second is the one that matters — `render.py` derives goldens from
`data.json`, which proves they agree with the *dataset*, not with the *pages*.

The extractor there makes exactly one assumption about how a page is read: **an element
boundary counts as whitespace.** `field_split_merge` rewrites a name as two adjacent spans
with no separator, so concatenating their text gives `CobaltSpindle Bracket` — what a
browser renders, and not what the golden says. Joining on the boundary is what "one column
becomes two" means.

After publishing, point the same suite at the deployed site:

```bash
BDHEAL_PAGES_URL=https://<owner>.github.io/<repo> \
  uv run --package bdheal pytest fixtures/tests -m pages
```

Byte-for-byte against the local files, because a 200 from every URL says the site is up,
not that the CDN has caught up with the deploy.

## Publishing

`deploy.sh` pushes `site/` straight to the `gh-pages` branch instead of using a Pages
Actions workflow, because Actions publishing needs the `workflow` OAuth scope that
`gh auth login` does not grant by default. A direct branch push needs only `repo`.

Pages serves through a CDN: **wait 30–60 seconds** after publishing before pointing a
collector at the site, or it reads the previous markup and the measurement is worthless.

Enable Pages once, per repository: Settings → Pages → deploy from branch → `gh-pages` / root.
