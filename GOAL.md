# Goal: build `bdheal` — a corpus-agnostic, independently installable Python package that wraps the Bright Data `bdata` CLI and self-heals web collectors (detect → diagnose → heal → verify → promote/rollback) with a benchmark that measures heal quality.

Authoritative spec: `docs/plan.md` (sections "Package split", "`bdheal` public surface",
"Self-healing loop", "Benchmark", "Verification"). CLI surface authority:
`docs/BRIGHT_DATA.md` — where the two disagree, `docs/BRIGHT_DATA.md` wins.

---

## Global invariants (checked on every feature, not just the one that introduces them)

These are gates, not aspirations. Any feature that breaks one is not done.

- [ ] G1 **Isolation.** `uv run --package bdheal pytest packages/bdheal` exits 0 with no
      corpus, no database file, no app, and no network. `StudioClient` and `HealStore`
      are stubbed at their interfaces in every test. If a test needs `preward`, a layer
      boundary has leaked.
- [ ] G2 **No upward dependency.** `rg -n "preward" packages/bdheal/` returns no match in
      `src/` or `tests/`. `packages/bdheal/pyproject.toml` does not name `preward`.
      The app depends on `bdheal`; never the reverse.
- [ ] G3 **argv is a list.** Every `bdata` invocation passes argv as a `list[str]`;
      `shell=True` appears nowhere in `packages/bdheal/`. Collector ids and heal prompts
      are interpolated values, so this is the injection boundary.
- [ ] G4 **Thin dependencies.** Runtime deps are exactly `pydantic selectolax lxml
      structlog`; dev deps exactly `pytest pytest-cov`. No `fastapi`, no `typer`,
      no `httpx`.
- [ ] G5 **Buildable at every step.** After each feature, `docker compose build api`
      exits 0 and the isolation test is still green — every feature is demonstrable on
      its own, without any later feature present.
- [ ] G6 **No secrets in output.** No API key, token or credential appears in any log
      line, exception message, heal prompt, or persisted `heal_events` row.
      (`BRIGHTDATA_API_KEY` lives in the gitignored `.env`.)

---

## Foundation

- [ ] F0 Architecture & shared skeleton (owner: designer)
      Produces `ARCHITECTURE.md`: layer assignment for every module in
      `packages/bdheal/src/bdheal/`, the two port signatures (`StudioClient`,
      `HealStore`), the workspace wiring decision (see Open question Q1), and the
      persisted schema shape for baselines and heal events.
      criteria: `ARCHITECTURE.md` exists at repo root; every module named in
      `docs/plan.md`'s repo layout (`models · studio · store · detect · diagnose ·
      heal · verify · bench/{mutate,runner,metrics}`) is assigned to exactly one Clean
      Architecture layer, and every dependency arrow it draws points inward.
      parallel-with: none

---

## Features (dependency order)

- [x] 1 Workspace + package skeleton — depends on: F0 (design only; no feature code)
      `packages/bdheal/` as a uv workspace member: `pyproject.toml`, `README.md`,
      `src/bdheal/__init__.py` with `__version__`, `tests/` with one real test.
      criteria: all of the following exit 0 from the repo root —
      (a) `uv run --package bdheal pytest packages/bdheal` (collects ≥1 test, all pass,
          no network access);
      (b) `uv run --package bdheal python -c "import bdheal; print(bdheal.__version__)"`
          prints a PEP 440 version;
      (c) `uv build --package bdheal` produces a wheel that installs into a clean venv
          with `preward` absent;
      (d) `docker compose build api`.
      (e) a standing **publishability check** (resolved, Q5): a `publish`-marked test,
          skipped unless `BDHEAL_PUBLISH_CHECK=1` so the isolation suite stays offline,
          builds wheel *and* sdist into a temp dir, installs the wheel into an empty
          venv resolved from the declared ranges alone, and asserts `import bdheal`
          works there with `__version__` and `__all__` intact and no repo path on that
          interpreter's `sys.path`.
      Plus G2 and G4 hold: no `preward` string anywhere under `packages/bdheal/`, and
      the manifest lists exactly `pydantic selectolax lxml structlog` + dev
      `pytest pytest-cov`.
      parallel-with: none

- [x] 2 Core models (`models.py`) — depends on: 1
      The whole public data surface: `CollectorSpec`, `RunResult`, `RowError`,
      `DetectVerdict`, `Signal`, `HealEvent`, `VerifyReport`. Pydantic models, no
      behaviour beyond validation.
      criteria: every name above is importable from `bdheal` top level and appears in
      `bdheal.__all__`; each has a one-line docstring. Invariant violations raise
      `ValueError` (pydantic `ValidationError` subclasses it), covered by a test per
      invariant — at minimum: empty/blank `collector_id` rejected; empty `anchor_urls`
      rejected; `row_schema` that is not a `BaseModel` subclass rejected;
      `RunResult.error_codes` defaults to an empty list (never `None`);
      `VerifyReport.field_accuracy` outside `0.0..1.0` rejected;
      `HealEvent.status` outside the documented status set rejected.
      `RunResult` round-trips through `model_dump()` / re-validation unchanged.
      parallel-with: none

- [x] 3 `StudioClient` port + `BdataStudioClient` adapter (`studio.py`) — depends on: 2
      The only code in the package that shells out to `bdata`. Abstract port + one
      concrete adapter; the subprocess runner is injected so tests never spawn `npx`.
      criteria:
      (a) a canned `bdata scraper run --json` payload containing 2 well-formed rows and
          1 `{"error": "...too many requests", "error_code": "rate_limit"}` row parses
          into a `RunResult` with exactly 2 validated rows, one `RowError`, and
          `error_codes == ["rate_limit"]` — per-row errors are data, never exceptions;
      (b) **injection test**: a collector id containing `"; rm -rf / #` is passed
          through as one single argv element, argv is a `list[str]`, and `shell=True`
          is never used (G3);
      (c) realtime→batch escalation: when the sync path signals escalation the adapter
          switches to batch and polls, with a timeout argument well above the 600 s
          default (test asserts the `--timeout` value in argv);
      (d) a `create` that fails at the AI-generation trigger (`Domain not allowed`, 400)
          raises one typed error whose message names the half-built collector left
          behind — no silent swallow;
      (e) malformed/non-JSON stdout raises a typed error, not `JSONDecodeError`.
      parallel-with: 4, 5

- [x] 4 `HealStore` port + SQLite adapter (`store.py`) — depends on: 2
      Persistence for per-collector baselines and heal events, behind a port the app
      may re-implement. Schema ships inside the package.
      criteria:
      (a) pointing the adapter at a fresh temp file creates the DB and applies the
          packaged schema (loaded via `importlib.resources`, not a path relative to
          `__file__`'s parents); the expected tables exist afterwards;
      (b) a baseline (row count, per-field null rates, skeleton hash) written then read
          back compares equal; a `HealEvent` written then read back preserves `status`,
          `prompt`, `preview_result` and `promoted`;
      (c) all SQL uses bound parameters — a collector id of `x'); DROP TABLE
          heal_events;--` round-trips as a literal string and the table still exists;
      (d) no test in this feature requires a file outside `tmp_path`.
      parallel-with: 3, 5

- [x] 5 Skeleton hashing (`skeleton.py`) — depends on: 2
      Strip text, keep the tag+class tree, hash it (`selectolax`). Pure function.
      criteria: exact-match golden tests, deterministic across processes —
      (a) changing only visible text yields an **identical** hash;
      (b) renaming a CSS class yields a **different** hash;
      (c) changing a tag (`<table>` → `<div>`) yields a **different** hash;
      (d) reordering sibling elements yields a **different** hash;
      (e) whitespace, HTML comments and attribute ordering do not change the hash;
      (f) the same input hashed twice in separate interpreter runs gives the same
          constant, asserted against a literal in the test.
      parallel-with: 3, 4

- [ ] 6 Detect — four domain-free signals (`detect.py`) — depends on: 3, 4, 5
      Pydantic validation failure · silent zero rows where the prior run returned >0 ·
      skeleton hash delta vs baseline · field null-rate spike vs baseline.
      criteria:
      (a) each of the four signals fires on its own fixture and on no other, producing
          `DetectVerdict(broken=True)` with that signal named in `signals`;
      (b) **rate-limit discrimination (highest-value test)**: a run whose rows are all
          `error_code == "rate_limit"` — zero usable rows — returns
          `DetectVerdict(broken=False)`, names throttling as the reason, and proposes
          no heal. Throttled must never be read as broken;
      (c) a first-ever run with no stored baseline returns `broken=False` (nothing to
          compare against) rather than firing the zero-row or null-rate signal;
      (d) a healthy run matching baseline returns `broken=False` with an empty
          `signals` list;
      (e) detect reads history through the `HealStore` port only, and touches no
          domain vocabulary — the module contains no term specific to any corpus.
      (f) **partial-throttle policy** (resolved, Q3): when *any* row carries
          `error_code == "rate_limit"` the sample is incomplete, so the volume-based
          signals — zero-rows-vs-prior and null-rate spike — are suppressed and recorded
          as `inconclusive`, never as a break;
      (g) schema-validation failures on rows that **did** return remain valid break
          evidence even when sibling rows were throttled — a malformed row is malformed
          regardless of throttling. So a partially throttled run never proposes a heal on
          volume grounds, may still report a schema break, and always requests a retry.
          Test the worked case: 10 inputs → 3 `rate_limit`, 7 rows, 2 failing validation
          ⇒ schema signal fires, volume signals `inconclusive`, retry requested.
      parallel-with: 11

- [ ] 7 Diagnose — failure class → prompt template (`diagnose.py`) — depends on: 6
      Classify a `DetectVerdict` into a failure class, select the prompt template, and
      render the heal prompt.
      criteria: a table-driven test asserts each failure class maps to its expected
      template id, with a deterministic rendered prompt (exact-match golden string);
      a verdict with no recognised class falls through to the documented generic
      template rather than raising; a verdict with `broken=False` produces no prompt at
      all; the rendered prompt contains only the caller's field names from
      `CollectorSpec.row_schema` and no credential (G6).
      parallel-with: 11

- [ ] 8 Heal + approval gate (`heal.py`) — depends on: 7
      `bdata scraper heal <collector_id> "<prompt>"` → `awaiting_approval` →
      `preview_result` → `approve` or `--reject`, plus the unattended `--auto-approve`
      path.
      criteria:
      (a) the gated path yields `HealEvent(status="awaiting_approval")` with
          `preview_result` populated; approving yields `status="done", promoted=True`;
          rejecting yields `promoted=False` and the documented rejected status;
      (b) `collector_id` is byte-identical before and after every path — heal is
          in-place;
      (c) the `--auto-approve` path reaches `done` without a separate approve call, and
          the flag is asserted present in argv;
      (d) `--url` is **not** passed on the heal call (it is a next-step hint only, per
          `docs/BRIGHT_DATA.md`) — asserted absent from the heal argv, and present on
          the approve argv where the anchor is required;
      (e) the prompt is a single argv element even when it contains quotes, newlines and
          shell metacharacters (G3);
      (f) a `HealEvent` row is written through `HealStore` on every terminal outcome,
          including rejection and failure.
      parallel-with: 11

- [ ] 9 Verify + non-regression (`verify.py`) — depends on: 8
      Run the healed collector against golden records, then re-run it against the OLD
      layout URL and diff — the overfit check.
      criteria:
      (a) `field_accuracy` against a fixture with a known number of correct fields
          equals an exact expected value (e.g. 3 of 4 fields → `0.75`), asserted
          numerically, not as "close enough";
      (b) an overfit heal — fixes the new layout, breaks the old — yields
          `non_regression_passed=False`; a heal that satisfies both yields `True`;
      (c) the non-regression pass re-runs against `old_layout_url` through the
          `StudioClient` port, asserted by the stub recording that URL;
      (d) `VerifyReport` carries `attempts` and a non-zero `elapsed_s` from an injected
          clock, so the value is deterministic in tests.
      parallel-with: 11

- [ ] 10 `Healer` facade — depends on: 9
      The single public entry point: `run · detect · heal · verify`, with both ports
      injected at construction.
      criteria:
      (a) a full loop — break introduced → detected → diagnosed → healed → verified →
          promoted — runs green against a stubbed `StudioClient` and a temp-file
          `HealStore`, with zero network calls (asserted by a runner stub that fails the
          test if invoked);
      (b) both ports are constructor arguments; no module-level client, no global state,
          no default that reaches the network implicitly;
      (c) rollback path: verification failure leaves the collector unpromoted, writes a
          `heal_events` row with `promoted=False`, and does not bump the schema version;
      (d) `bdheal.__all__` exports exactly ten names — `Baseline`, `BenchCase`,
          `CollectorSpec`, `DetectVerdict`, `HealEvent`, `Healer`, `RowError`,
          `RunResult`, `Signal`, `VerifyReport` — and nothing else;
          `from bdheal import Healer` works from a clean venv.
      parallel-with: 11

- [ ] 11 Mutation generators (`bench/mutate.py`) — depends on: 5
      Nine domain-free HTML perturbations: class rename · `<table>`→`<div>` · column
      reorder · link label · URL pattern change · date format · field split/merge ·
      wrapper nesting · pagination.
      criteria:
      (a) nine generators exist, one per class, each taking HTML and returning HTML;
      (b) every output re-parses cleanly (`lxml` round-trip, no parser error) and is
          non-empty;
      (c) every output differs from its input;
      (d) output is deterministic — same input, same result, byte-for-byte, asserted
          against golden fixtures;
      (e) **declared expected detector** (resolved, Q2): every generator carries, as
          data on the generator rather than a comment, the detect signal that *should*
          catch its class — `skeleton` for the six structural classes, `schema` for date
          format, `schema_or_null_rate` for URL pattern, and **`none` for link label**,
          which is expected to evade all four detectors. F11 asserts the declaration
          exists and is one of the permitted values; it does **not** assert detection
          (that is F12's job, which already depends on both 10 and 11 — so no F11 → F6
          edge is introduced);
      (f) the six structural classes — class rename, `<table>`→`<div>`, column reorder,
          field split/merge, wrapper nesting, pagination — each change the F5 skeleton
          hash. The other three are text/attribute changes and by F5's contract must
          **not** move it;
          ⚠️ **`column_reorder` must reorder siblings that differ in tag or class**
          (found during F5). Swapping two byte-identical siblings cannot move a
          structural hash — the structure genuinely did not change — so a uniform-cell
          fixture would fail this criterion for a correct implementation. Build the
          fixture with distinguishable columns (e.g. `<li class="name">` vs
          `<li class="date">`);
      (g) no generator contains domain vocabulary; each is exercised on a generic
          fixture, not a corpus page.
      parallel-with: 6, 7, 8, 9, 10

- [ ] 12 Benchmark runner + metrics (`bench/runner.py`, `bench/metrics.py`) — depends on: 10, 11
      Drive mutated fixtures through the full `Healer` loop, record per-case outcomes,
      compute the five metrics, and persist run state so a multi-hour run resumes.
      criteria:
      (a) all five metrics are computed — heal rate, field accuracy vs golden,
          non-regression rate, time-to-heal, attempts-to-heal — each asserted to an
          exact expected value over a canned set of case results (injected clock, so
          timings are deterministic);
      (b) **resume**: a run interrupted after N of M cases, then restarted, executes
          only the remaining M−N cases and completes; the test asserts no case is
          executed twice and the final metrics match an uninterrupted run;
      (c) the runner accepts an injected `StudioClient` and `HealStore` — the whole
          benchmark runs green in tests with no network (G1);
      (d) exposes a callable Python API only; no CLI framework dependency is added (G4);
      (e) **signal × mutation coverage matrix** (resolved, Q2): the runner reports which
          detect signal actually caught each mutation class, compared against the
          generator's declared expectation from F11(e). Classes that no signal catches
          are reported as **detection gaps, not failures** — an honest published gap is a
          finding, and `link label` is expected to be one. The test asserts the matrix is
          produced and that a deliberately-undetectable case is reported as a gap rather
          than silently dropped or counted as a heal failure.
      parallel-with: none

---

## Dependency order at a glance

```
F0 → 1 → 2 → { 3 | 4 | 5 } → 6 → 7 → 8 → 9 → 10 → 12
                     └── 5 → 11 ─────────────────┘   (11 runs alongside 6–10)
```

Parallel groups: `{3, 4, 5}` after 2 · `11` alongside `6–10`.

---

## Resolved decisions

All four questions the planner raised were resolved with the user on 2026-08-19 before
any feature code was written. Recorded here so the rationale survives.

- **Q1 — Workspace root and Docker build context. → Root workspace.**
  The repo root gets a `pyproject.toml` acting as the uv workspace root, with members
  `api` and `packages/bdheal`; the lockfile lives at `/uv.lock`. `compose.yaml`'s
  `build: ./api` becomes a root-level context with `dockerfile: api/Dockerfile`, since
  the image needs both the lockfile and `packages/bdheal`. `bdheal` stays a **sibling**
  of `api/`, not a child — the peer relationship is the architectural point, and burying
  it under the app would undercut the claim that it is independently publishable.
  `docs/plan.md` contained a stale line asserting `api/pyproject.toml` owns the
  workspace; that line is corrected, this decision governs.

- **Q2 — Skeleton-hash coverage for non-structural mutations. → Coverage matrix.**
  Neither widen the skeleton nor restate F11 as "trips any signal". Instead each
  generator *declares* the signal that should catch it (F11(e)) and the benchmark
  *reports what actually caught it* (F12(e)). The three non-structural classes are
  expected not to move the skeleton hash — that is F5 behaving correctly, not a defect.
  **`link label` is expected to evade all four detectors**, and that is reported as a
  published detection gap rather than buried. This keeps F5's text-insensitivity
  contract intact, introduces no F11 → F6 edge, and converts a spec contradiction into a
  benchmark finding — which is the honest result the project's provenance discipline
  demands.

- **Q3 — Partial-throttle policy. → Suppress volume signals only.**
  Any `rate_limit` row makes the sample incomplete, so zero-rows-vs-prior and null-rate
  spike are suppressed as `inconclusive`. Schema-validation failures on rows that *did*
  return still count as break evidence, because a malformed row is malformed regardless
  of throttling. A partially throttled run never heals on volume grounds and always
  requests a retry. Rationale: healing against incomplete data is the expensive failure
  mode — it burns credits and can promote a collector fitted to a truncated sample.

- **Q4 — Scope boundary for hosted/unattended pieces. → Out of scope for this build.**
  GitHub Pages fixture hosting and the cron GitHub Action are operational infrastructure,
  not `bdheal` features, and are tracked outside this ledger. **F12 is done when the
  runner passes green against stubs with resume proven** — the real 3–7 hour live
  benchmark run is an operational task and cannot gate a feature.

---

- **Q5 — Should `bdheal` carry its own lockfile? → No; prove installability instead.**
  Raised during F1. Lockfiles are for applications: a library declares ranges and the
  consumer resolves. A second lockfile would pin one resolution that no consumer is
  bound by, so it could pass while the package remained uninstallable for anyone else.
  The single root workspace lock stays, and the claim "independently publishable" is
  carried by a permanent clean-room test instead — F1(e). It is gated behind
  `BDHEAL_PUBLISH_CHECK=1` because it builds and downloads, and G1 requires the default
  suite to stay offline. This adds to the earlier decisions; it supersedes none of them.

## Deferred to submission (Aug 22–23)

- **`docs/` is gitignored** (`/docs` in `.gitignore`), so `docs/plan.md` and
  `docs/BRIGHT_DATA.md` never reach the public repo. Hackathon rule 9 requires a public
  source repository **and** a written explanation of Scraper Studio usage. `GOAL.md` and
  `ARCHITECTURE.md` are tracked and unaffected. User decision: revisit at submission
  time — either publish `docs/` or write a separate root-level `SCRAPER_STUDIO.md` for
  judges. **Do not let this land on the 23rd alongside the demo video.**

- **Licence: MIT** (decided 2026-08-19). `LICENSE` at repo root and a bundled copy at
  `packages/bdheal/LICENSE`; the wheel carries `License-Expression: MIT` and
  `dist-info/licenses/LICENSE`. `bdheal` depends only on lxml (BSD), pydantic (MIT),
  selectolax (MIT) and structlog (MIT/Apache), so it is unencumbered by the AGPL-3.0
  `pymupdf` constraint that applies to the app.

---

## Working constraint

**No git commits without the user's explicit permission.** No agent working this ledger
may run `git commit`, `git add`, or any other git write command. Work stays in the
working tree for the user to review.
