# Bright Data Scraper Studio — operational reference

Source: `https://docs.brightdata.com/datasets/scraper-studio/coding-agent-prompts`
Full docs index: `https://docs.brightdata.com/llms.txt` — get this file to find other
pages.

## Invocation

Run each command through `npx`. Install nothing globally.

```bash
npx -p @brightdata/cli bdata login
npx -p @brightdata/cli bdata --version
```

The binary is **`bdata`**, from the `@brightdata/cli` package.

## Verified CLI surface

The project confirmed this against `bdata --help` on **v0.3.5** (2026-08-18). This
supersedes the earlier reading of the documentation page, which used the prose only. Each
subcommand below is real.

```
bdata scraper create  <url> <description>   # -> {collector_id, name, status, ...}
bdata scraper run     <collector_id> [url]
bdata scraper heal    <collector_id> <prompt>
bdata scraper approve <collector_id>
```

### Supply `--name` with each `create`

The default name is `cli-scraper-<timestamp>`. With this default one collector is not
distinguishable from another in the UI. There is **no programmatic delete**. Therefore a person
must find a collector in a list and remove it manually. Give each collector a name.

### ⚠️ A `create` description has a limit of 500 characters

`--help` gives this limit on the argument. No other source gives it. If the description is
longer than the limit, the system makes the template, and *then* the AI trigger returns
`Invalid description` (400). Therefore a description that is too long costs an orphan
collector. It does not give a clean rejection. **Measure the description before it goes
out:**

```bash
LEN=$(printf '%s' "$DESC" | wc -c); [ "$LEN" -lt 500 ] || echo "too long: $LEN"
```

The project verified this at cost on 2026-08-20. A description of 587 characters left
`c_mt16flbr27bq7fbsjp` orphaned.

**Each AI-trigger failure orphans a collector.** This is not limited to the blocked-host
condition below. The system makes the template first and starts the generation second.
Therefore each 400 at the second step leaves a collector with `status: ai_trigger_failed`,
and there is no programmatic delete.

These flags exist, but the source page did not show them:

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

These other top-level commands exist: `scrape` (Web Unlocker), `search`, `pipelines`,
`status`, `zones`, `budget`, `browser`, `discover`, `skill`, `config`, `init`.

## The loop

Build a minimal collector first. Then heal it to extend it. A small known-good baseline
gives something to verify the `preview_result` of the heal against.

1. **login** — authenticate.
2. **create** — make a scraper for a target URL and a field list. This returns a Collector
   ID with the shape `c_mpohus372o5tmid1jk`. Save the ID. Each later step uses it.
3. **run** — run the collector against a URL. This returns a JSON array of rows.
4. **heal** — repair or extend the collector in place, anchored on a URL. The Collector ID
   does not change.
5. **approve** — anchored on the same URL.
6. **run again** — confirm that the new fields come back.

### ⚠️ The system does not persist a heal without `--auto-save`

The project found this cause on 2026-08-20 on `c_mt16h8d01sakfyvaem`, after the documented
flow failed two times with no message.

**What does not operate.** `heal <id> "<prompt>"` and then `approve <id> --url <anchor>`.
The heal runs all nine steps. It returns `awaiting_approval` with a `preview_result` that
contains the new field with true content. `approve` then returns `status: done`. But each
later run returns the *original* field set, including a run against the anchor URL. No
component reports an error.

**What operates.** `heal <id> "<prompt>" --auto-save`. The step list then contains one more
entry, which the first attempt did not have:

```
Step: save_new_template — polling (attempt 1/1500)
```

Verified: a later run returned the new field with 2,217 characters, and each existing field
did not change.

Therefore `preview_result` is a proposal, `approve` acknowledges the proposal, and
**`--auto-save` writes the template back**. The sequence
`heal → awaiting_approval → approve → done` in the documentation is not sufficient. A
pipeline that follows the documentation exactly continues to run the old template, and it
reports success.

**Always assert the field on a true run afterwards.** Never trust a status. This is the
function of `Healer.heal()`. Manual use of the CLI omits that verification.

### ⚠️ `preview_result` is an object **or an array**

Verified 2026-08-21. A preview that contains more than one row comes back as a JSON array:

```json
[{"components": [{"ref": "RF-001", "name": "…", "category": "…", "updated": "…", "href": "…"}, …]}]
```

A preview with one row comes back as an object. Therefore a collector with one row never
finds this condition. A field that is typed as an object only makes the parse reject the array,
and the system discards the *complete repair* as an envelope that it cannot use.

### ⚠️ A gate with no answer blocks the collector — `Status: 409`

The project verified this at cost on the same day. Bright Data completes the full repair
and then waits at `user_approval`. If the caller never answers, the job stays open with no
limit — five hours in the observed case. Each later heal on that collector then fails:

```
Failed to start self-healing for collector c_…: Error: Another refactor job is still in progress
  Status: 409
```

The job is not slow. No person answered it. To clear it, use
`bdata scraper approve <id> --reject`. This returns
`{"status":"rejected","completed_steps":[…,"user_approval"]}` and releases the collector
immediately. **Each code path that opens a heal must answer the gate before it exits. This
includes a path that exits on a failure.**

### ⚠️ `--auto-save` on `heal` is NOT sufficient — `approve` needs its own

**Corrected 2026-08-21 on `c_mt16h8d01sakfyvaem`, after the previous advice in this file
caused the loss of a completed repair.**

This section previously said that `--auto-save` on `heal` was sufficient, and that
`approve` did not need the flag. That is incorrect, and it loses the template with no
message.

Use `heal <id> "<prompt>" --auto-save` on a collector that has **no drift to repair** — for
example, an intentional schema extension and not a fix. The heal then runs to
`user_approval` and stops:

```
"status": "awaiting_approval",
"completed_steps": ["planner", "control_preview_runner", "code_fixer",
                    "step_preview_runner", "request_fulfillment_validator", "step_advance"]
```

**`save_new_template` is absent.** `preview_result` shows each requested field with correct
content. This makes the result convincing and incorrect: the proposal is complete, but the
system wrote nothing. A later run returns the original field set.

`approve <id> --auto-save` completes the operation:

```
"status": "done",
"completed_steps": [..., "step_advance", "user_approval", "save_new_template"]
```

**The sequence that operates is `heal --auto-save` and then `approve --auto-save`.** Look
for `save_new_template` in `completed_steps`. If it is absent, the operation failed,
whatever the `status` says.

The project verified the earlier note against a *mutated page*. On a mutated page the loop
approves its own repair. A schema extension has no mutation to detect. Therefore it stops
at the gate, and the flag cannot act. The two observations can both be correct. The old
text generalised from one observation.

**The rule that this file already gives still applies: assert the fields on a true run.**
That rule found this defect. Eight fields were live at 09:26 and absent at 10:37, because
no person answered the gate.

## Heal state machine

```
heal ──> status: awaiting_approval ──> approve ──> status: done
              │
              └─ preview_result: sample row under the proposed fix
```

`--auto-approve` omits the gate and polls to `done`. Use it only for a heal that needs no
review.

`preview_result` is a check before promotion, and it is free. It shows the proposed
extraction against a live anchor URL *before* the collector changes. Verify against the
preview. Do not promote the change and then run the collector again.

Heal does the repair (the layout broke) and the extension (add fields to an existing
schema). The mechanism is the same and the in-place semantics are the same.

## Prompt template

There is one template with parameters. Replace `<TARGET_URL>` and `<FIELDS>`.

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

The top-level `scrape` command (Web Unlocker) is **not** one of the four `scraper`
subcommands. It has none of their flags. This is its complete option set, verified on
v0.3.5:

```
-f, --format <format>  markdown | html | screenshot | json   (DEFAULT: markdown)
--country <code>       ISO country code
--zone <name>          Web Unlocker zone
--mobile               mobile user agent
--async                submit asynchronously, return job id
-o, --output <path>    write to file
--json --pretty --timing
```

⚠️ **The default format is `markdown` and not HTML.** A caller that needs markup — for
example, to compute a structural skeleton hash — must supply `--format html`. Without the
flag, the command returns markdown. Markdown parses into a tag tree that is almost
empty. There is no error, but the fingerprint has no meaning.

## Escalation is internal — one invocation and not two (verified 2026-08-19)

A `scraper run` that goes above the realtime page limit **escalates and completes the job
without help**, in the same invocation:

```
stderr: Triggering scrape... / Polling (attempt 1/600)
        Realtime page limit exceeded — switching to batch mode...
        Submitting batch job...   Batch job: j_mt03g2acasgof6m2f
        Collecting (batch)...     Polling batch (attempt 1/3600) ...
stdout: the JSON rows, alone
```

This has three consequences. Each one is necessary for a wrapper:

1. **Never watch for `switching to batch mode` and start the run again.** The announced job
   already runs, and the account already paid for it. A second run submits a duplicate.
   Two jobs that take minutes and have a rate limit then give one answer.
2. **`--sync` does not prevent the escalation.** The project captured the output above
   *with* the flag set. The flag permits a single URL only, and the CLI rejects it with
   `--urls`. Therefore there is one run shape, at the batch deadline, because each call can
   escalate.
3. **The streams are separate.** The progress and the diagnostics go to **stderr**. The
   JSON payload goes to **stdout** only. Therefore `json.loads(stdout)` is safe, and the
   escalation marker is a string on stderr. It does not corrupt the payload.

The batch poll is slow and real. In one observed run the poll was still at
`attempt 82/3600` after approximately 14 minutes. Set the process deadline for this. Give
the process more time than the `--timeout` value of the CLI. `bdata` can then report a
timeout as JSON, and the system does not stop it during its output.

## Flags on `scraper run` that do not combine

`--sync` does not combine with `--urls` or with `--input-file`. The `/dca/crawl` endpoint
accepts one URL. Verified verbatim:

```
✗ --sync cannot be combined with --urls / --input-file. The /dca/crawl endpoint accepts
  only a single URL. Drop --sync to use the batch endpoint (/dca/trigger).
```

Therefore the sync path serves a single URL only. A run with more than one URL must use
batch.

## Government-domain policy — this blocks the corpus in the plan

Verified 2026-08-18 against all four agencies. Bright Data classifies a municipal site as
Government and refuses it at the network layer. This is independent of `robots.txt`, which
permits `/AgendaCenter` on each of the four sites.

| Host | Response |
|---|---|
| `bothellwa.gov` | `Access denied: classified as Government and blocked by Bright Data usage policy` |
| `www.cityofpa.us` | same — flat policy block, no KYC offer |
| `www.bainbridgewa.gov` | `Forbidden: government site, requires special permissions` → KYC |
| `www.lakehavenwsd.gov` | same — KYC path offered |

A `scraper create` against a blocked host fails at the AI-generation trigger with
`Domain not allowed` (400). It **leaves a partially built collector**. Bright Data has no
programmatic delete. Therefore the collector must be removed in the web UI.

The permitted path is KYC at `https://brightdata.com/cp/kyc`. Do not go around the
classifier. Do not use an archive mirror. Do not use a proxy. Bright Data sponsors this
hackathon, and the policy is theirs to enforce.

## Operational timings

- On a permitted host, `scraper create` completes the full nine-step AI build in
  approximately 2 minutes.
- In batch mode, `scraper run` polls a maximum of **3600 attempts**. One run can take many
  minutes. A subprocess wrapper needs a timeout that is much longer than the default of
  600 s.
- A target site can rate-limit the crawler. The run then returns
  `{"error": "...too many requests", "error_code": "rate_limit"}` for each input row. The
  job does not fail. Make `error_code` a first-class outcome in the Pydantic model.

## Notes for this project

- Put each Collector ID in `api/config/collectors.yaml`, adjacent to its anchor. Do not put
  an ID in the code.
- A heal is anchored on a URL. Therefore the non-regression check in the plan maps
  directly: anchor the heal on the new layout, then `run` against the URL of the **old**
  layout and compare the result with the golden.
- Scraper Studio runs in the Bright Data cloud and cannot connect to `localhost`. Therefore
  the benchmark fixtures must be public.
