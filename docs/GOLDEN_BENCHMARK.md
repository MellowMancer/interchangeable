# The golden benchmark — runbook

This file tells how the project measures `bdheal`. The project controls a site. The
project breaks the site when it decides. True collectors scrape the site. The project then
compares the results against records made from the same dataset that made the site.

Scraper Studio runs in the Bright Data cloud. It cannot connect to `localhost`. Therefore
the fixture site must be public. This is the only reason for GitHub Pages.

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

# 3. Publish, wait 30-60s for the CDN, then prove the served bytes are the rendered ones.
fixtures/deploy.sh
BDHEAL_PAGES_URL=https://mellowmancer.github.io/interchangeable \
  uv run --package bdheal pytest fixtures/tests -m pages

# 4. The live run. Spends real credit and takes hours.
BDHEAL_BENCH=1 BDHEAL_PAGES_URL=https://mellowmancer.github.io/interchangeable \
  uv run --package bdheal python fixtures/benchmark.py
```

Steps 1 to 3 are free and quick. `BDHEAL_BENCH=1` gates step 4. This gate prevents an
accidental start.

**The CDN delay in step 3 is necessary.** Pages supplies the site through a cache. A
collector that runs against the site too early reads the previous markup. The run
then completes, the numbers are incorrect, and no component reports an error. Step 3
compares the supplied bytes against the local files and finds this condition. A 200 status
from each URL does not find it.

## Before a live run

**`bdata budget` returns 403** with the message "API key lacks the required permissions".
There is no read-only `scraper list` command to test with. Therefore a check of the
scraper permissions needs a true `create`, which costs credit. Examine the control
panel first.

The code now enforces two other pre-flight items. The single-page clause is a constant
with a length guard in `fixtures/benchmark.py`. The report prints the
`mean_attempts_to_heal` caveat adjacent to the number.

**`make release` puts `data/` into the image.** A release during a run gives an image that
contains a partially measured benchmark. This is worse than an old benchmark,
because the page shows the data that it has as if that data were the full result.

## An upstream failure stops the run, by design

`bdheal.errors.StudioError: scraper run exited 1: fetch failed` shows that a Bright Data
scrape failed. It is not a defect in this repository. The runner catches one exception
only: `VerificationIncompleteError`. Each other exception stops the run, because each
other exception is a defect. This occurred on 2026-08-23 at case four of ten.

To continue a run, start it again with the same `--run-id`. The runner omits the completed
cases. The collector memo prevents a rebuild of the ten collectors. But the runner
discards a memo that has no `base_url`, and then builds each collector again. That
operation takes approximately twenty minutes and the credit for ten builds. Therefore
examine the memo for a `base_url` first. Do not assume that a restart is inexpensive.

## Where to find the details

This file is the runbook only. Each item below has one location, and that location is not
this file. A caveat in three files can become three different caveats. These copies were
already different about the quantity of collectors that a run builds.

| Question | Answer is in |
|---|---|
| What each mutation does, and which signals it must trip | `fixtures/README.md` — *What each mutation is expected to do* |
| Why step 2 shows something that step 1 cannot, and the element-boundary assumption | `fixtures/README.md` — *Checks* |
| Why a collector must be single-page, and why the fixture links are dead | `fixtures/README.md` — *Collectors MUST be single-page* |
| Why `deploy.sh` pushes a branch and does not use a Pages Actions workflow | `fixtures/README.md` — *Publishing* |
| Why the row schema **is** the instrument, and the cost of a looser schema | `fixtures/benchmark.py` module docstring |
| **Why `date_format` and `url_pattern` are detected but cannot be healed** | `fixtures/benchmark.py` module docstring |
| What a run costs, and how `--run-id` continues a run | `fixtures/benchmark.py` module docstring |

Read the bold row before publishing a number. The two classes give
`caught_by=schema, healed=False` **by design**. The schema that detects them is the same
schema that refuses the healed output. To add them to a heal rate without this statement
reports a property of the mutation as a failure of the heal.

For the coverage-matrix contract, see `docs/ARCHITECTURE.md` §14. For the CLI, see
`docs/BRIGHT_DATA.md`.
