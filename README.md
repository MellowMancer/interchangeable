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

## The finding

Three UK-authorised ramipril products, same active ingredient, three manufacturers. All
three state the same clinical fact — ramipril must not be started until 36 hours after the
last dose of sacubitril/valsartan. They do not agree on how binding it is:

| Manufacturer | Where the washout appears |
|---|---|
| Aurobindo Pharma – Milpharm | **§4.3 Contraindications** — an absolute bar |
| Wockhardt UK | §4.5 Interactions |
| Zentiva | §4.5 Interactions |

A pharmacist reading Aurobindo's label sees a contraindication. Reading Zentiva's, they
see an interaction. Same molecule, same requirement, different regulatory weight — and
nothing on either label says the other exists.

That row is produced by the pipeline in this repository, with the quote behind each cell
sliced from the stored section text at the character offsets shown, so every cell can be
checked against its source.

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
classification, comparison, an HTTP API, an MCP server and the three UI screens.

The self-healing loop has been driven through a full cycle against a controlled fixture
site. On a real layout mutation it detected the break, named the signal, repaired the
collector and scored the result — `field_accuracy 1.0`, and the non-regression check
passed, meaning the repair also still works against the layout it was built for. The
collector id was unchanged throughout, which is the property the design rests on. The
repair was confirmed to persist by re-running the collector from a cold process. On an
unmutated control page the detector stayed silent, which is the only measurement that can
show it is not simply firing on everything.

`medicines.org.uk` cannot be broken on cue, which is why that evidence comes from a site
we control — see `docs/GOLDEN_BENCHMARK.md`.

Nothing here is production-ready, and nothing it outputs is medical advice.

## Deploying

The web app goes to Vercel (root directory `web`, with `API_URL` set to the API's
public URL); the API goes to Render as a free web service. Neither needs a card.

The corpus is shipped, not scraped in place. `ixq run` writes `data/*.db` locally,
`docker build` bakes them into the image, and refreshing the data means a rebuild and
a redeploy. The API only ever reads, so the container needs a writable filesystem —
`bdheal`'s schema is applied on every connection — but never a persistent one: nothing
written at runtime outlives the request that wrote it. That is what lets it sit on a
free tier at all, since Render's free instances have no persistent disk. It serves
every endpoint in about 70 MB against the free instance's 512 MB.

`data/` is gitignored, so the image is **built locally and pushed to a registry**;
letting Render build from the repo would produce a service with empty databases.

```bash
# one-time: a GitHub personal access token with write:packages
echo $GH_TOKEN | docker login ghcr.io -u <github-user> --password-stdin

# every release: build, push, and tell Render to pull the new tag
make release
```

`make release` reads `GH_USER` and `RENDER_DEPLOY_HOOK` from `.env`, which is gitignored;
pass them in the environment instead if you keep them elsewhere.

Create the service once as a Render **web service from an existing image** — not a
private service, which only other Render services can reach — pointing at
`ghcr.io/<github-user>/ixq-api` with the port set to 8000. Make the GHCR package public
and no registry credentials are needed.

`make release` exists because none of this can move to CI: `data/` is gitignored, so a
GitHub Actions runner has no corpus to bake in. Its build flags are both load-bearing —
Render requires `linux/amd64`, and without `--provenance=false` buildx emits a
multi-arch manifest list it will not pull. The final `curl` is Render's deploy hook,
taken from the service's Settings tab; an image-backed service never redeploys itself
when a tag is pushed. Keep the hook URL in the environment, not in a file: it is a
secret that triggers a deploy for anyone holding it.

A free Render service spins down after 15 minutes idle, and every page is a Server
Component, so a sleeping API does not degrade a page — it stalls it. `.github/workflows/
keep-warm.yml` pings `/health` every 13 minutes to stay inside that window.

GitHub delays scheduled workflows under load, sometimes past the 15-minute threshold, so
treat the workflow as best-effort: a lapsed ping costs one ~12s cold start, not an
outage. A dedicated pinger (cron-job.org, UptimeRobot) holds the interval more reliably
if the demo must never wait.

Uptime is the binding constraint on the free plan, not memory or image size. The
allowance is 750 instance hours per workspace per calendar month against the 744 a
service running continuously uses in a 31-day month — six hours of margin, and only for
one service. Which is why the web half lives on Vercel.

The same image runs unmodified on Cloud Run (`--port 8000 --allow-unauthenticated`) if a
Google billing account is ever available; Render is the default because it needs no card.

Every page is a Server Component, so the browser never calls the API and the API needs
no CORS configuration. Before pushing a change, run the image with no volume mounted —
that is what proves the baked databases are present:

```bash
docker run --rm -p 8099:8000 "$IMG"
curl localhost:8099/substances   # empty array means the databases did not ship
```

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

The Makefile exists only for these and `make release`: the underlying `docker
compose run` invocations are long, and the `--user` flag they need on Linux must
be omitted on macOS. `make lock` regenerates both lockfiles after a manual manifest edit.

`uv.lock` and `web/pnpm-lock.yaml` are committed and the images install
frozen, so builds are reproducible across machines.
