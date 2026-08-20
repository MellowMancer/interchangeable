# AI assistance disclosure

This file is to disclose where and how AI tools were used throughout the repository.

## Tool

**Claude Code (Anthropic)**, used throughout in an agentic terminal workflow. Bright Data's Scraper Studio is driven from a coding agent through the `bdata` CLI, so collector creation, running, healing and approval
all happen inside the same terminal session as the code that calls them.

## What the AI produced

- The implementation of `bdheal` across its twelve features: detectors, failure
  classification, the heal gate, verification, persistence, the CLI adapter, and the
  benchmark harness — built feature by feature, each one gated by an independent test pass.
- The test suite (370 offline tests) and the architecture tests that enforce the layer map.
- `docs/BRIGHT_DATA.md` A Stripped down version of the bdata documentation provided by `bdata --help`
- The nine mutation generators, the fixture renderer, and this repository's documentation.

## What the author directed, decided and verified

- **Architecture.** Splitting the work into a reusable self-healing library and an
  application that consumes it, rather than one program that does both.
- **Healing Criteria.** 
  - That verifying a heal means re-running the healed collector against the *old* layout to prove it was not overfitted, not merely re-running it against the new one and observing green.
  - To consider proportional record-count drop as a quarantine signal, which became `ROW_COUNT_DROP` in
  `detect.py`; 
- **The error-code vocabulary.** The assistant invented five plausible Bright Data error
  codes and got four of them wrong. The author diagnosed that by obtaining a real 1000-row payload, inspecting it, and updating the vocabulary in `packages/bdheal/src/bdheal/vocabulary.py`.
- **The single-page collector constraint.** Diagnosed from a real run in which a collector
  built from a listing URL crawled 1.05K pages and failed 999 of them to return one record.
- **Corrections during review.** Several assistant-authored defects were caught and fixed
  before they shipped, including a credential-redaction pattern that leaked short tokens while passing its
  test, and a baseline guard that let a half-refused run poison the collector's known-good shape.
- **Every commit author-approved.** Author required that nothing be committed without permission, so no commit in the history was agent-initiated.
- **Quality gates.** Each commit was verified to follow proper standards, minimal redundancy, modularity, ensuring linear dependencies (children not importing functions of the parent) and more
