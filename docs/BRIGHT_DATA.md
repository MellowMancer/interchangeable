# Bright Data Scraper Studio — operational reference

Source: `https://docs.brightdata.com/datasets/scraper-studio/coding-agent-prompts`
Full docs index: `https://docs.brightdata.com/llms.txt` — fetch this to discover other pages.

## Invocation

Every command runs through `npx`. Nothing is installed globally.

```bash
npx -p @brightdata/cli bdata login
npx -p @brightdata/cli bdata --version
```

The binary is **`bdata`**, from the `@brightdata/cli` package.

## Verified CLI surface

Confirmed against `bdata --help` on **v0.3.5** (2026-08-18). This supersedes the
earlier prose-only reading of the docs page — every subcommand below is real.

```
bdata scraper create  <url> <description>   # -> {collector_id, name, status, ...}
bdata scraper run     <collector_id> [url]
bdata scraper heal    <collector_id> <prompt>
bdata scraper approve <collector_id>
```

### `--name` is worth passing on every `create`

The default is `cli-scraper-<timestamp>`, which makes every collector an account has ever
built indistinguishable in the UI. There is **no programmatic delete**, so a collector that
outlives its run can only be removed by a human picking it out of a list. Name them.

### ⚠️ `create` descriptions are capped at 500 characters

`--help` states it on the argument; nothing else does. Over the cap the template is
created and *then* the AI trigger returns `Invalid description` (400) — so an oversized
description costs an orphaned collector rather than a clean rejection. **Measure before
sending:**

```bash
LEN=$(printf '%s' "$DESC" | wc -c); [ "$LEN" -lt 500 ] || echo "too long: $LEN"
```

Verified the expensive way on 2026-08-20: a 587-character description stranded
`c_mt16flbr27bq7fbsjp`.

**Any AI-trigger failure orphans a collector**, not only the blocked-host case documented
below. The template is created first and generation is triggered second, so every 400 at
that second step leaves a `status: ai_trigger_failed` collector behind, with no
programmatic delete.

Flags that the source page did not show, but which exist:

| Flag | Where | Note |
|---|---|---|
| `--json`, `--pretty`, `-o <path>` | all four | output control; earlier marked unattested |
| `--timeout <seconds>` | the four **`scraper`** subcommands only | default 600; `run` batch mode defaults 3600. **NOT valid on top-level `bdata scrape`** — that command rejects it as an unknown option |
| `--max-retries <n>`, `--no-retry` | create, heal | retry on the AI-Flow 429 concurrency cap |
| `--auto-approve`, `--auto-save` | heal | `--auto-save` persists the healed template |
| `--reject` | approve | reject instead of promote |
| `--url <url>` | heal, approve | next-step hint only — **not** sent to the heal call |
| `--urls <list>` | run | **comma-separated single value**, not variadic — `--urls a,b,c`. Commander binds one argument, so space-separated URLs silently drop all but the first |
| `--input-file <path>` | run | one URL per line, or a JSON array of strings / `{"url": ...}` objects |
| `--sync`, `--sync-timeout` | run | synchronous `/dca/crawl`, single-URL only, server caps at 25–50 s |

Other top-level commands present: `scrape` (Web Unlocker), `search`, `pipelines`,
`status`, `zones`, `budget`, `browser`, `discover`, `skill`, `config`, `init`.

## The loop

Build minimal first, then heal to extend — a small known-good baseline makes the heal's `preview_result` verifiable against something.

1. **login** — authenticate.
2. **create** — scraper for a target URL + field list. Returns a Collector ID (`c_mpohus372o5tmid1jk` shape). Save it; every later step reuses it.
3. **run** — execute against a URL. Returns a JSON array of rows.
4. **heal** — repair or extend in place, anchored on a URL. The Collector ID does not change.
5. **approve** — anchored on the same URL.
6. **run again** — confirm the new fields come back.

### ⚠️ A heal is not persisted unless you pass `--auto-save`

Root cause found 2026-08-20 on `c_mt16h8d01sakfyvaem`, after the documented flow silently
failed twice.

**What does not work.** `heal <id> "<prompt>"` then `approve <id> --url <anchor>`. The
heal runs all nine steps, returns `awaiting_approval` with a `preview_result` containing
the new field populated with real content, and `approve` returns `status: done`. Every
later run — including against the anchor URL itself — returns the *original* field set.
Nothing reports an error at any point.

**What works.** `heal <id> "<prompt>" --auto-save`. The step list then contains one extra
entry absent from the first attempt:

```
Step: save_new_template — polling (attempt 1/1500)
```

Verified: a subsequent run returned the new field at 2,217 characters with every existing
field unchanged.

So `preview_result` is a proposal, `approve` acknowledges it, and **`--auto-save` is what
writes the template back**. The `heal → awaiting_approval → approve → done` sequence in
the docs is not sufficient on its own, and a pipeline following it exactly keeps running
the old template while reporting success.

**Always assert the field on a real run afterwards** — never trust a status. This is what
`Healer.heal()` exists to do; driving the CLI by hand skips that verification.

### ⚠️ `preview_result` is an object **or an array**

Verified 2026-08-21. A preview carrying several rows comes back as a JSON array:

```json
[{"components": [{"ref": "RF-001", "name": "…", "category": "…", "updated": "…", "href": "…"}, …]}]
```

A single-row preview comes back as an object, which is why a one-row collector never trips
this. Typing the field as an object alone rejects the array, and the *entire completed
repair* is discarded as an unusable envelope.

### ⚠️ An unanswered gate blocks the collector — `Status: 409`

Verified the expensive way, same day. Bright Data finishes the whole repair and then waits
at `user_approval`. If the caller never answers, the job stays open indefinitely — five
hours in the observed case — and every later heal on that collector fails:

```
Failed to start self-healing for collector c_…: Error: Another refactor job is still in progress
  Status: 409
```

It is not a slow job; nobody picked up. Clear it with `bdata scraper approve <id> --reject`,
which returns `{"status":"rejected","completed_steps":[…,"user_approval"]}` and frees the
collector immediately. **Any code path that opens a heal must answer the gate on its way
out, including on failure.**

### ⚠️ `--auto-save` on `heal` alone is NOT enough — `approve` needs its own

**Corrected 2026-08-21, on `c_mt16h8d01sakfyvaem`, after this file's previous advice cost
a completed repair.**

This section used to say `--auto-save` on `heal` was sufficient and `approve` did not need
its own. That is wrong, and following it loses the template silently.

`heal <id> "<prompt>" --auto-save` on a collector that has **no drift to repair** — i.e. a
deliberate schema extension rather than a fix — runs to `user_approval` and stops:

```
"status": "awaiting_approval",
"completed_steps": ["planner", "control_preview_runner", "code_fixer",
                    "step_preview_runner", "request_fulfillment_validator", "step_advance"]
```

**`save_new_template` is absent.** `preview_result` shows every requested field correctly
populated, which is what makes this so convincing and so wrong: the proposal is perfect
and nothing was written. A later run returns the original field set.

`approve <id> --auto-save` is what completes it:

```
"status": "done",
"completed_steps": [..., "step_advance", "user_approval", "save_new_template"]
```

**The working sequence is `heal --auto-save` then `approve --auto-save`.** Look for
`save_new_template` in `completed_steps`; its absence is the failure, whatever `status`
says.

The earlier note was verified against a *mutated page*, where the loop presumably
auto-approves its own repair. A schema extension has no mutation to detect, parks at the
gate, and the flag never gets to act. Both observations can be true; the old wording
generalised from one.

**And the rule this file already records still governs: assert the fields on a real run.**
That is what caught it — eight fields were live at 09:26 and gone by 10:37 because the gate
was never answered.

## Heal state machine

```
heal ──> status: awaiting_approval ──> approve ──> status: done
              │
              └─ preview_result: sample row under the proposed fix
```

`--auto-approve` skips the gate and polls straight to `done`. Use only where the heal is trusted without review.

`preview_result` is a free pre-promotion check: it shows the proposed extraction against a live anchor URL *before* the collector changes. Verify against it rather than promoting and re-running.

Heal covers both repair (layout broke) and extension (add fields to an existing schema) — same mechanism, same in-place semantics.

## Prompt template

One template, parameterised. Replace `<TARGET_URL>` and `<FIELDS>`.

```text
Build, run, heal and verify a Bright Data scraper end to end. Run every Bright Data CLI
command through `npx -p @brightdata/cli` so nothing is installed globally. Do every step
in order and stop if a step fails:

1. Authenticate: `npx -p @brightdata/cli bdata login`.
2. Create a scraper for <TARGET_URL> extracting: <FIELDS>. Report the Collector ID.
3. Run it on the same URL and pretty-print the result.
4. Heal it in place to also capture <ADDITIONAL_FIELDS>. Keep the same Collector ID,
   anchor the heal on the same URL, and show the approval envelope.
5. When preview_result shows every field, approve the fix anchored on the same URL.
6. Run it again and confirm all fields come back.
```

## `bdata scrape` is a different command with a different flag set

Top-level `scrape` (Web Unlocker) is **not** one of the four `scraper` subcommands and
shares none of their flags. Its complete option set, verified v0.3.5:

```
-f, --format <format>  markdown | html | screenshot | json   (DEFAULT: markdown)
--country <code>       ISO country code
--zone <name>          Web Unlocker zone
--mobile               mobile user agent
--async                submit asynchronously, return job id
-o, --output <path>    write to file
--json --pretty --timing
```

⚠️ **The default format is `markdown`, not HTML.** Any caller wanting markup — e.g. to
compute a structural skeleton hash — must pass `--format html` explicitly. Omitting it
returns markdown, which parses into a near-empty tag tree: no error, just a meaningless
fingerprint.

## Escalation is internal — one invocation, not two (verified 2026-08-19)

A `scraper run` that exceeds the realtime page limit **escalates and finishes the job by
itself**, in the same invocation:

```
stderr: Triggering scrape... / Polling (attempt 1/600)
        Realtime page limit exceeded — switching to batch mode...
        Submitting batch job...   Batch job: j_mt03g2acasgof6m2f
        Collecting (batch)...     Polling batch (attempt 1/3600) ...
stdout: the JSON rows, alone
```

Three consequences, all load-bearing for any wrapper:

1. **Never watch for `switching to batch mode` and re-run.** The announced job is already
   running and already paid for; a second run submits a duplicate. Two minutes-long,
   rate-limited jobs for one answer.
2. **`--sync` does not prevent escalation** — the capture above was produced *with* the
   flag set. It only restricts you to a single URL (it is rejected alongside `--urls`).
   There is therefore one run shape, at the batch deadline, because any call may escalate.
3. **Streams are separated**: progress and diagnostics on **stderr**, the JSON payload on
   **stdout** alone. So `json.loads(stdout)` is safe, and the escalation marker is a
   stderr string, not something that pollutes the payload.

Batch polling is slow and real: an observed run was still at `attempt 82/3600` after ~14
minutes. Budget the process deadline accordingly, and give it grace beyond the CLI's own
`--timeout` so `bdata` can report a timeout as JSON rather than being killed mid-sentence.

## Mutually exclusive flags on `scraper run`

`--sync` cannot be combined with `--urls` or `--input-file` — the `/dca/crawl` endpoint
takes a single URL. Verified verbatim:

```
✗ --sync cannot be combined with --urls / --input-file. The /dca/crawl endpoint accepts
  only a single URL. Drop --sync to use the batch endpoint (/dca/trigger).
```

So the sync path is reachable only for a single URL; multi-URL runs must go straight to
batch.

## Government-domain policy — blocks the plan's corpus

Verified 2026-08-18 against all four agencies. Bright Data classifies municipal sites
as Government and refuses them at the network layer, independent of robots.txt (which
permits `/AgendaCenter` on every one of them).

| Host | Response |
|---|---|
| `bothellwa.gov` | `Access denied: classified as Government and blocked by Bright Data usage policy` |
| `www.cityofpa.us` | same — flat policy block, no KYC offer |
| `www.bainbridgewa.gov` | `Forbidden: government site, requires special permissions` → KYC |
| `www.lakehavenwsd.gov` | same — KYC path offered |

`scraper create` against a blocked host fails at the AI-generation trigger with
`Domain not allowed` (400) and **leaves a half-built collector behind**; Bright Data
exposes no programmatic delete, so it must be removed in the web UI.

Sanctioned path is KYC at `https://brightdata.com/cp/kyc`. Do not route around the
classifier — no archive mirrors, no proxy indirection. This is a Bright Data–sponsored
hackathon and the policy is theirs to enforce.

## Operational timings

- `scraper create` on a permitted host completes the full nine-step AI build in ~2 min.
- `scraper run` polls up to **3600 attempts** in batch mode; a single run can take many
  minutes. Any subprocess wrapper needs a timeout well above the 600s default.
- Target sites can rate-limit the crawler: a run returns
  `{"error": "...too many requests", "error_code": "rate_limit"}` per input row rather
  than failing the job. Treat `error_code` as a first-class outcome in the Pydantic model.

## Notes for this project

- Collector IDs belong in `api/config/collectors.yaml` beside their anchor, never in code.
- A heal is anchored on a URL, so the plan's non-regression check maps cleanly: heal anchored on the new layout, then `run` against the **old** layout URL and diff against golden.
- Scraper Studio executes in Bright Data's cloud and cannot reach `localhost` — benchmark fixtures must be publicly hosted.
