# ARCHITECTURE — `bdheal`

The contract every feature in `GOAL.md` is written against. F0 produced it; F1–F12 fill
the frame it defines. Where this document and a feature's own instinct disagree, this
document wins — twenty consistent slices are worth more than twenty clever ones.

Authoritative inputs: `GOAL.md` (invariants G1–G6, features, resolved decisions Q1–Q4),
`docs/plan.md` (package split, public surface, heal loop, benchmark), and
`docs/BRIGHT_DATA.md` (the verified `bdata` CLI surface — it wins over `plan.md`).

---

## 1. The one dependency arrow

```
preward (the app)  ──depends on──▶  bdheal  ──▶  bdata CLI  ──▶  Bright Data
```

Never the reverse (G2). `bdheal` is a sibling of `api/`, not a child, because the peer
relationship *is* the architectural claim: a package buried inside the application it
serves is not independently publishable, whatever its manifest says.

`bdheal` knows: collector ids, Pydantic schemas, anchor URLs, HTML structure.
`bdheal` never knows: sources, records, tiers, signals-in-the-domain-sense, documents, lexicons.
A term from any problem domain appearing under `packages/bdheal/` is a defect.

## 2. Workspace wiring (resolved decision Q1)

```
rf-pre/
├─ pyproject.toml          # virtual uv workspace root; members = api, packages/bdheal
├─ uv.lock                 # ONE lockfile for the workspace
├─ .dockerignore           # the api image builds from the repo root, so this is its ignore file
├─ compose.yaml            # api: context ".", dockerfile "api/Dockerfile"
├─ packages/bdheal/        # this package
└─ api/                    # the app; declares bdheal via [tool.uv.sources] workspace = true
```

The api image needs the workspace lockfile *and* `packages/bdheal`, so its build context
is the repo root. `api/uv.lock` is superseded by `/uv.lock`.

**F1 does this first, before anything else:** run `uv lock` at the repo root, delete the
now-dead `api/uv.lock` and `api/.dockerignore`, then confirm
`docker compose build api` exits 0. Until the root lockfile exists the image cannot
build — that is expected at F0, not a defect.

## 3. Layer map

Every module in `packages/bdheal/src/bdheal/` belongs to exactly one layer.
`tests/test_architecture.py` enforces this table; adding a module without updating both
fails the suite.

| Layer | Module | Role |
|---|---|---|
| **Entities** | `models.py` | Every type that crosses a boundary — Pydantic |
| | `vocabulary.py` | Closed vocabularies: signal kinds, heal statuses, failure classes, mutation classes |
| | `errors.py` | The package's exception hierarchy |
| | `skeleton.py` | Structural fingerprint of a page — pure, deterministic |
| | `bench/mutate.py` | The nine HTML perturbations and their declared detectors — pure |
| | `bench/metrics.py` | The five metrics and the coverage matrix — pure |
| **Use Cases** | `ports.py` | Every abstract seam: `StudioClient`, `HealStore`, `Clock`, `CommandRunner`, `HealLoop` |
| | `detect.py` | The four signals and the throttle policy |
| | `diagnose.py` | Failure class → prompt template → rendered prompt |
| | `heal.py` | The heal/approve gate, writing an event on every terminal outcome |
| | `verify.py` | Golden diff plus the non-regression pass |
| | `healer.py` | The `Healer` facade — the public entry point |
| | `bench/runner.py` | Drives cases through a `HealLoop`, persists resume state |
| **Interface Adapters** | `studio.py` | `BdataStudioClient`: argv shaping, JSON parsing, error-row mapping |
| | `store.py` | `SqliteHealStore` + `connect()`; ships `schema.sql` |
| **Frameworks & Drivers** | `clock.py` | `SystemClock` — the only place time is read |
| | `process.py` | `SubprocessRunner` — the only place a process starts |
| | `__init__.py`, `bench/__init__.py` | Export surface / composition |

Two carve-outs, stated so nobody has to guess:

- **Pure-computation libraries may appear in Entities.** `pydantic`, `selectolax`,
  `lxml` and `hashlib` compute; they do not perform I/O. Anything that opens a socket,
  a file, a database or a process may not appear inside Entities or Use Cases —
  that is the line the Dependency Rule actually protects.
- **`bdheal` ships no composition root.** There is no `default_healer()` and no
  module-level client. The caller wires `Healer(studio, store, clock)`. A library that
  can reach the network without being handed the means to is not testable in isolation.

## 4. Dependency rules

1. **Inward only.** A module may import from its own layer or any layer inside it.
   Never outward. Enforced by `test_dependencies_point_inward`.
2. **Shared inner layers are importable from anywhere.** `models`, `vocabulary`,
   `errors`, `skeleton` and `ports` are the shared spine; every module may import them.
   That is composition through shared layers, which is the sanctioned form.
3. **`bench/` never names its parent's implementation.** It depends on `ports.HealLoop`,
   which `Healer` satisfies structurally, so the benchmark composes with the loop without
   knowing that `healer.py` exists. This is the concrete form of "children never
   reference parents".
4. **Absolute imports only** — `from bdheal.models import RunResult`. No relative imports.
5. **Ports are `Protocol`, not `ABC`.** Structural typing: an adapter satisfies a port by
   having the methods. The app may substitute its own `HealStore` without inheriting
   anything of ours.
6. **One port per boundary**, with the reason recorded in its docstring. Do not split
   `HealStore` into three stores because it stores three things; there is one backing
   store and one reason to change.

## 5. The ports (`ports.py`)

Signatures are frozen here. A feature that needs a different signature changes it here
first, and updates every stub in `tests/conftest.py` in the same pass.

```python
class StudioClient(Protocol):
    def create(self, url: str, description: str) -> str: ...
    def run(self, spec: CollectorSpec, urls: Sequence[str]) -> RunResult: ...
    def heal(self, spec: CollectorSpec, prompt: str, *, auto_approve: bool = False) -> HealEvent: ...
    def approve(self, spec: CollectorSpec, url: str, *, reject: bool = False) -> HealEvent: ...
    def fetch_html(self, url: str) -> str: ...

class HealStore(Protocol):
    def save_baseline(self, baseline: Baseline) -> None: ...
    def baseline(self, collector_id: str) -> Baseline | None: ...
    def save_heal_event(self, event: HealEvent) -> HealEvent: ...
    def heal_events(self, collector_id: str) -> list[HealEvent]: ...
    def save_bench_case(self, case: BenchCase) -> None: ...
    def completed_case_ids(self, run_id: str) -> list[str]: ...

class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...

class CommandRunner(Protocol):
    def __call__(self, argv: list[str], timeout_s: int) -> ProcessResult: ...

class HealLoop(Protocol):        # what Healer is, from the benchmark's point of view
    def run(...) -> RunResult: ...
    def detect(...) -> DetectVerdict: ...
    def heal(...) -> HealEvent: ...
    def verify(...) -> VerifyReport: ...
```

Notes that are decisions, not commentary:

- **`fetch_html` exists because the skeleton signal needs page HTML and the package owns
  no HTTP client** (G4). It is served by `bdata scrape` (Web Unlocker), keeping `bdata`
  the single outward call. `detect()` takes `page_html` as a parameter, so detect itself
  stays port-free apart from `HealStore` (F6(e)).
- **`CommandRunner` is where argv meets the operating system.** argv is a `list[str]`,
  always; there is no shell anywhere in the package (G3). `test_no_call_passes_shell`
  keeps it that way.
- **`Clock` is one port with two readings.** `now()` timestamps records, `monotonic()`
  measures durations. Splitting them lets a test freeze one and not the other, which is
  how a deterministic timing assertion stops being deterministic.
- **Benchmark resume state rides on `HealStore`** rather than a third port, because
  `GOAL.md` fixes the package at two injected ports and a resume reads baselines, events
  and case state together.

## 6. Data model

**The rule: a type that crosses a boundary is a Pydantic model in `models.py`. A type
that never leaves the module computing it is a `@dataclass(frozen=True, slots=True)` in
that module.** Pydantic at the boundary because the caller's `row_schema` failing
validation *is* a detect signal and must produce structured per-field errors; dataclasses
inside because that is the house style and validation there would be ceremony.

Entities in `models.py` (F2 adds the validators; the fields are already contract):

| Model | Carries | Notes |
|---|---|---|
| `CollectorSpec` | `collector_id`, `name`, `anchor_urls`, `row_schema: type[BaseModel]` | The caller's whole input |
| `RowError` | `index`, `message`, `error_code`, `field_errors` | Target-side *and* schema-side failure, one shape |
| `RunResult` | `collector_id`, `fetched_at`, `rows`, `errors`, `error_codes` | `error_codes` is a list, never `None` |
| `Signal` | `kind`, `outcome`, `detail` | One detector's reading |
| `DetectVerdict` | `broken`, `signals`, `incomplete`, `retry_requested`, `reason` | `incomplete` covers every target-side refusal, not only throttling |
| `HealEvent` | `collector_id`, `status`, `created_at`, `prompt`, `preview_result`, `promoted`, `failure_class`, `template_id`, `attempts`, `error`, `id` | |
| `VerifyReport` | `field_accuracy`, `non_regression_passed`, `attempts`, `elapsed_s` | |
| `Baseline` | `collector_id`, `captured_at`, `row_count`, `null_rates`, `skeleton_hash` | Crosses `HealStore`, so it is Pydantic |
| `BenchCase` | run/case ids, `mutation`, `expected_signals`, `caught_by`, outcome fields | Crosses `HealStore` |

`RunResult.rows` is `list[dict[str, Any]]`: validated, normalised row *data*, not
`row_schema` instances. F2 requires `RunResult` to round-trip through `model_dump()`,
and the rows are persisted and compared; a caller wanting instances re-validates with
its own schema, which costs one line and buys serialisability.

`__all__` is exactly ten names — `Baseline`, `BenchCase`, `CollectorSpec`,
`DetectVerdict`, `HealEvent`, `Healer`, `RowError`, `RunResult`, `Signal`,
`VerifyReport` — plus `__version__`, which is a dunder and not listed. `Baseline` and
`BenchCase` are exported because they cross the `HealStore` port, and §4 rule 5 invites
an application to supply its own implementation: a port whose vocabulary is only
reachable via `bdheal.models` is a half-public contract (decided 2026-08-19). Enums stay out: they are `StrEnum`, so
`event.status == "done"` works without importing anything.

Every boundary model sets `extra="forbid"` via a shared `_Boundary` base: a mistyped
field name silently becoming an ignored extra is precisely the bug class the
schema-validation detect signal exists to catch. Models are **not** frozen —
`model_copy(update=...)` is the store's update idiom (decided 2026-08-19).

Closed vocabularies live in `vocabulary.py`: `SignalKind` (`schema · zero_rows ·
skeleton · null_rate`), `SignalOutcome` (`fired · inconclusive`), `FailureClass`,
`HealStatus` (`awaiting_approval · done · rejected · failed`), `MutationClass`,
`MutationClass`. Benchmark vocabulary lives there too, because `BenchCase` crosses the
persistence boundary and its values must be nameable from the innermost layer.

### Incomplete samples (resolved decision Q3, widened by F6(h) on 2026-08-19)

`error_code` is data, never an exception. **Any row carrying an `error_code` at all** —
not merely `rate_limit`, but `blocked`, `captcha`, `timeout` or anything else the target
returns — makes the sample incomplete, so `zero_rows` and `null_rate` record
`SignalOutcome.INCONCLUSIVE` and `retry_requested` is set. A schema failure on a row that
*did* return is still valid break evidence. Such a run therefore never heals on volume
grounds, may still report a schema break, and always asks for a retry.

The narrow `rate_limit`-only reading was a **live false negative**, found in F6
verification: five of ten rows returning `error_code="blocked"` produced `broken=False`,
`signals={}` and no retry — total silence on a half-broken run. Do not reintroduce it.

The governing principle, which F7 onward also follows: **extraction problems justify a
heal; target-side problems justify a retry; neither justifies silence.** The
discriminator is one line — an error carrying an `error_code` is target-side; an error
carrying none is an extraction fault (which is also why a row that is not an object at
all fires the schema signal).

## 7. Persisted schema (`src/bdheal/schema.sql`)

Three tables: `bdheal_baselines`, `bdheal_heal_events`, `bdheal_bench_cases`. Shipped
inside the package and applied by `store.connect()`, loaded through
`importlib.resources` — never a path walked up from `__file__`, so a wheel behaves like
a checkout.

Two deliberate choices:

- **Every table is prefixed `bdheal_`.** The app's own `api/src/preward/adapters/sqlite/schema.sql`
  already owns a `heal_events` table of a different shape. The prefix lets both live in
  one SQLite file without either owning the other's DDL.
- **No foreign keys to application tables.** `bdheal` does not own collectors; it is told
  about them. A `REFERENCES collectors(id)` would make the package unusable standalone.

All SQL binds its parameters. Collector ids are caller-supplied strings and are treated
as hostile input.

## 8. Reuse registry

Extend these. Do not clone a near-copy beside them. If what you need is *almost* here,
change what is here.

| Component | Where | Use it for |
|---|---|---|
| `CollectorSpec`, `RunResult`, `RowError`, `DetectVerdict`, `Signal`, `HealEvent`, `VerifyReport`, `Baseline`, `BenchCase` | `models.py` | Every boundary type. Adding a boundary type means editing this file |
| `NonBlankStr`, `Ratio` | `models.py` | Field constraints shared across models: a caller-supplied name, and a `0.0..1.0` fraction. A new field of either kind annotates with these rather than re-spelling `Field(ge=…)` |
| `SignalKind`, `SignalOutcome`, `FailureClass`, `HealStatus`, `MutationClass` | `vocabulary.py` | Any closed set of values. No bare string literals for states |
| `BdhealError`, `StudioError`, `StudioResponseError`, `CollectorCreateError` | `errors.py` | Every raise. New error types subclass `BdhealError` |
| `skeleton()`, `skeleton_hash()` | `skeleton.py` | Any structural comparison — detect and bench both consume it |
| `null_rates()`, `capture_baseline()` | `detect.py` | Baseline maths, in one place, used by both detect and the facade |
| `TEMPLATE_IDS`, `Diagnosis` | `diagnose.py` | Prompt selection. A new failure class adds a row here |
| `heal()`, `approve()`, `PROMOTED_STATUS` | `heal.py` | The approval gate. A new terminal outcome, or a wider definition of "promoted", changes this file — not the CLI adapter |
| `BDATA_ARGV`, `DEFAULT_TIMEOUT_S`, `BATCH_TIMEOUT_S` | `studio.py` | Every `bdata` invocation. No feature re-spells the npx prefix |
| `connect()`, `SqliteHealStore` | `store.py` | Persistence. `schema.sql` is the single DDL source |
| `SystemClock` | `clock.py` | The only `datetime.now` in the package |
| `SubprocessRunner` | `process.py` | The only `subprocess.run` in the package |
| `Mutation`, `MUTATIONS` | `bench/mutate.py` | The generator registry. A tenth mutation appends here |
| `Metrics`, `CoverageRow` | `bench/metrics.py` | Benchmark aggregation |
| `StubStudioClient`, `InMemoryHealStore`, `FixedClock`, `RecordingRunner`, `ForbiddenRunner`, `SampleRow`, fixtures `studio` `store` `clock` `spec` | `tests/conftest.py` | Every test. Programme the stub you were given; do not write a second one |

## 9. Feature isolation

- A feature is a module plus its test file. It depends on the shared spine
  (`models`, `vocabulary`, `errors`, `skeleton`, `ports`) and on nothing else at its own
  layer unless the dependency order in `GOAL.md` names it (`heal.py` may use
  `diagnose.Diagnosis`; `healer.py` composes all of them — that is its job).
- Features compose **through** the shared layers, never by reaching into each other's
  internals. Nothing imports a name prefixed `_` from another module.
- Deleting one feature's module must break only its call sites and its own test file.
- `bench/` is a second use case over the same entities, not a layer. It reaches the loop
  through `HealLoop` and reaches persistence through `HealStore`.

## 10. Conventions

- **Files are named by role, not type.** `studio.py` is the Bright Data boundary;
  `store.py` is persistence. There is no `utils.py`, no `helpers.py`, no `base.py`.
- **Module docstrings state *why* the module exists**, not what its functions are called.
  Public functions and classes get a one-line docstring. Comments explain non-obvious
  *why* and nothing else.
- **Named constants, never magic values.** `RATE_LIMIT_CODE`, `BATCH_TIMEOUT_S`,
  `DEFAULT_TIMEOUT_S`, `TEMPLATE_IDS` already exist; add to them.
- **Errors are explicit and typed.** No bare `except`. No silent swallow. A `bdata`
  failure raises a `StudioError` subclass whose message says what to do about it —
  including naming the orphaned collector a failed `create` leaves behind.
- **Logging**: `structlog.get_logger(__name__)` in the module that logs. The package
  **never configures logging** — configuration belongs to the application. No log line,
  exception message, heal prompt or persisted row may contain an API key, token, or raw
  argv (G6). `BRIGHTDATA_API_KEY` reaches `bdata` through the environment and is never
  read, echoed, or interpolated by this package.
- **Cognitive complexity ≤ 15 per function.** Single responsibility per function.

## 11. Test strategy

Decided once, here. Developers write their feature's tests test-first against these
conventions; the Tester runs the whole suite.

**Framework**: `pytest` + `pytest-cov`. Nothing else — no mock library, no HTTP recorder.
If a test needs a fake, it programmes a stub from `conftest.py`.

**Location and naming**: `packages/bdheal/tests/`, flat. One file per module under test,
named `test_<module>.py` (`test_detect.py`, `test_bench_mutate.py` for `bench/mutate.py`).
Test functions are `test_<what_is_true>` and read as a sentence.

**The whole suite, one command, from the repo root:**

```bash
uv run --package bdheal pytest packages/bdheal
```

It must exit 0 with **no corpus, no database file, no application and no network** (G1).
This is the isolation test and it is the architecture's proof, not a convenience.

**Unit vs integration, for this package:**

- **Unit** — a pure function against literal inputs: `skeleton.py`, `bench/mutate.py`,
  `bench/metrics.py`, `verify.field_accuracy`, `diagnose`. Deterministic output means
  exact-match golden assertions, including a hash asserted against a literal constant.
- **Integration** — two or more units across a port, with the port stubbed:
  `detect` + `HealStore`, `heal` + `StudioClient` + `HealStore`, the full `Healer` loop,
  the benchmark runner. Still no network, still no file except `tmp_path`.
- The one adapter that touches a real resource is `SqliteHealStore`, tested against a
  `tmp_path` file. Never a path outside `tmp_path`.

**How offline works.** `tests/conftest.py` owns the stubs; every fixture is typed as the
**port**, not the concrete adapter, so a test cannot accidentally bind to an
implementation detail:

| Stub | Stands in for | Behaviour |
|---|---|---|
| `StubStudioClient` | `StudioClient` | Queued canned responses; records every call in `calls` and every URL in `urls_run` |
| `InMemoryHealStore` | `HealStore` | Dictionaries. No file, no schema |
| `FixedClock` | `Clock` | Frozen; `advance(seconds)` makes elapsed times exact values |
| `RecordingRunner` | `CommandRunner` | Captures argv and timeouts, replays queued `ProcessResult`s. This is how argv-injection and `--timeout` assertions are made without `npx` |
| `ForbiddenRunner` | `CommandRunner` | Raises `AssertionError` on any call — drop it in to prove a code path never leaves the process |
| `SampleRow` | the caller's `row_schema` | Deliberately generic; a test that needs domain vocabulary has already failed |

**The gated tests.** Anything that needs the network is marked and skipped unless its
environment variable is set: `@pytest.mark.live` (`BDHEAL_LIVE=1`) for the real `bdata`
CLI, and `@pytest.mark.publish` (`BDHEAL_PUBLISH_CHECK=1`) for the clean-room build and
install that stands in for a lockfile the package deliberately does not have (Q5). One
`pytest_runtest_setup` hook in `conftest.py` reads the `NETWORK_GATES` map, so a third
gate is a row rather than another branch; the markers are declared in `pyproject.toml`
under `--strict-markers`, so a typo fails rather than silently running. Neither is part
of the isolation run — they are an operator's tools for confirming the CLI surface has
not moved and that the package still installs standalone.

**`tests/test_architecture.py` is a standing test, owned by nobody's feature.** It
enforces the layer map, the inward dependency rule, the four-dependency limit (G2 + G4),
and the absence of any `shell` argument (G3). If it fails, the fix is the code or this
document — not the test.

## 12. Mutation → declared detector (resolved decision Q2)

F11 populates `MUTATIONS` with exactly these declarations. F12 reports what actually
caught each class and publishes the disagreements as coverage gaps — a gap is a finding,
not a failure.

| Mutation class | Declared detectors (`frozenset[SignalKind]`) | Moves the skeleton hash? |
|---|---|---|
| `class_rename` | `skeleton` | yes |
| `table_to_div` | `skeleton` | yes |
| `column_reorder` | `skeleton` | yes |
| `field_split_merge` | `skeleton` | yes |
| `wrapper_nesting` | `skeleton` | yes |
| `pagination` | `skeleton` | yes |
| `date_format` | `schema` | no |
| `url_pattern` | `{schema, null_rate}` | no |
| `link_label` | `{}` (empty) | no — expected to evade all four detectors |

The three non-structural classes leaving the skeleton hash untouched is `skeleton.py`
behaving correctly, not a defect: its contract is text-insensitivity.

The declaration is a **set of `SignalKind`**, not an enumerated combination. A class two
detectors can see is `{schema, null_rate}`; one nothing catches is the **empty set**, an
honest published gap. `coverage` is then membership — `caught_by in expected_signals` —
rather than decoding names like `schema_or_null_rate` by hand, and a fifth detector adds
one enum member instead of multiplying combinations. Persisted as a sorted comma-joined
`TEXT` column, so `""` is a real, meaningful value.

## The argv flag guard — what it does and does not catch

`tests/test_studio.py` records, offline, the valid flag set per `bdata` subcommand
(`ALLOWED_FLAGS`) and the mutually-exclusive pairs (`EXCLUSIVE_FLAGS`), and asserts the
adapter never emits a flag a subcommand lacks nor an exclusive pair together. It exists
because the injected `CommandRunner` makes the suite blind to whether the real CLI would
accept what we send: three argv defects passed a green 91-test suite before it was added.

**Scope limit, verified by mutation test (2026-08-19):** the guard catches *wrong* and
*conflicting* flags. It cannot catch a **missing required** flag — deleting
`--format html` from `fetch_html` leaves the guard green, because absence is not a
violation. Only a dedicated value assertion catches that, and one exists
(`test_fetch_html_asks_for_html_and_gets_the_page_source`).

So: **every required flag needs its own point assertion.** Do not treat the guard as
covering required-flag regressions. This matters most where the CLI has a silent default
that is wrong for us — `bdata scrape` defaults to `--format markdown`, which would have
produced a meaningless skeleton hash with no error anywhere.

## 13. Underspecified in `GOAL.md`, decided here

Recorded so the next reader does not have to re-derive them.

1. **Where the skeleton signal's HTML comes from.** Nothing in the spec said; `bdheal`
   has no HTTP client. Decided: `StudioClient.fetch_html` via `bdata scrape`, and
   `detect(..., page_html=None)` skips the skeleton signal when no HTML is supplied.
2. **Where `Healer` lives.** The plan lists the class but not a module. Decided:
   `healer.py`, Use Cases.
3. **`ports.py` exists at all.** `GOAL.md` puts each port in the same file as its
   adapter, which cannot be assigned to exactly one layer — F0's own acceptance
   criterion. Decided: ports in `ports.py` (Use Cases), adapters in `studio.py` /
   `store.py` (Interface Adapters). F3 and F4 still deliver "port + adapter"; the port
   just lands one file over.
4. **Benchmark resume state.** Persisted through `HealStore`, since the package is fixed
   at two ports.
5. **`bench/runner.py` receives a `HealLoop`, not a `StudioClient` + `HealStore` pair.**
   F12(c)'s literal wording says the two ports; its intent is "the benchmark runs green
   with no network". Injecting a `HealLoop` built on stubbed ports satisfies the intent
   and avoids `bench/` importing its parent's implementation, which the project's
   isolation rule forbids.
6. **`RunResult.rows` are dicts, not `row_schema` instances** — see §6.
7. **Table prefixing.** `bdheal_*`, so the package's DDL cannot collide with the app's.
