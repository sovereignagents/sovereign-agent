# Lessons

Dated writeups of experiments against sovereign-agent. Each lesson implements a technique (usually from a recent paper), compares it against a baseline on standard scenarios, and writes up what was learned.

Lessons are the **research vehicle** for the framework. See SOW §4 for the full rationale. The short version: without this feed, every paper's technique lives in isolation — a PDF, maybe a reference implementation, nobody builds on any of them. With the feed, each paper gets implemented against a real always-on agent, compared against a baseline on the same scenarios every other lesson used, and archived in a location anyone can clone and run.

## Adding a lesson

1. Copy `_template/` to `lessons/YYYY-MM-<slug>/` (where `<slug>` is something like `rag-baseline` or `reflexion-memory`).
2. Implement the technique as a new extension under the appropriate `sovereign_agent/…` directory. Your lesson's `implementation.py` re-exports the new module.
3. Write `compare.py`: run one or more scenarios with the baseline, then with the new variant, and record metrics.
4. Fill in `README.md`: paper reference, hypothesis, implementation notes, setup, results, what was learned, when to use this.
5. Fill in `LESSON.yaml` with the machine-readable metadata (it's what the top-level `lessons/README.md` index regenerates from).
6. (Optional) record a teaching video and add its URL to `LESSON.yaml`.

## Current lessons

*No published lessons yet.* The framework is v0.1.0 alpha; the first lessons land once the v1.0 release checklist clears. The template below is ready for use.

## Deprecation

Lessons are append-only. When a later lesson invalidates an earlier one, the earlier gets a deprecation notice at the top of its README and `deprecated: true` in `LESSON.yaml`. It is **not deleted**. The lessons feed is a research log: its value comes partly from faithfully recording what was tried, including what didn't work.
