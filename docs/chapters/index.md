# The chapters

Five chapters that reconstruct the spine of sovereign-agent from nothing. Each chapter adds one or two architectural decisions, ships with a runnable demo, and ends with something you can show off.

The full chapter content is in the repo under `chapters/`. This page is a map.

## Pedagogical model

Each chapter's `solution.py` re-exports the corresponding module in `sovereign_agent/`. The tutorial and the package are the same code — the minitorch trick. A CI check (`tools/verify_chapter_drift.py`) enforces this so chapters cannot drift.

Work through a chapter in this order: read `README.md`, fill in `starter.py`, run `tests.py` until green, compare to `solution.py`, then `python -m chapters.chapter_N_<slug>.demo`.

## The sequence

### Chapter 1 — Session directory as the unit of everything
Decisions: 1. You build the `Session` class with atomic state writes, traversal-safe paths, and the trace-append helper. Demo: create a session, write events, update state, inspect the directory tree.

### Chapter 2 — SessionQueue with three guarantees
Decisions: 2, 4, 8. Per-session serialization, global concurrency cap, retry with exponential backoff, idle preemption via `_close` sentinel, graceful shutdown that detaches rather than kills. Demo: 6 sessions with `max_concurrent=3` running in waves.

### Chapter 3 — Filesystem IPC and tickets
Decisions: 3, 9. Atomic IPC messages via temp-file-then-rename, `IpcWatcher` with fail-closed handoff rules, the `Ticket` state machine (`pending → running → success/skipped/error`), and manifest discipline (no success without a verified sha256 manifest). Demo: happy path plus a deliberately corrupt manifest that the framework refuses to accept.

### Chapter 4 — Drift-corrected scheduler
Decisions: 6. The `compute_next_run` function with anchoring and skip-ahead. Demo: side-by-side comparison of anchored vs naive scheduling under a simulated "laptop asleep" scenario.

### Chapter 5 — Planner, executor, halves — the working agent
Decisions: 5, 7, plus the two-stage planner/executor split, tool discovery, the handoff protocol, and a minimal orchestrator. Demo: end-to-end agent trajectory that plans, executes, calls tools, writes files, and completes.

## Why five and not eight

The eight architectural decisions don't map 1:1 to chapters. Some decisions are boring alone (Decision 5 — credential gateway; Decision 7 — mount allowlist) but make sense as part of the "production-readiness" chapter (5). Others are only useful in combination: Decisions 3 and 9 both matter individually, but the point is that they *work together* to give you inter-process communication with verifiable proof of work. Packaging them into one chapter makes the demo legible.

The unit is "runnable demo," not "atomic concept." Five chapters, five runnable demos, one working agent at the end.
