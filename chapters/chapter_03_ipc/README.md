# Chapter 3 — IPC and Tickets

## What you'll build

Two of the most important primitives in sovereign-agent, introduced together because they're used together in every long-running operation:

1. **Filesystem IPC with atomic rename** (Decision 3). Processes talk to each other by writing JSON files to shared directories. Writes use the temp-file-then-rename trick so readers never see a torn write. No sockets, no message brokers, no shared memory.
2. **Tickets with explicit state** (Decision 9) plus **manifest discipline** (Pattern D). Every long-running operation gets a ticket directory with a state machine (`pending → running → success | skipped | error`). `success` requires a `manifest.json` whose sha256 checksums verify against the actual output files. This is the antidote to LLM hallucinated success — the framework catches "I wrote the file" reports that weren't backed by actual writes.

## Why these are bundled

Separately they're interesting; together they're what makes long-running operations in sovereign-agent *correct*. An operation writes a result file, emits a ticket manifest listing that file's sha256, and the framework verifies the manifest before accepting the operation as successful. Then a short LLM-readable summary (Pattern B) goes in `summary.md`, and the agent reads *that* instead of the raw output — keeping its context focused on the next decision.

The cost is one extra second of polling latency for IPC. That's invisible for agent systems and unacceptable for high-frequency trading. Pick the cost that fits the problem.

## Status

Both modules are implemented and well-tested:

- `sovereign_agent.ipc` — 10 tests in `tests/unit/test_ipc.py` covering atomic writes, chronological ordering, `_close` sentinel, quarantine of malformed files, the fail-closed rule on duplicate handoff files, and `session_complete.json` dispatch.
- `sovereign_agent.tickets` — 11 tests in `tests/unit/test_tickets.py` covering state transitions, manifest verification (including tamper detection and missing-file detection), summary discipline, and ID uniqueness.

The `starter.py` / `tests.py` / `demo.py` triple is future work.

## Run the existing tests

```bash
pytest tests/unit/test_ipc.py tests/unit/test_tickets.py -v
```
