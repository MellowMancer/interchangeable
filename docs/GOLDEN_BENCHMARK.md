# The golden benchmark — runbook

How `bdheal` is measured: a site we control, broken on cue, scraped by real collectors, and
scored against records derived from the same dataset that rendered it.

Scraper Studio executes in Bright Data's cloud and cannot reach `localhost`, so the fixture
site has to be publicly hosted. That is the only reason GitHub Pages is in this picture.

```
fixtures/data.json ──► render.py ──► fixtures/site/ ──► gh-pages ──► collectors
                                          │
                                          └─ manifest.json ──► fixtures/benchmark.py ──► metrics
```

## The four commands

```bash
# 1. The library, offline. No corpus, no database, no network.
uv run --package bdheal pytest packages/bdheal

# 2. The fixture goldens, offline.
uv run --package bdheal pytest fixtures/tests

# 3. Publish, wait 30-60s for the CDN, then prove the served bytes are ours.
fixtures/deploy.sh
BDHEAL_PAGES_URL=https://mellowmancer.github.io/interchangeable \
  uv run --package bdheal pytest fixtures/tests -m pages

# 4. The live run. Spends real credit and takes hours.
BDHEAL_BENCH=1 BDHEAL_PAGES_URL=https://mellowmancer.github.io/interchangeable \
  uv run --package bdheal python fixtures/benchmark.py
```

Steps 1–3 are free and fast. Step 4 is gated behind `BDHEAL_BENCH=1` precisely so it cannot
be reached by accident.

## What step 2 establishes that nothing else does

`render.py` derives every golden from `data.json` using the mutation generators' own
constants. That proves the goldens agree with the **dataset**. It does not prove they agree
with the **pages**: the generators perturb HTML through `lxml` while the goldens are
transformed at the dict level, and a divergence between those two paths would corrupt every
published number with the whole suite still green.

So `fixtures/tests/test_golden.py` parses the committed pages back and compares. It also
re-renders into a temp directory and asserts byte-identity with `fixtures/site/`, which is
what makes a `git diff` of that directory an honest record of what a mutation changed.

**The one assumption it makes:** an element boundary counts as whitespace.
`field_split_merge` rewrites a name as two adjacent spans with no separator, so
concatenating their text gives `CobaltSpindle Bracket` — what a browser renders, and not
what the golden says. Joining on the boundary is what "one column becomes two" means.

## Publishing

`deploy.sh` pushes `fixtures/site/` straight to the `gh-pages` branch rather than through a
Pages Actions workflow, because Actions publishing needs the `workflow` OAuth scope that
`gh auth login` does not grant by default. A direct branch push needs only `repo`. It
commits inside a temp directory, never in this working tree.

Pages serves through a CDN. **Wait 30–60 seconds** after publishing before pointing a
collector at the site, or it reads the previous markup and the measurement is worthless.
Step 3's byte-comparison is what catches that, where a 200 from every URL would not.

## Links on the fixture site are dead on purpose

They are extracted as data and never followed. `base_path` in `data.json` keeps them dead
*inside* the published site: a root-relative `/register/rf-001` resolves against the account
root on a project Pages site, which is not a site these fixtures own. Change `base_path`
when publishing anywhere else.

`url_pattern` is the declared exception — it exists to move links onto another prefix, and
`MOVED_PATH_PREFIX` goes on the front, so its links read `/v2/interchangeable/…` and land
outside the site again. A mutation whose subject is links moving cannot also keep them put.

`pages.html` is the one page here meant to be clicked. It links to every fixture and no
fixture links back, so a collector anchored on a fixture can never reach it.

## The row schema is the instrument, not decoration

`fixtures/benchmark.py` declares what a healthy row looks like, and that declaration is what
makes the declared signals fire at all:

- `updated` must refuse a day-first date, or `date_format` trips nothing.
- `href` must refuse a link that moved, or `url_pattern` trips nothing.

Loosen either to a plain `str` and those classes report a **detector** gap that is really a
schema gap. Both fields are constrained strings rather than `date` and `AnyUrl` because
`studio.py` validates with `model_dump()` and `verify.py` scores with no normalisation, so a
`date`-typed field would dump a `datetime.date` that can never equal the golden's
`"2026-01-14"`.

### Read this before publishing the numbers

The schema that detects `date_format` and `url_pattern` is the same schema that rejects the
healed output: once the page changes, the values a correct collector extracts are exactly
the ones the schema refuses. Bright Data's heal repairs selectors, not your Pydantic model.
Both classes are therefore expected to come out **detected and then not healable** —
`caught_by=schema`, `healed=False`. That is a property of what the mutation does, not a
failure of healing, and it belongs in the write-up rather than folded silently into the heal
rate.

## Cost and resumption

Nine collectors at roughly two minutes each to build, then several collector runs per case.
State is written per case, so re-running with the same `--run-id` executes only what is
left, and collector ids are remembered in `fixtures/run/collectors.json` so a second run
does not pay to build them again. Bright Data exposes no programmatic delete, so that file
is written after every single build rather than at the end.

## Before the first live run

- **`bdata budget` currently returns 403**, "API key lacks the required permissions". There
  is no read-only `scraper list` to probe with, so scraper permissions cannot be confirmed
  without spending a real `create`. Check the control panel first.
- Every collector description must say **this page only, follow no links, no pagination**.
  A probe collector built without it walked 1.05K pages and failed 999 of them to return a
  single record.
- `mean_attempts_to_heal` is `1.0` by construction until the runner has a retry budget. The
  report says so where it prints the number; keep that caveat attached.

See `docs/ARCHITECTURE.md` §14 for the coverage-matrix contract and `docs/BRIGHT_DATA.md`
for the CLI surface.
