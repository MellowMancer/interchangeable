# rf-pre

## Top priority: clean, structured code

This outranks speed, cleverness, and feature count.

- **Zero duplication.** Extract shared logic. Never copy-paste a block between files.
- **Minimal comments.** Code explains itself through naming. Comment only non-obvious *why*, never *what*. No commented-out code.
- **No over-complication.** Minimum code that solves the problem. No speculative features, no abstractions for single-use code, no unrequested "flexibility", no error handling for impossible cases. If 200 lines could be 50, rewrite it.
- **Surgical changes.** Touch only what the task requires. Don't refactor working code, reformat neighbours, or delete unrelated dead code — mention it instead.
- **Match existing style**, even where you'd do it differently.
- Cognitive complexity ≤ 15 per function. Single responsibility per function/class. Named constants, not magic values. Explicit error handling, never a silent catch.

## Modular and isolated

- **Children never reference parents.** No upward imports (`from ..x import y`), no reaching outside a module's own directory for a sibling's internals. A parent may compose its children; a child must not know its parent exists.
- Each module is self-contained and independently testable — it depends on what it is given, not on where it sits in the tree.
- Cross-module communication goes through explicit interfaces and typed boundaries (Pydantic models), never shared mutable state or another module's private names.
- Deleting or relocating a module should break only its call sites, nothing beneath it.

## Don't assume

State assumptions explicitly. If multiple readings exist, surface them rather than picking silently. If something is unclear, stop and ask. If a simpler approach exists, say so.

## Architecture

Clean Architecture. Before creating a file, identify its layer: Entities → Use Cases → Interface Adapters → Frameworks & Drivers. Dependencies point inward only. Use Cases reach external systems through abstract interfaces, never concrete clients.

Project-specific: FastAPI is the seam between pipeline and UI — the frontend never opens SQLite. Tier cues, lexicon, and agency config are data (`config/*.yaml`), not code.

`docs/BRIGHT_DATA.md` is the authority on the Bright Data CLI surface, not `docs/plan.md`.

## Commits

Format — tag, then a one-line summary. **No description body. No Claude co-author trailer.**

```
[feat] added self-healing to scraper
[chore] cleaned up comments
[docs] updated readme
[ui] Built shadow cards for loading ui elements
```

## Security

Before calling work complete, check for: hardcoded credentials or tokens, injection risk (SQL, shell, template), insecure defaults (`DEBUG=True`, open CORS, unvalidated input), sensitive data in logs or errors. Flag when a SonarQube scan (localhost:9000) is warranted.
