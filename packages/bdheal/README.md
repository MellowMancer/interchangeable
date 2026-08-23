# bdheal

Self-healing for [Bright Data Scraper Studio](https://docs.brightdata.com/datasets/scraper-studio)
collectors: **detect → diagnose → heal → verify → promote or roll back**.

It is corpus-agnostic by construction. It knows collector ids, Pydantic schemas, anchor
URLs and HTML structure, and nothing about any problem domain. It is for a project that
has a Bright Data account and a Pydantic model.

> **Status: Implemented; And tested against a live account.** Every call below is
> implemented and covered — `pytest packages/bdheal` is green. An end-to-end run against a real Bright
> Data collector was conducted for the benchmark that lives in `fixtures/`.

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
module-level client: nothing reaches the network unless the caller supplies something
that can.

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

A substitute `StudioClient` or `HealStore` needs no inheritance — the ports are
`Protocol`s, satisfied structurally.

## Checks

```bash
uv run --package bdheal pytest packages/bdheal
```

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
