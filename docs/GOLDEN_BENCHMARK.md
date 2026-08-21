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

**The CDN wait in step 3 is not politeness.** Pages serves through a cache, so a collector
pointed at the site too early reads the previous markup — the run completes, the numbers are
worthless, and nothing reports an error. Step 3's byte-comparison against the local files is
what catches that, where a 200 from every URL would not.

## Before a live run

**`bdata budget` returns 403**, "API key lacks the required permissions". There is no
read-only `scraper list` to probe with, so scraper permissions cannot be confirmed without
spending a real `create`. Check the control panel first.

The other two pre-flight items are now enforced rather than remembered: the single-page
clause is a constant with a length guard in `fixtures/benchmark.py`, and the
`mean_attempts_to_heal` caveat is printed beside the number by the report itself.

## Where the details live

This file is the runbook and nothing more. Everything below has exactly one home, and it is
not here — a caveat kept in three places is three places to drift, and these copies had
already disagreed with each other about how many collectors a run builds.

| Question | Answered in |
|---|---|
| What each mutation does, and which signals it should trip | `fixtures/README.md` — *What each mutation is expected to do* |
| Why step 2 establishes something step 1 cannot, and the element-boundary assumption | `fixtures/README.md` — *Checks* |
| Why collectors must be single-page, and why the fixture links are dead | `fixtures/README.md` — *Collectors MUST be single-page* |
| Why `deploy.sh` pushes a branch rather than using a Pages Actions workflow | `fixtures/README.md` — *Publishing* |
| Why the row schema **is** the instrument, and what loosening it costs | `fixtures/benchmark.py` module docstring |
| **Why `date_format` and `url_pattern` are detected and then not healable** | `fixtures/benchmark.py` module docstring |
| What a run costs, and how `--run-id` resumes one | `fixtures/benchmark.py` module docstring |

The bold row is the one to read before publishing any number. Those two classes come out
`caught_by=schema, healed=False` **by construction** — the schema that detects them is the
same schema that rejects the healed output — so folding them into a heal rate without saying
so would report a property of the mutation as a failure of healing.

See `docs/ARCHITECTURE.md` §14 for the coverage-matrix contract and `docs/BRIGHT_DATA.md`
for the CLI surface.
