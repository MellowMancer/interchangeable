# bdheal benchmark fixtures

These are the pages that the self-healing benchmark runs against. A true site does not
change its design on demand. Therefore the benchmark supplies a site that it
controls fully, and breaks that site.

## The data is synthetic — read this first

Each record in `data.json` is invented. The reference codes, the component names and the
dates describe nothing that exists. Each generated page shows a banner that says this. Do
not use these pages to represent anything true.

## How it works

```
data.json  ──►  render.py  ──►  site/base.html           the base ("old") layout
                     │
                     └────────►  site/<mutation>.html    one page per bdheal mutation class
                     └────────►  site/index.html         a human index of the above
                     └────────►  site/manifest.json      pages, expected signals, goldens
```

`index.html` is the only page here for a person to click. GitHub Pages supplies it at the
root of the site. A visitor then gets an index that tells them what the site is. They do
not get the base layout of the benchmark with no context. `index.html` links to each
fixture, and no fixture links back to it. Therefore a collector that is anchored on a
fixture cannot reach the index, and the single-page rule below stays correct. `index.html`
is not a benchmark page and is not in the manifest.

The base layout is `base.html`. Each consumer reads that name from
`manifest["base_page"]`. Therefore a new name for the file changed no downstream code.
`render.py` does not remove files. Therefore a page with an old name stays in `site/`
until a manual delete removes it.

One dataset is the single source of truth. `render.py` makes the base page from the
dataset. Each mutated page is that same base page after one of the generators in
`bdheal`'s own `bench/mutate.py`. **`render.py` derives the golden records from the
dataset. It does not transcribe them.** Therefore a page and the records that score it
cannot become different.

`site/` is generated, but the repository contains it intentionally. A `git diff` of `site/`
between two renders is the record of what a mutation changed, and a person can review it.

```bash
uv run --package bdheal python fixtures/render.py   # regenerate
fixtures/deploy.sh                                  # render + publish to gh-pages
```

## What each mutation must do

The project verified this table against the rendered site. It did not assert the table.

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

`pagination` is the only class that removes data. The other classes move data. `pagination`
divides the listing, and the rows after the first page stop arriving. Therefore its golden
is the first half of the dataset. It is also the only class that tests the volume detector,
because no other class in the set changes the row count.

`link_label` is the honest class. The structure of the page does not change, and the
extracted name becomes `Details` for each row. No detector in `bdheal` sees this. The
benchmark reports it as a coverage gap. It does not omit it. That report is the finding.

## Collectors MUST be single-page

A `scraper create` that points at a listing URL builds a **site crawler**. It does not
build a page extractor. A probe collector that was built in this way walked 1.05K pages,
failed 999 of them, and returned one record.

The description of each benchmark collector must say this: **extract from this page only,
follow no links, no pagination.** Compare the page count of the first collector with the
Bright Data dashboard before the other cases run.

The system extracts the `href` values on these pages as data. **A collector must not
follow them.** They resolve to nothing, and each page contains
`<meta name="robots" content="nofollow">`. Therefore a collector that does not obey its
single-page instruction fails here, and the failure is visible. This is a tripwire and not
a guarantee. The description is what limits the collector.

`base_path` in `data.json` keeps the tripwire in this site. On a project Pages site, a
root-relative path such as `/register/rf-001` resolves against the *account* root.
Therefore it fails on a site that these fixtures do not own.
`/interchangeable/register/rf-001` fails in the published site. Change `base_path` for
publication to a different location. `render.py` applies `base_path` one time, before it
renders or scores anything. Therefore the pages and the goldens cannot disagree about it.

**One page is outside that containment, and it is the honest exception.** `url_pattern`
exists to move links to a different prefix. `MOVED_PATH_PREFIX` goes at the front.
Therefore its links are `/v2/interchangeable/…` and are outside the site again. A mutation
whose subject is links that move to a different location cannot also keep those links in
their original location.

## Checks

```bash
uv run --package bdheal pytest fixtures/tests            # goldens, offline
```

These tests show three things, and `render.py` cannot show any of them about itself. First,
that a second render makes the committed `site/` byte for byte. Second, that **a parse of
each page gives the golden that scores it**. Third, that the signals in the manifest still
agree with `MUTATIONS`. The second test is the important one. `render.py` derives the
goldens from `data.json`, which shows that they agree with the *dataset*. It does not show
that they agree with the *pages*.

The extractor in the tests makes one assumption about how to read a page: **an element
boundary is whitespace.** `field_split_merge` writes a name as two adjacent spans with no
separator. A join of their text gives `CobaltSpindle Bracket`. A browser shows that,
but the golden does not contain it. To join on the boundary is the meaning of "one column
becomes two".

After publication, point the same suite at the deployed site:

```bash
BDHEAL_PAGES_URL=https://<owner>.github.io/<repo> \
  uv run --package bdheal pytest fixtures/tests -m pages
```

The suite compares byte for byte against the local files. A 200 status from each URL shows
that the site operates. It does not show that the CDN has the new deploy.

## Publishing

`deploy.sh` pushes `site/` directly to the `gh-pages` branch. It does not use a Pages
Actions workflow, because publication with Actions needs the `workflow` OAuth scope.
`gh auth login` does not grant that scope by default. A direct branch push needs the `repo`
scope only.

Pages supplies the site through a CDN. **Wait 30 to 60 seconds** after publication, before
a collector points at the site. Without that delay, the collector reads the previous
markup and the measurement has no value.

Enable Pages one time for each repository: Settings → Pages → deploy from branch →
`gh-pages` / root.
