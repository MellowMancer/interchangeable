# bdheal

Self-healing for [Bright Data Scraper Studio](https://docs.brightdata.com/datasets/scraper-studio)
collectors: **detect → diagnose → heal → verify → promote or roll back**.

It is corpus-agnostic by construction. It knows collector ids, Pydantic schemas, anchor
URLs and HTML structure — and nothing about any problem domain. If you have a Bright
Data account and a Pydantic model, it is meant for you.

> **Status: implemented; not yet run against a live account.** Every call below is
> implemented and covered — `pytest packages/bdheal` is green with no corpus, no database
> and no network. What has *not* happened yet is an end-to-end run against a real Bright
> Data collector; the benchmark that will do that lives in `fixtures/`, and until it has
> run, the numbers this package can produce are untested against reality.

## Install

Not published to an index yet. From a checkout:

```bash
uv pip install ./packages/bdheal
```

Runtime dependencies are exactly three: `pydantic`, `selectolax`, `lxml`.
No web framework, no CLI framework, no HTTP client. The `bdata` CLI it drives is
invoked through `npx`, so Node is a runtime requirement of the default adapter.

## The usage shape

Both ports are constructor arguments. The package ships no composition root and no
module-level client: nothing reaches the network unless you hand it something that can.

```python
from pathlib import Path

from bdheal import CollectorSpec, Healer
from bdheal.clock import SystemClock
from bdheal.process import SubprocessRunner
from bdheal.store import SqliteHealStore, connect
from bdheal.studio import BdataStudioClient

clock = SystemClock()
healer = Healer(
    studio=BdataStudioClient(SubprocessRunner(), clock),
    store=SqliteHealStore(connect(Path("heal.db"))),
    clock=clock,
)

spec = CollectorSpec(
    collector_id="c_...",
    name="listings",
    anchor_urls=["https://example.com/listings"],
    row_schema=MyRow,
)

result = healer.run(spec, spec.anchor_urls)
verdict = healer.detect(spec, result)
if verdict.broken:
    event = healer.heal(spec, verdict)
    report = healer.verify(spec, golden_rows, old_layout_url="https://example.com/old")
```

Substituting your own `StudioClient` or `HealStore` needs no inheritance — the ports are
`Protocol`s, satisfied structurally.

## Checks

```bash
uv run --package bdheal pytest packages/bdheal
```

Green with no corpus, no database, no application and no network: both ports are stubbed
at their interfaces. Two markers are gated out of that run because they need the
network — set the variable to opt in:

| Marker | Variable | What it does |
|---|---|---|
| `live` | `BDHEAL_LIVE=1` | calls the real `bdata` CLI, to confirm its surface has not moved |
| `publish` | `BDHEAL_PUBLISH_CHECK=1` | builds wheel and sdist, installs into an empty venv from the declared ranges alone, and proves `import bdheal` works with this repo off `sys.path` |

The fixture benchmark that exercises the loop end to end is a separate concern and lives
outside this package, in `fixtures/` — `bdheal` is corpus-agnostic and does not ship one.
See `docs/GOLDEN_BENCHMARK.md`.

The package carries no lockfile of its own, deliberately: a lock pins one resolution for
one application, and cannot show that a library resolves for anybody else. The `publish`
check is what backs the claim instead.

See `docs/ARCHITECTURE.md` for the layer map and the contribution contract.
