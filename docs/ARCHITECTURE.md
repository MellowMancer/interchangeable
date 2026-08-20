# ARCHITECTURE — `bdheal`

The contract the package is built against, and the only document that constrains it. Where
this document and a module's own instinct disagree, this document wins.

It carries the invariants, resolved decisions and known gaps in full, so nothing here
depends on reading anything else. The one exception is the `bdata` CLI surface itself:
flags and subcommands are whatever the vendor ships, verified against `bdata --help`, and
this document never overrides them.

---

## 1. Invariants

Gates, not aspirations. Checked on every change, not only the one that introduces them.

| | Invariant |
|---|---|
| **G1** | **Isolation.** `uv run --package bdheal pytest packages/bdheal` exits 0 with no corpus, no database file, no app and no network. Both ports are stubbed at their interfaces in every test. A test that needs `ixq` means a layer boundary leaked. |
| **G2** | **No upward dependency.** `rg -n "ixq" packages/bdheal/` returns nothing in `src/` or `tests/`, and the manifest never names it. The app depends on `bdheal`; never the reverse. |
| **G3** | **argv is a list.** Every `bdata` invocation passes argv as `list[str]`; `shell=True` appears nowhere. Collector ids and heal prompts are interpolated values, so this is the injection boundary. |
| **G4** | **Thin dependencies.** Runtime deps are exactly `pydantic selectolax lxml`; dev deps exactly `pytest pytest-cov`. No `fastapi`, no `typer`, no `httpx`. (`structlog` was dropped as a declared dependency with no call sites.) |
| **G5** | **Buildable at every step.** `docker compose build api` exits 0 and the isolation test stays green after every change. |
| **G6** | **No secrets in output.** No API key, token or credential in any log line, exception message, heal prompt or persisted row. `BRIGHTDATA_API_KEY` reaches `bdata` through the environment and is never read, echoed or interpolated here. |

## 2. The one dependency arrow

```
ixq (the app)  ──depends on──▶  bdheal  ──▶  bdata CLI  ──▶  Bright Data
```

Never the reverse (G2). `bdheal` is a **sibling** of `api/`, not a child: a package buried
inside the application it serves is not independently publishable, whatever its manifest
says.

`bdheal` knows collector ids, Pydantic schemas, anchor URLs and HTML structure. It never
knows sources, records, documents or lexicons. **A term from any problem domain appearing
under `packages/bdheal/` is a defect.**

## 3. Workspace wiring

```
interchangeable/
├─ pyproject.toml          # virtual uv workspace root; members = api, packages/bdheal
├─ uv.lock                 # ONE lockfile for the workspace
├─ .dockerignore           # the api image builds from the repo root
├─ compose.yaml            # api: context ".", dockerfile "api/Dockerfile"
├─ packages/bdheal/
└─ api/                    # declares bdheal via [tool.uv.sources] workspace = true
```

The api image needs the workspace lockfile *and* `packages/bdheal`, so its build context is
the repo root.

## 4. Layer map

Every module belongs to exactly one layer. `tests/test_architecture.py` enforces this
table; adding a module without updating both fails the suite.

| Layer | Module | Role |
|---|---|---|
| **Entities** | `models.py` | Every type that crosses a boundary — Pydantic |
| | `vocabulary.py` | Closed vocabularies: signal kinds, outcomes, heal statuses, failure classes, mutation classes |
| | `errors.py` | The exception hierarchy |
| | `skeleton.py` | Structural fingerprint of a page — pure, deterministic |
| | `bench/mutate.py` | The nine perturbations and their declared detectors — pure |
| | `bench/metrics.py` | The five metrics and the coverage matrix — pure |
| **Use Cases** | `ports.py` | Every abstract seam |
| | `detect.py` | The four signals and the throttle policy |
| | `diagnose.py` | Failure class → template → rendered prompt |
| | `heal.py` | The heal/approve gate |
| | `verify.py` | Golden diff plus the non-regression pass |
| | `healer.py` | The `Healer` facade — the public entry point |
| | `bench/runner.py` | Drives cases through a `HealLoop`, persists resume state |
| **Interface Adapters** | `studio.py` | `BdataStudioClient`: argv shaping, JSON parsing, error-row mapping |
| | `store.py` | `SqliteHealStore` + `connect()`; ships `schema.sql` |
| **Frameworks & Drivers** | `clock.py` | `SystemClock` — the only place time is read |
| | `process.py` | `SubprocessRunner` — the only place a process starts |
| | `__init__.py` | Export surface |

Two carve-outs:

- **Pure-computation libraries may appear in Entities.** `pydantic`, `selectolax`, `lxml`
  and `hashlib` compute; they do not perform I/O. Anything that opens a socket, file,
  database or process may not appear in Entities or Use Cases — that is the line the
  Dependency Rule actually protects.
- **No composition root ships.** There is no `default_healer()` and no module-level client.
  The caller wires `Healer(studio, store, clock)`. A library that can reach the network
  without being handed the means to is not testable in isolation.

## 5. Dependency rules

1. **Inward only.** Import from your own layer or any layer inside it. Enforced by
   `test_dependencies_point_inward`.
2. **The shared spine is importable from anywhere** — `models`, `vocabulary`, `errors`,
   `skeleton`, `ports`. Composition through shared layers is the sanctioned form.
3. **`bench/` never names its parent's implementation.** It depends on `ports.HealLoop`,
   which `Healer` satisfies structurally, so the benchmark composes with the loop without
   knowing `healer.py` exists.
4. **Absolute imports only.** No relative imports.
5. **Ports are `Protocol`, not `ABC`.** An adapter satisfies a port by having the methods,
   so the app may substitute its own `HealStore` without inheriting anything of ours.
6. **One port per boundary**, reason recorded in its docstring. Do not split `HealStore`
   into three because it stores three things: one backing store, one reason to change.
7. Nothing imports a `_`-prefixed name from another module. Deleting one module must break
   only its call sites and its own test file.

## 6. The ports (`ports.py`)

Signatures are frozen here. A change happens here first, updating every stub in
`tests/conftest.py` in the same pass.

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
    def bench_cases(self, run_id: str) -> list[BenchCase]: ...

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

Decisions, not commentary:

- **`fetch_html` exists because the skeleton signal needs page HTML and the package owns no
  HTTP client** (G4). Served by `bdata scrape`, keeping `bdata` the single outward call.
  `detect()` takes `page_html` as a parameter, so it stays port-free apart from `HealStore`.
- **`CommandRunner` is where argv meets the OS.** Always `list[str]`, no shell (G3).
- **`Clock` is one port with two readings** — `now()` timestamps, `monotonic()` measures.
  One port, so a test cannot freeze one and not the other.
- **Benchmark resume state rides on `HealStore`** rather than a third port. `bench_cases`
  exists because `completed_case_ids` returns ids only: a resumed run could skip finished
  cases but not read them back, leaving pre-crash rows write-only.

## 7. Data model

**A type that crosses a boundary is a Pydantic model in `models.py`. A type that never
leaves the module computing it is a `@dataclass(frozen=True, slots=True)` there.** Pydantic
at the boundary because the caller's `row_schema` failing validation *is* a detect signal
and must produce structured per-field errors.

| Model | Carries | Notes |
|---|---|---|
| `CollectorSpec` | `collector_id`, `name`, `anchor_urls`, `row_schema: type[BaseModel]` | The caller's whole input |
| `RowError` | `index`, `message`, `error_code`, `field_errors` | Target-side *and* schema-side failure, one shape |
| `RunResult` | `collector_id`, `fetched_at`, `rows`, `errors`, `error_codes` | `error_codes` is a list, never `None` |
| `Signal` | `kind`, `outcome`, `detail` | One detector's reading |
| `DetectVerdict` | `broken`, `signals`, `incomplete`, `retry_requested`, `reason` | `incomplete` covers every target-side refusal, not only throttling |
| `HealEvent` | ids, `status`, `created_at`, `prompt`, `preview_result`, `promoted`, `failure_class`, `template_id`, `attempts`, `error` | |
| `VerifyReport` | `field_accuracy`, `non_regression_passed`, `attempts`, `elapsed_s` | |
| `Baseline` | `collector_id`, `captured_at`, `row_count`, `null_rates`, `skeleton_hash` | Crosses `HealStore`, so Pydantic |
| `BenchCase` | run/case ids, `mutation`, `expected_signals`, `caught_by`, outcome fields | Crosses `HealStore` |

- `RunResult.rows` is `list[dict[str, Any]]` — validated row *data*, not `row_schema`
  instances, so `RunResult` round-trips through `model_dump()`. A caller wanting instances
  re-validates in one line and buys serialisability.
- `__all__` is exactly ten names. `Baseline` and `BenchCase` are exported because they
  cross `HealStore` and rule 5 invites the app to supply its own implementation; a port
  whose vocabulary is only reachable via `bdheal.models` is a half-public contract. Enums
  stay out — they are `StrEnum`, so `event.status == "done"` works unimported.
- Every boundary model sets `extra="forbid"` via a shared `_Boundary` base: a mistyped field
  silently becoming an ignored extra is exactly the bug the schema signal exists to catch.
  Models are **not** frozen — `model_copy(update=...)` is the store's update idiom.
- Closed vocabularies live in `vocabulary.py`, including benchmark vocabulary, because
  `BenchCase` crosses persistence and its values must be nameable from the innermost layer.

## 8. Detect semantics

**The governing principle: extraction problems justify a heal; target-side problems justify
a retry; neither justifies silence.**

The discriminator is one line — an error carrying an `error_code` is target-side; an error
carrying none is an extraction fault. A row that is not an object at all fires the schema
signal: a collector that returned objects and now returns strings is broken.

**Incomplete samples.** `error_code` is data, never an exception. **Any** row carrying a
target-side or ambiguous code — `rate_limit`, `blocked`, `captcha`, `timeout`,
`dead_page`, `crawl_error`, `ajax_request_error` — makes the sample incomplete, so
`row_count` and `null_rate` record `SignalOutcome.INCONCLUSIVE` and `retry_requested` is
set. Codes the vendor attributes to the scraper (`parse_error`, `bad_input`,
`wait_element_timeout`) are extraction evidence and do fire the schema signal.

Such a run never heals on volume grounds, may still report a schema break, and always asks
for a retry.

> The narrow `rate_limit`-only reading was a **live false negative**: five of ten rows
> returning `blocked` produced `broken=False`, `signals={}` and no retry — total silence on
> a half-broken run. Do not reintroduce it.

**Ambiguous codes are reported, not judged.** A single run cannot tell a dead page from a
collector resolving relative links against the site root — a real payload produced 980
`dead_page` rows from exactly that bug. So `detect` stays stateless: ambiguous codes land in
`DetectVerdict.ambiguous_codes` and request a retry. **The escalation belongs to the
facade**: retry once, and if the *same* ambiguous codes return they are no longer plausibly
transient and become extraction evidence. One wasted retry is the cheap direction to be
wrong in.

**Thresholds and precedence.**

- `NULL_RATE_SPIKE = 0.5` — absolute rise above baseline.
- Signal precedence, pinned by test: **`skeleton > schema > row_count > null_rate`**. A
  moved tag-and-class tree is *why* the others fired; naming a symptom would send the heal
  hunting for a field on a page whose rows it can no longer find.
- **First run with no baseline returns `broken=False`.** Nothing to compare against is not
  evidence of breakage.
- **`diagnose` never consults `incomplete`.** `FIRED` is the only input to classification:
  `detect` already suppresses the volume detectors whenever any row is target-side, so a
  signal surviving to `FIRED` inside an incomplete sample is extraction evidence by
  construction. Suppressing on `incomplete` alone would delete a real schema break whenever
  one sibling row was blocked.

## 9. The heal → verify → promote contract

Obligations the facade and the benchmark must honour. Each was found by verification, not
designed up front.

**A gate cycle is not one row.** A gated heal emits **two** events (`awaiting_approval`,
then the terminal outcome); auto-approve and a failed call emit one. Anything counting rows
per cycle must select the **terminal-most** row, never treat row count as cycle count.

**A failed gate call raises; it does not return a `failed` event.** `heal.heal` and
`heal.approve` write the row and re-raise `StudioError`. That is asymmetric with the
value-based `VerifyReport.non_regression_passed=False`, so the caller cannot branch on
`event.status` for this failure mode.

**Three branches, and they are not interchangeable:**

| Condition | Outcome |
|---|---|
| `except StudioError` | not promoted |
| `except VerificationIncompleteError` | **retry** — never rollback |
| `VerifyReport` is `False` | roll back |

Rolling back on `VerificationIncompleteError` would discard a heal that was never actually
tested, and feed the benchmark a fabricated non-regression failure.

**Two promotion floors**, both of which must appear in any published methodology or the
numbers are not reproducible:

- `NON_REGRESSION_FLOOR = 1.0` — the old layout must still yield *every* golden field. A
  lower floor lets a heal drop one field in ten and still publish as non-regressive.
- `field_accuracy > 0` — a no-op heal extracting nothing regresses nothing, and would
  otherwise score perfectly on the old layout and promote.

## 10. Persisted schema (`src/bdheal/schema.sql`)

Three tables — `bdheal_baselines`, `bdheal_heal_events`, `bdheal_bench_cases` — shipped
inside the package and applied by `store.connect()`, loaded through `importlib.resources`
so a wheel behaves like a checkout.

- **Every table is prefixed `bdheal_`.** The app already owns a `heal_events` table of a
  different shape; the prefix lets both share one SQLite file without either owning the
  other's DDL.
- **No foreign keys to application tables.** `bdheal` does not own collectors; it is told
  about them. A `REFERENCES collectors(id)` would make the package unusable standalone.
- All SQL binds its parameters. Collector ids are caller-supplied and treated as hostile.

## 11. Reuse registry

Extend these. Do not clone a near-copy beside them.

| Component | Where | Use it for |
|---|---|---|
| The nine boundary models | `models.py` | Every boundary type |
| `NonBlankStr`, `Ratio` | `models.py` | Shared field constraints — annotate rather than re-spelling `Field(ge=…)` |
| `SignalKind`, `SignalOutcome`, `FailureClass`, `HealStatus`, `MutationClass` | `vocabulary.py` | Any closed set. No bare string literals for states |
| `BdhealError` and subclasses | `errors.py` | Every raise |
| `skeleton()`, `skeleton_hash()` | `skeleton.py` | Any structural comparison |
| `null_rates()`, `capture_baseline()` | `detect.py` | Baseline maths, used by detect and the facade |
| `TEMPLATE_IDS`, `Diagnosis` | `diagnose.py` | Prompt selection. A new failure class adds a row |
| `heal()`, `approve()`, `PROMOTED_STATUS` | `heal.py` | The approval gate |
| `BDATA_ARGV`, `DEFAULT_TIMEOUT_S`, `BATCH_TIMEOUT_S` | `studio.py` | Every `bdata` invocation |
| `connect()`, `SqliteHealStore` | `store.py` | Persistence; `schema.sql` is the single DDL source |
| `SystemClock` / `SubprocessRunner` | `clock.py` / `process.py` | The only `datetime.now` / `subprocess.run` |
| `Mutation`, `MUTATIONS` | `bench/mutate.py` | The generator registry |
| `Metrics`, `CoverageRow` | `bench/metrics.py` | Benchmark aggregation |
| Stubs and fixtures | `tests/conftest.py` | Every test. Programme the stub you were given |

## 12. Conventions

Project-wide coding rules are not repeated here. Package-specific:

- **Files are named by role, not type.** No `utils.py`, `helpers.py` or `base.py`.
- **Module docstrings state *why* the module exists.** Comments explain non-obvious *why*
  and nothing else.
- **Errors are explicit and typed.** No bare `except`, no silent swallow. A `bdata` failure
  raises a `StudioError` subclass whose message says what to do about it — including naming
  the orphaned collector a failed `create` leaves behind.
- **The package never configures logging.** Configuration belongs to the application.

## 13. Test strategy

**Framework:** `pytest` + `pytest-cov`. Nothing else — no mock library, no HTTP recorder. A
test needing a fake programmes a stub from `conftest.py`.

**Layout:** `packages/bdheal/tests/`, flat, one file per module under test. Test functions
are `test_<what_is_true>` and read as a sentence.

**The suite, one command from the repo root:**

```bash
uv run --package bdheal pytest packages/bdheal
```

It must exit 0 with no corpus, no database, no app and no network (G1). This is the
architecture's proof, not a convenience.

**Unit** is a pure function against literal inputs, asserted against exact goldens including
a hash pinned to a literal. **Integration** is two or more units across a stubbed port. The
one adapter touching a real resource is `SqliteHealStore`, tested against `tmp_path` and
never outside it.

Every fixture is typed as the **port**, not the adapter, so a test cannot bind to an
implementation detail:

| Stub | Stands in for | Behaviour |
|---|---|---|
| `StubStudioClient` | `StudioClient` | Queued canned responses; records calls and URLs |
| `InMemoryHealStore` | `HealStore` | Dictionaries. No file, no schema |
| `FixedClock` | `Clock` | Frozen; `advance(seconds)` makes elapsed times exact |
| `RecordingRunner` | `CommandRunner` | Captures argv and timeouts, replays queued results — how argv-injection and `--timeout` assertions happen without `npx` |
| `ForbiddenRunner` | `CommandRunner` | Raises on any call — proves a path never leaves the process |
| `SampleRow` | the caller's `row_schema` | Deliberately generic; a test needing domain vocabulary has already failed |

**Gated tests** are marked and skipped unless their environment variable is set:
`@pytest.mark.live` (`BDHEAL_LIVE=1`) for the real CLI, `@pytest.mark.publish`
(`BDHEAL_PUBLISH_CHECK=1`) for the clean-room build and install that stands in for the
lockfile the package deliberately does not carry. One `pytest_runtest_setup` hook reads the
`NETWORK_GATES` map, so a third gate is a row rather than a branch; markers are declared
under `--strict-markers`, so a typo fails rather than silently running.

**`tests/test_architecture.py` is a standing test owned by nobody's feature.** It enforces
the layer map, the inward rule, the dependency limit (G2 + G4) and the absence of any
`shell` argument (G3). If it fails, the fix is the code or this document — not the test.

### The argv flag guard — and what it cannot catch

`tests/test_studio.py` records the valid flag set per subcommand (`ALLOWED_FLAGS`) and the
mutually-exclusive pairs, asserting the adapter never emits a flag a subcommand lacks nor an
exclusive pair together. It exists because the injected `CommandRunner` makes the suite
blind to whether the real CLI would accept what we send: three argv defects passed a green
91-test suite before it was added.

**Scope limit, verified by mutation test:** it catches *wrong* and *conflicting* flags. It
**cannot catch a missing required flag** — deleting `--format html` from `fetch_html` leaves
it green, because absence is not a violation. **Every required flag needs its own point
assertion.** This matters most where the CLI has a silent default that is wrong for us:
`bdata scrape` defaults to `--format markdown`, which would produce a meaningless skeleton
hash with no error anywhere.

## 14. Benchmark

`MUTATIONS` carries these declarations; the runner reports what actually caught each class
and publishes disagreements as coverage gaps. **A gap is a finding, not a failure.**

| Mutation class | Declared detectors | Moves the skeleton hash? |
|---|---|---|
| `class_rename` · `table_to_div` · `column_reorder` · `field_split_merge` · `wrapper_nesting` · `pagination` | `{skeleton}` | yes |
| `date_format` | `{schema}` | no |
| `url_pattern` | `{schema, null_rate}` | no |
| `link_label` | `{}` — expected to evade all four detectors | no |

The three non-structural classes leaving the hash untouched is `skeleton.py` behaving
correctly: its contract is text-insensitivity. The declaration is a **set**, so a class
nothing catches is the empty set — an honest published gap — and `coverage` is membership
rather than decoding names by hand.

**⚠️ Collectors must be scoped to a single page.** A naive `create` against a listing URL
produces a site crawler, not a page extractor: one probe walked an entire catalogue for
1.05K page fulfillments and 999 failed crawls to yield a single record. Every `create`
description states *this page only, follow no links, no pagination*, and fixtures are
self-contained pages with nowhere to crawl to.

**⚠️ Two parsers are in play.** `skeleton.py` hashes with `selectolax`; `bench/mutate.py`
generates with `lxml`. All nine classes agree today, verified independently — but a
divergence in malformed-HTML tolerance would corrupt the coverage matrix. If a case ever
reports an unexpected detector, check parser disagreement before suspecting the detector.

**⚠️ `column_reorder` must reorder siblings differing in tag or class.** Swapping two
byte-identical siblings cannot move a structural hash, because the structure genuinely did
not change — a uniform-cell fixture would fail the criterion for a correct implementation.

**One golden set cannot score two layouts.** `verify` scores both the healed and old-layout
passes against one golden set — right for the six structural classes, wrong for
`date_format`, `url_pattern` and `link_label`, whose mutations change the page text.
**Resolved: exclude those three from the non-regression rate and disclose it** in a note
travelling on every `Metrics` value, because a limit disclosed only in documentation is not
disclosed to whoever reads the number. Incomplete verifications are excluded too, not
counted as failures.

**What the runner must honour:**

- Build each case's spec with `anchor_urls=[fixture_url]`. A `RunResult` does not carry its
  source URLs, so the ambiguous-code retry re-runs `spec.anchor_urls` — if those differ from
  the fixture, the retry silently checks a *different page*.
- `caught_by` is `None` for an escalated case: the loop's retry caught it, not a detector,
  and fabricating a signal would tell the matrix otherwise. Do not read it as a gap unqualified.
- Attempts-to-heal counts loop passes, not heal calls. `VerifyReport.attempts` counts
  verification passes inside one `verify()` call.

## 15. Resolved decisions

Recorded so nobody re-derives them.

1. **Workspace root.** Root `pyproject.toml` with members `api` and `packages/bdheal`, one
   lockfile at `/uv.lock`, api image built from the repo root.
2. **Coverage matrix over hash coverage.** Non-structural mutations are declared against the
   detectors that should catch them and the disagreements are published, rather than
   stretching the skeleton hash to cover text changes.
3. **Partial throttle suppresses volume signals only** — widened later to every target-side
   code (§8).
4. **Hosted and unattended pieces are out of scope** for this build.
5. **`bdheal` carries no lockfile.** A library pinning its own transitive tree is hostile to
   the applications embedding it; installability is proved instead by the gated
   clean-room build-and-install check.
6. **Where the skeleton signal's HTML comes from.** `StudioClient.fetch_html` via
   `bdata scrape`; `detect(..., page_html=None)` skips the skeleton signal.
7. **`Healer` lives in `healer.py`**, Use Cases.
8. **`ports.py` exists at all.** Putting each port beside its adapter yields a file that
   cannot be assigned to one layer. Ports live in `ports.py` (Use Cases), adapters in
   `studio.py` / `store.py` (Interface Adapters).
9. **`bench/runner.py` receives a `HealLoop`**, not a `StudioClient` + `HealStore` pair —
   satisfying "runs green with no network" without `bench/` importing its parent.
   A signature-comparison test guards `Healer` and `HealLoop` against drift.
10. **Licence: MIT.** `LICENSE` at the repo root and a bundled copy in the package; the
    wheel carries `License-Expression: MIT`.

## 16. Known gaps

Real, recorded, none blocking. Say these out loud rather than letting a reader discover them.

- **The redaction net in `studio.py` catches only what it can name.** Unlabelled tokens slip
  through if they are base64 containing `+` or `/`, are a single character class, or fall
  under `MIN_OPAQUE_CHARS`. This is residue behind four label-based patterns, and both named
  threat channels — `npx` echoing argv, `bdata` relaying auth errors — are covered by a
  labelled one. The 24-character floor trades against redacting collector ids.
- **`preview_result` is the one subprocess-authored field persisted unredacted.** It holds
  sample rows rather than auth material, so likelihood is low — but revisit it if the loop
  ever previews a page behind authentication.
- **`mean_attempts_to_heal` publishes `1.0` by construction** — one loop pass per case, one
  heal per pass. Real and tested, but carries no information until the runner has a retry
  budget. Say so when publishing it.
- **A target-side code with no baseline yields `signals == []`** while `incomplete`,
  `retry_requested` and `reason` still speak. Consistent with "no baseline means no detector
  ran", but it deserves a regression test next time `detect.py` is touched.

## Working constraint

**No git commits without the user's explicit permission.** No agent working this repository
runs `git commit`, `git add`, or any other git write command. Work stays in the working tree
for the user to review.
