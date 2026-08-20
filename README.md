# Interchangeable?

Same drug, different manufacturer, different label.

When a pharmacy dispenses a generic, it substitutes whichever manufacturer's version is
on the shelf. Everyone — patient and prescriber alike — assumes same drug, same
information. That assumption is not always true.

**Interchangeable?** compares the UK Summaries of Product Characteristics of every
authorised product sharing an active substance, and shows where the manufacturers
disagree — with the exact quoted text behind every claim.

The question mark is deliberate. The project asks whether these products really are
interchangeable; it does not assert that they are not.

## The finding that started it

Three UK-authorised ramipril products, same active ingredient:

| Product | §4.3 Contraindications |
|---|---|
| Ramipril 10mg Tablets | hypersensitivity · angioedema history · concomitant sacubitril/valsartan |
| Ramipril 2.5mg Tablets | *identical three* |
| **Ramipril 1.25mg Tablets** | hypersensitivity · angioedema history · **extracorporeal treatments** · **bilateral renal artery stenosis** · **2nd/3rd trimester pregnancy** |

One manufacturer lists later-pregnancy use as an absolute contraindication. Two do not
list it in §4.3 at all. Divergence runs both ways — the third omits the
sacubitril/valsartan contraindication the others carry.

## What it will and will not say

Absence from §4.3 does not prove absence from the label: a warning missing there is often
present in §4.4 or §4.6. So the system reports **placement**, never omission it has not
checked, and every claim names the sections that were actually scanned.

Divergence is reported as individual findings, not as a rate. Establishing a rate needs a
far larger run than has been done.

Clauses that match no known concept are counted and published as `unclassified` rather
than dropped. A visible recall gap is worth more than a clean-looking result that quietly
lost what it could not parse.

## How it works

Labels are collected through Bright Data Scraper Studio: a collector generated from a
one-line description returns the structured sections of a product page, and `bdheal` —
the self-healing loop in `packages/bdheal/` — detects when a page's structure drifts,
composes a repair prompt, verifies the fix against goldens and the previous layout, and
promotes or rolls back. The collector ID never changes, so nothing downstream notices.

No language model sits in the data path. Section splitting is deterministic because the
EU SmPC format is legally standardised, concept matching is a YAML lexicon, and every
quote is sliced from the stored section text at exact character offsets — so a claim can
always be checked against its source.

## Ask it from an agent

The comparison is also exposed over MCP, so an assistant can answer a dispensing question
directly rather than being handed a dashboard:

```bash
ixq-mcp        # stdio MCP server
```

| Tool | Question |
|---|---|
| `label_says(substance, concept)` | Does this manufacturer's label contraindicate X? |
| `divergences(substance)` | Where do these manufacturers disagree? |

Both answers name the sections that were actually scanned, and a concept that was never
matched comes back as `found: false` with the list of concepts that *are* known — never as
a bare "no". `divergences` includes each label's revision date, so a one-sided finding can
be read as a stale label rather than a real disagreement.

## Status

Working end to end for the ramipril corpus: collection, section splitting, concept
classification, comparison, an HTTP API and an MCP server. The UI is not built yet.
Nothing here is production-ready, and nothing it outputs is medical advice.

## Development

Everything runs in Docker; nothing is installed on the host.

```bash
docker compose watch   # start both services with live reload
docker compose down    # stop
```

- API — http://localhost:8000 (`/health`, `/docs`)
- Web — http://localhost:3000

`docker compose watch` copies changed files into the running containers rather
than bind-mounting the working tree, so build artifacts (`.next`,
`node_modules`, `__pycache__`) stay inside the containers and never land in
your checkout.

### Adding dependencies

```bash
make add-py pkg=httpx    # Python, into ixq
make add-py pkg=httpx member=bdheal
make add-js pkg=zod      # Node
docker compose build     # rebuild images with the new dependency
```

The Makefile exists only for these three: the underlying `docker compose run`
invocations are long, and the `--user` flag they need on Linux must be omitted
on macOS. `make lock` regenerates both lockfiles after a manual manifest edit.

`uv.lock` and `web/pnpm-lock.yaml` are committed and the images install
frozen, so builds are reproducible across machines.
