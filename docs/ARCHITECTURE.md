# ARCHITECTURE — `bdheal`

This is the contract for the package, and the only document that constrains it. If this
document and the design of a module disagree, obey this document.

This document contains the invariants, the resolved decisions and the known gaps in full.
Therefore no other document is necessary. There is one exception: the `bdata` CLI
surface. The flags and the subcommands are those that the vendor supplies, verified against
`bdata --help`. This document never supersedes them.

---

## 1. Invariants

These are gates and not objectives. Check them at each change, and not only at the change
that adds them.

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

The reverse direction is prohibited (G2). `bdheal` is a **sibling** of `api/` and not a
child. A package inside the application that it serves cannot be published independently,
whatever its manifest says.

`bdheal` knows collector ids, Pydantic schemas, anchor URLs and HTML structure. It never
knows sources, records, documents or lexicons. **A term from a problem domain in
`packages/bdheal/` is a defect.**

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

The api image needs the workspace lockfile *and* `packages/bdheal`. Therefore its build
context is the root of the repository.

## 4. Layer map

Each module is in one layer only. `tests/test_architecture.py` enforces this table. A new
module that is not in the table makes the suite fail.

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

There are two exceptions to the table:

- **A pure-computation library can be in Entities.** `pydantic`, `selectolax`, `lxml` and
  `hashlib` compute. They do no I/O. A component that opens a socket, a file, a database or
  a process must not be in Entities or in Use Cases. That is the line that the Dependency
  Rule protects.
- **The package supplies no composition root.** There is no `default_healer()` and no
  client at module level. The caller makes `Healer(studio, store, clock)`. A library that
  can connect to the network without the caller supplying the means cannot be tested in
  isolation.

## 5. Dependency rules

1. **Import inward only.** Import from the module's own layer, or from a layer inside it.
   `test_dependencies_point_inward` enforces this.
2. **Each layer can import the shared spine** — `models`, `vocabulary`, `errors`,
   `skeleton`, `ports`. Composition through a shared layer is the permitted form.
3. **`bench/` never names the implementation of its parent.** It depends on
   `ports.HealLoop`. `Healer` satisfies `HealLoop` structurally. Therefore the benchmark
   composes with the loop and does not know that `healer.py` exists.
4. **Use absolute imports only.** Do not use a relative import.
5. **A port is a `Protocol` and not an `ABC`.** An adapter satisfies a port when it has the
   methods. Therefore the app can substitute its own `HealStore` and inherit nothing from
   this package.
6. **Use one port for each boundary.** Record the reason in the docstring of the port. Do
   not divide `HealStore` into three ports because it stores three things: it is one
   backing store and has one reason to change.
7. No module imports a name with a `_` prefix from a different module. A deleted module
   must break its call sites and its own test file only.

## 6. The ports (`ports.py`)

These signatures are frozen. To change one, change it here first, and correct each stub in
`tests/conftest.py` in the same operation.

```python
class StudioClient(Protocol):
    def create(self, url: str, description: str, name: str | None = None) -> str: ...
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
    def bench_runs(self) -> list[str]: ...

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

These are decisions and not commentary:

- **`fetch_html` exists because the skeleton signal needs the HTML of a page, and the
  package owns no HTTP client** (G4). `bdata scrape` supplies the HTML. Therefore `bdata`
  stays the one outward call. `detect()` takes `page_html` as a parameter. Therefore
  `detect()` uses no port other than `HealStore`.
- **`CommandRunner` is where argv goes to the OS.** Always use `list[str]`. Do not use a
  shell (G3).
- **`Clock` is one port with two readings.** `now()` makes a timestamp and `monotonic()`
  measures. It is one port. Therefore a test cannot freeze one reading and not the other.
- **The benchmark resume state uses `HealStore`** and not a third port. `bench_cases`
  exists because `completed_case_ids` returns ids only. Without `bench_cases`, a resumed
  run could omit the completed cases but could not read them, and the rows from before a
  crash would be write-only.

## 7. Data model

**A type that crosses a boundary is a Pydantic model in `models.py`. A type that stays in
the module that computes it is a `@dataclass(frozen=True, slots=True)` in that module.**
Use Pydantic at the boundary, because a `row_schema` from the caller that fails validation
*is* a detect signal, and it must give structured errors for each field.

| Model | Carries | Notes |
|---|---|---|
| `CollectorSpec` | `collector_id`, `name`, `anchor_urls`, `row_schema: type[BaseModel]`, `rows_key` | The caller's whole input. `rows_key` drives descent into the response envelope |
| `RowError` | `index`, `message`, `error_code`, `field_errors` | Target-side *and* schema-side failure, one shape |
| `RunResult` | `collector_id`, `fetched_at`, `rows`, `errors`, `error_codes` | `error_codes` is a list, never `None` |
| `Signal` | `kind`, `outcome`, `detail` | One detector's reading |
| `DetectVerdict` | `broken`, `signals`, `incomplete`, `retry_requested`, `reason`, `ambiguous_codes` | `incomplete` covers every target-side refusal, not only throttling |
| `HealEvent` | `id`, other ids, `status`, `created_at`, `prompt`, `preview_result`, `promoted`, `failure_class`, `template_id`, `attempts`, `error` | `preview_result` is `PreviewResult` — an object **or an array**. Bright Data returns an array when the preview carries several rows, and typing it as an object alone discarded a completed repair |
| `VerifyReport` | `field_accuracy`, `non_regression_passed`, `attempts`, `elapsed_s` | |
| `Baseline` | `collector_id`, `captured_at`, `row_count`, `null_rates`, `skeleton_hash` | Crosses `HealStore`, so Pydantic |
| `BenchCase` | run/case ids, `mutation`, `expected_signals`, `caught_by`, `fired_kinds`, outcome fields | Crosses `HealStore`. `fired_kinds` is what makes an unexpected signal visible rather than a pass |

- `RunResult.rows` is `list[dict[str, Any]]`. It contains validated row *data* and not
  instances of `row_schema`. Therefore `RunResult` round-trips through `model_dump()`. A
  caller that needs instances validates again in one line, and gets serialisability.
- **`rows` and `errors` are not two parts of one set.** If the schema rejects a row, the
  system keeps the row in `rows` with the incorrect fields set to null, *and* names the row
  in `errors`. If the system removed the row, it would hide the shape of the break from
  `null_rate`. `null_rate` is the signal that exists to see that shape: a field that stopped
  arriving. Code that treats the two lists as disjoint counts a row two times.
- `__all__` contains exactly ten names. `Baseline` and `BenchCase` are exported because
  they cross `HealStore`, and rule 5 permits the app to supply its own implementation. A
  port whose vocabulary is reachable only through `bdheal.models` is a contract that is
  half public. The enums are not exported. They are `StrEnum`, therefore
  `event.status == "done"` operates with no import.
- Each boundary model sets `extra="forbid"` through a shared `_Boundary` base. A field with
  an incorrect name that becomes an ignored extra is the defect that the schema signal
  exists to find. The models are **not** frozen. `model_copy(update=...)` is how the store
  updates a model.
- The closed vocabularies are in `vocabulary.py`. This includes the benchmark vocabulary,
  because `BenchCase` crosses persistence, and the innermost layer must be able to name its
  values.

## 8. Detect semantics

**The governing principle: an extraction problem justifies a heal. A target-side problem
justifies a retry. Neither justifies silence.**

The discriminator is **membership of a set, and not the presence of a code**. An error is
target-side when its `error_code` is in `UNTRUSTWORTHY_SAMPLE_CODES`. Each other error is an
extraction fault. A collector-fault code also has an `error_code`. Therefore "a code means
target-side" is false, and it causes the false negative that is recorded below. A row that
is not an object fires the schema signal: a collector that returned objects and now returns
strings is broken.

**Incomplete samples.** `error_code` is data. It is never an exception. **Any** row with a
target-side code or an ambiguous code makes the sample incomplete. Those codes are
`rate_limit`, `global_rate_limit`, `bucket_rate_limit`, `blocked`, `captcha_timeout`,
`timeout`, `dead_page`, `crawl_error`, `ajax_request_error` and `unspecified`. Therefore
`row_count` and `null_rate` record `SignalOutcome.INCONCLUSIVE`, and the system sets
`retry_requested`. The vendor attributes three codes to the scraper: `parse_error`,
`bad_input` and `wait_element_timeout`. Those are evidence of an extraction fault, and they
do fire the schema signal.

`vocabulary.py` is the only location where these names are correct. A manual copy of this
list gave four of five names incorrectly one time. This is why the sets are in
`vocabulary.py` and not here. Use the names above to read this section. Do not use them as
the source.

Such a run never heals for a volume reason. It can still report a schema break. It always
asks for a retry.

> The narrow reading, which used `rate_limit` only, was a **live false negative**. Five of
> ten rows returned `blocked`, and the result was `broken=False`, `signals={}` and no
> retry. That is complete silence on a run that was half broken. Do not use that reading
> again.

**The system reports an ambiguous code. It does not judge it.** One run cannot tell a dead
page from a collector that resolves a relative link against the root of the site. A true
payload gave 980 `dead_page` rows from that second condition. Therefore `detect` is
stateless: an ambiguous code goes into `DetectVerdict.ambiguous_codes` and asks for a
retry. **The facade does the escalation.** It retries one time. If the *same* ambiguous
codes return, they are no longer probably transient, and they become evidence of an
extraction fault. One unnecessary retry is the inexpensive direction for an error.

**Thresholds and precedence.**

- `NULL_RATE_SPIKE = 0.5` — absolute rise above baseline.
- `ROW_COUNT_DROP = 0.4` — `row_count` fires on a 40% shortfall against the baseline, and
  not on a decrease to zero only. A partial decrease is the usual shape of a break.
- Signal precedence, pinned by a test: **`skeleton > schema > row_count > null_rate`**. A
  tag-and-class tree that moved is *why* the other signals fired. A named symptom makes
  the heal look for a field on a page whose rows it can no longer find.
- **The first run has no baseline and returns `broken=False`.** No data to compare against
  is not evidence of a break.
- **`diagnose` never reads `incomplete`.** `FIRED` is the only input to the
  classification. `detect` already suppresses the volume detectors when any row is
  target-side. Therefore a signal that reaches `FIRED` in an incomplete sample is evidence
  of an extraction fault, by design. If the system suppressed on `incomplete` alone, it
  would delete a true schema break when one adjacent row was blocked.

## 9. The heal → verify → promote contract

These are the obligations of the facade and the benchmark. Verification found each one.
The design did not anticipate them.

**A gate cycle is not one row.** A gated heal writes **two** events: `awaiting_approval`,
and then the terminal outcome. An auto-approve and a failed call write one event. Code that
counts the rows for each cycle must select the **terminal-most** row. It must not use the
row count as the cycle count.

**Where a failed gate call raises, and where it does not.** The use cases `heal.heal` and
`heal.approve` write the row and raise `StudioError` again. The **facade does not**.
`Healer.heal` catches the exception and returns the recorded event with `status=failed`.
The benchmark branches on this (`if not loop.heal(...).promoted`), and the healer tests pin
it.

The two halves are both important. If a caller of the facade writes `try/except StudioError`
around it, that branch never runs, and the caller does not examine the event that it
received. If a caller of the use case examines `event.status` and does not catch the
exception, it never receives an event.

**A gate that opens must be answered, including on the exit path.** Bright Data completes
the full repair and then waits at `user_approval`. If any component raises between the
opening of the heal and its settlement, `_record` rejects the gate with `release_gate()`
before the exception propagates. The original error still reaches the caller, and a cleanup
that fails travels with it as a note. It does not replace the original error. The project
verified this at cost: a parse error omitted `approve`, the collector waited at the gate for
five hours, and each later heal returned
`Status: 409 — Another refactor job is still in progress`. Two collectors were stranded, and
a person had to release them.

**A refusal because the collector is occupied is not a failed repair.** `GateBusyError` and
`HealStatus.GATE_BUSY` keep the two conditions apart. The first is retryable and means that
the system attempted nothing. The second is a verdict on a repair that the system did
attempt. `Healer._gate` clears a stale gate and proposes again exactly one time
(`GATE_RECOVERY_ATTEMPTS`). It then stops, and does not cycle against a billable endpoint.

**There are three branches, and they are not equivalent:**

| Condition | Outcome |
|---|---|
| `except StudioError` | not promoted |
| `except VerificationIncompleteError` | **retry** — never refuse |
| `VerifyReport` is `False` | refuse |

If the system refused on `VerificationIncompleteError`, it would discard a heal that it
never tested, and it would give the benchmark an invented non-regression failure.

**⚠️ "Refused" is a verdict and not an undo.** `heal` runs with `--auto-save`. Therefore the
new template is live when the system writes it. `approve` refuses anything that is no longer
at the gate. Therefore when the verification has a verdict, there is nothing to reject. The
API supplies no method to restore a previous template. Therefore a refused heal leaves the
collector **modified**, and only the heal event records that the system did not keep the
change. Code that drives many collectors must treat a refused heal as permanent. This is
why two benchmark cases cannot share one collector.

**There are two promotion floors.** A published methodology must contain both, or the
numbers are not reproducible:

- `NON_REGRESSION_FLOOR = 1.0` — the old layout must still give *each* golden field. With a
  lower floor, a heal can lose one field in ten and still publish as non-regressive.
- `field_accuracy > 0` — a heal that does nothing extracts nothing and regresses nothing.
  Without this floor it would score perfectly on the old layout and promote.

## 10. Persisted schema (`src/bdheal/schema.sql`)

There are three tables: `bdheal_baselines`, `bdheal_heal_events` and `bdheal_bench_cases`.
The package contains them, and `store.connect()` applies them. The package loads the schema
through `importlib.resources`. Therefore a wheel operates in the same way as a checkout.

- **Each table name has the prefix `bdheal_`.** The app already owns a `heal_events` table
  with a different shape. The prefix lets the two share one SQLite file, and neither owns
  the DDL of the other.
- **There is no foreign key to an application table.** `bdheal` does not own the collectors.
  The caller tells it about them. A `REFERENCES collectors(id)` would make the package
  unusable on its own.
- Each SQL statement binds its parameters. A collector id comes from the caller, and the
  package treats it as hostile.

## 11. Reuse registry

Extend these components. Do not make a near-copy adjacent to one.

| Component | Where | Use it for |
|---|---|---|
| The nine boundary models | `models.py` | Every boundary type |
| `NonBlankStr`, `Ratio` | `models.py` | Shared field constraints — annotate rather than re-spelling `Field(ge=…)` |
| `SignalKind`, `SignalOutcome`, `FailureClass`, `HealStatus`, `MutationClass` | `vocabulary.py` | Any closed set. No bare string literals for states |
| `BdhealError` and subclasses | `errors.py` | Every raise |
| `skeleton()`, `skeleton_hash()` | `skeleton.py` | Any structural comparison |
| `null_rates()`, `capture_baseline()` | `detect.py` | Baseline maths, used by detect and the facade |
| `TEMPLATES`, `Diagnosis` | `diagnose.py` | Prompt selection. A new failure class adds a row |
| `heal()`, `approve()`, `release_gate()`, `PROMOTED_STATUS` | `heal.py` | The approval gate. `release_gate` answers a gate with no `HealEvent` to describe it — the state the incident above left behind |
| `PreviewResult` | `models.py` | The preview's two shapes. Annotate rather than re-spelling the union |
| `BDATA_ARGV`, `DEFAULT_TIMEOUT_S`, `BATCH_TIMEOUT_S` | `studio.py` | Every `bdata` invocation |
| `connect()`, `SqliteHealStore` | `store.py` | Persistence; `schema.sql` is the single DDL source |
| `SystemClock` / `SubprocessRunner` | `clock.py` / `process.py` | The only `datetime.now` / `subprocess.run` |
| `Mutation`, `MUTATIONS` | `bench/mutate.py` | The generator registry |
| `Metrics`, `CoverageRow` | `bench/metrics.py` | Benchmark aggregation |
| Stubs and fixtures | `tests/conftest.py` | Every test. Programme the supplied stub |

## 12. Conventions

This document does not repeat the coding rules for the project. These rules apply to this
package:

- **Give a file the name of its role, and not of its type.** Do not make `utils.py`,
  `helpers.py` or `base.py`.
- **A module docstring gives the reason that the module exists.** A comment explains a
  *reason* that is not obvious, and nothing else.
- **Each error is explicit and typed.** Do not use a bare `except`. Do not discard an
  exception. A failure of `bdata` raises a subclass of `StudioError`. Its message says what
  to do, and it names the orphan collector that a failed `create` leaves.
- **The package never configures logging.** Configuration belongs to the application.

## 13. Test strategy

**Framework:** `pytest` and `pytest-cov`. There is no other framework, no mock library and
no HTTP recorder. A test that needs a fake programmes a stub from `conftest.py`.

**Layout:** `packages/bdheal/tests/`, flat, one file for each module under test. A test
function is `test_<what_is_true>` and reads as a sentence.

**Run the suite with one command from the root of the repository:**

```bash
uv run --package bdheal pytest packages/bdheal
```

It must exit 0 with no corpus, no database, no app and no network (G1). This is the proof
of the architecture. It is not a convenience.

A **unit** test runs a pure function against literal inputs, and asserts against exact
goldens. This includes a hash that is pinned to a literal. An **integration** test runs two
or more units across a stubbed port. `SqliteHealStore` is the one adapter that uses a true
resource. Test it against `tmp_path` and never outside `tmp_path`.

Type each fixture as the **port** and not as the adapter. A test then cannot bind to an
implementation detail:

| Stub | Stands in for | Behaviour |
|---|---|---|
| `StubStudioClient` | `StudioClient` | Queued canned responses; records calls and URLs |
| `InMemoryHealStore` | `HealStore` | Dictionaries. No file, no schema |
| `FixedClock` | `Clock` | Frozen; `advance(seconds)` makes elapsed times exact |
| `RecordingRunner` | `CommandRunner` | Captures argv and timeouts, replays queued results — how argv-injection and `--timeout` assertions happen without `npx` |
| `ForbiddenRunner` | `CommandRunner` | Raises on any call — proves a path never leaves the process |
| `SampleRow` | the caller's `row_schema` | Deliberately generic; a test needing domain vocabulary has already failed |

**A gated test has a marker, and the suite omits it unless its environment variable is
set.** `@pytest.mark.live` (`BDHEAL_LIVE=1`) uses the true CLI. `@pytest.mark.publish`
(`BDHEAL_PUBLISH_CHECK=1`) does the clean-room build and install. That check replaces the
lockfile that the package intentionally does not carry. One `pytest_runtest_setup` hook
reads the `NETWORK_GATES` map. Therefore a third gate is a row and not a branch. The
markers are declared under `--strict-markers`. Therefore a marker with an incorrect name
fails, and does not run without a message.

**`tests/test_architecture.py` is a standing test, and no feature owns it.** It enforces the
layer map, the inward rule, the dependency limit (G2 and G4), and the absence of a `shell`
argument (G3). If it fails, correct the code or this document. Do not correct the test.

### The argv flag guard — and what it cannot find

`tests/test_studio.py` records the valid flag set for each subcommand (`ALLOWED_FLAGS`) and
the pairs of flags that do not combine. It asserts that the adapter never emits a flag
that a subcommand does not have, and never emits an exclusive pair together. It exists
because the injected `CommandRunner` prevents the suite from knowing if the true CLI would
accept the argv that the adapter sends. Three argv defects passed a green suite of 91 tests
before the project added this guard.

**A limit of its scope, verified by a mutation test:** it finds a flag that is *incorrect*
and a pair that *conflicts*. It **cannot find a required flag that is absent**. A delete of
`--format html` from `fetch_html` keeps the suite green, because an absence is not a
violation. **Each required flag needs its own point assertion.** This is most important
where the CLI has a default that is silent and incorrect for this package.

Two such flags exist. The project found the second one in production on 2026-08-20, after
it shipped undetected behind a green suite:

- `bdata scrape` uses `--format markdown` by default. Markdown parses to a skeleton hash
  with no meaning, and no component reports an error.
- **`scraper heal` does not persist without `--auto-save`.** It previews the fix, accepts an
  approval, and reports `done`, and the collector continues to run its old template. Each
  heal appeared to succeed and changed nothing. That is the exact condition that this
  package exists to prevent. The guard listed the flag as permitted, and never asserted that
  the adapter sent it.

## 14. Benchmark

`MUTATIONS` contains these declarations. The runner reports which detector caught each
class, and publishes each disagreement as a coverage gap. **A gap is a finding and not a
failure.**

| Mutation class | Declared detectors | Moves the skeleton hash? |
|---|---|---|
| `column_reorder` · `field_split_merge` · `wrapper_nesting` | `{skeleton}` | yes |
| `class_rename` · `table_to_div` | `{skeleton, row_count}` | yes — extraction stops entirely, so the count collapses too |
| `pagination` | `{skeleton, row_count}` | yes — and the row count falls with it |
| `date_format` | `{schema, null_rate}` | no |
| `url_pattern` | `{schema, null_rate}` | no |
| `link_label` | `{}` — expected to evade all four detectors | no |

The three non-structural classes do not move the hash. This shows that `skeleton.py`
operates correctly, because its contract is that it ignores text. Each declaration is a
**set**. Therefore a class that no detector catches is the empty set, which is an honest
published gap, and `coverage` is a membership test. It does not decode names manually.

**⚠️ A collector must have a scope of one page.** A simple `create` against a listing URL
makes a site crawler and not a page extractor. One probe walked a complete catalogue for
1.05K page fulfillments and 999 failed crawls, and returned one record. The description of
each `create` states *this page only, follow no links, no pagination*. Each fixture is a
self-contained page with no location to crawl to.

**⚠️ There are two parsers.** `skeleton.py` hashes with `selectolax`. `bench/mutate.py`
generates with `lxml`. Today the two parsers agree on all nine classes, and the project
verified this independently. But a difference in how they tolerate malformed HTML would
make the coverage matrix incorrect. If a case reports an unexpected detector, look for a
difference between the parsers before the detector comes under suspicion.

**⚠️ `column_reorder` must reorder siblings that differ in tag or in class.** An exchange
of two siblings that are identical byte for byte cannot move a structural hash,
because the structure did not change. A fixture with uniform cells would then fail the
criterion for a correct implementation.

**One golden set cannot score two layouts.** `verify` scores the healed pass and the
old-layout pass against one golden set. This is correct for the six structural classes. It
is incorrect for `date_format`, `url_pattern` and `link_label`, because their mutations
change the text of the page. **Resolved: omit those three from the non-regression rate and
disclose this** in a note that travels on each `Metrics` value. A limit that appears in
documentation only is not disclosed to the person who reads the number. The system also
omits an incomplete verification. It does not count one as a failure.

**`caught_by` is one signal. `fired_kinds` is each signal.** `SIGNAL_PRECEDENCE` selects
`caught_by`, which answers "which detector gets the credit". `as_declared` compares
`fired_kinds` against the declaration, because a class that also trips an undeclared
detector is a disagreement that must be published. The first live run showed this.
`row_count` fired on `class_rename`, `table_to_div`, `url_pattern` and `date_format`. None
of the four declares `row_count`. The system kept the credited kind only, and each of the
four reported "as declared".

**What the runner must do:**

- Build the spec of each case with `anchor_urls=[fixture_url]`. A `RunResult` does not carry
  its source URLs. Therefore the retry for an ambiguous code runs `spec.anchor_urls` again.
  If those URLs are not the fixture, the retry examines a *different page*, and no component
  reports this.
- `caught_by` is `None` for an escalated case. The retry of the loop caught the case, and a
  detector did not. To invent a signal would tell the matrix something else. Do not read
  this as a gap without the qualification.
- Attempts-to-heal counts the passes of the loop. It does not count the heal calls.
  `VerifyReport.attempts` counts the verification passes in one `verify()` call.

## 15. Resolved decisions

These are recorded so that no person derives them again.

1. **Workspace root.** Root `pyproject.toml` with members `api` and `packages/bdheal`, one
   lockfile at `/uv.lock`, api image built from the repo root.
2. **Coverage matrix over hash coverage.** Non-structural mutations are declared against the
   detectors that should catch them and the disagreements are published, rather than
   stretching the skeleton hash to cover text changes.
3. **Partial throttle suppresses volume signals only** — widened later to every target-side
   code (§8).
4. **Hosted and unattended pieces are out of scope** for this build.
5. **`bdheal` carries no lockfile.** A library that pins its own transitive tree is hostile
   to the applications that embed it. The gated clean-room build-and-install check proves
   installability instead.
6. **Where the skeleton signal's HTML comes from.** `StudioClient.fetch_html` via
   `bdata scrape`; `detect(..., page_html=None)` skips the skeleton signal.
7. **`Healer` lives in `healer.py`**, Use Cases.
8. **`ports.py` exists at all.** If each port were adjacent to its adapter, the file could
   not belong to one layer. A port is in `ports.py` (Use Cases). An adapter is in
   `studio.py` or `store.py` (Interface Adapters).
9. **`bench/runner.py` receives a `HealLoop`**, and not a `StudioClient` with a `HealStore`.
   This satisfies "runs green with no network", and `bench/` does not import its parent. A
   signature-comparison test guards `Healer` and `HealLoop` against a difference.
10. **Licence: MIT.** `LICENSE` at the repo root and a bundled copy in the package; the
    wheel carries `License-Expression: MIT`.

## 16. Known gaps

These are true, recorded, and none of them blocks release. State them. Do not let a reader
find them.

- **The redaction net in `studio.py` catches only what it can name.** An unlabelled token
  passes through if it is base64 that contains `+` or `/`, if it is one character class, or
  if it is shorter than `MIN_OPAQUE_CHARS`. This is the residue behind four label-based
  patterns. A labelled pattern covers the two named threat channels: `npx` that echoes argv,
  and `bdata` that relays an auth error. The floor of 24 characters is a compromise against
  the redaction of a collector id.
- **`preview_result` is the one field from a subprocess that the system persists without
  redaction.** It holds sample rows and not auth material. Therefore the risk is low. But
  examine this again if the loop ever previews a page behind authentication.
- **`mean_attempts_to_heal` gives `1.0` by design** — one loop pass for each case, one heal
  for each pass. It is true and tested, but it carries no information until the runner has a
  retry budget. Say this at publication.
- **`null_rate` has never fired.** The project confirmed this against a live collector
  across all nine classes. `url_pattern` declares `null_rate`, but an incorrect field used
  to reject the complete row. `rows` was then empty and each null rate was 0.0, which cannot
  spike. Partial rows (§7) make the signal reachable. Whether it now fires is untested until
  the next live run.
- **A refused heal on Bright Data cannot be reversed** (§9). The record says that the system
  did not keep the heal. The collector stays healed in both conditions.
- **A target-side code with no baseline gives `signals == []`**, and `incomplete`,
  `retry_requested` and `reason` still carry information. This agrees with "no baseline
  means that no detector ran". But it needs a regression test at the next change to
  `detect.py`.

## 17. The source surface, and what it does not have

`bdheal` does not depend on a source. `ixq` does. These are properties of
medicines.org.uk that shaped the schema and the UI. The project verified each one against
the served HTML. It did not assume them. They are here because a person has already found
each one a second time.

- **No product photograph of any UK generic exists, anywhere.** EMC has no concept of an
  image. Its sitemap contains `/smpc` and `/pil` URLs only. A PIL PDF contains no embedded
  image. The MHRA schema has no image field. The manufacturers have decided not to publish
  a photograph. A branded medicine gets photography. A POM generic gets a row in a table.
  More effort cannot close this gap. The substitute is §3 *Pharmaceutical form*, which is
  the manufacturer's own regulated description. The system parses it into `AppearanceView`
  and shows it as a **drawing that the project makes**. This is why each glyph must read as a
  schematic and never as a photograph.

- **There are two revision dates on each page, and they disagree.** `Last updated on emc:`
  and §10 *Date of revision of the text* differ by as much as years. The system stores both,
  as `listing_updated` and `revised`, because they answer different questions. A reader who
  sees one date only cannot tell which staleness they are looking at. Continue to publish
  the publisher's own string. A parse of text with a precision of one month into a date
  invents a day that no person published.

- **There are two company values on each page.** The account name in the header
  (`Aurobindo Pharma - Milpharm Ltd.`) is not the legal MA holder in §7
  (`Milpharm Limited`). `ma_holder` and `holder_id` hold the header value. `ma_holder` is
  free text. Therefore two spellings of one company become two columns without a group on
  `holder_id`.

- **There is no structured field for the strength or the pharmaceutical form.** A regular
  expression extracts `variant` from the product name. `variant` is `null` when the name
  does not carry both values — 102 of 744 stored labels. A card that assumes a value shows a
  blank line.

- **The marketing status is binary.** A `discontinued` badge is present or absent. The site
  has no suspended state and no withdrawn state.

## 18. The honesty layer is necessary

Four independent components carry the statement that an absence has a scope, and that the
system does not assert it. They appear redundant and they are not. Each one covers a route
that the others do not reach. **Do not combine them into one.**

- `SectionCoverage` draws an uncollected section with a dashed border. Therefore the scope
  of an absence is visible adjacent to it.
- Each absent cell says, in words, that it is not the same as a label that is silent.
- `RecallGap` publishes two counts. It does not publish a percentage that flatters.
- The reliability page separates a *declared* gap from a missed detection. A declared gap is
  a mutation that no detector can see, therefore silence is the expected result.

One rule is below all four: **report the placement, and never an omission that the system
did not examine.** A screen that cannot say which sections it read must not report an
absence.

## Working constraint

**Make no git commit without the explicit permission of the user.** An agent that works in
this repository does not run `git commit`, `git add`, or any other git write command. Work
stays in the working tree for the user to review.
