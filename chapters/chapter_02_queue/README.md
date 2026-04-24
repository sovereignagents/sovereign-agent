# Chapter 2 — SessionQueue

## What you'll build

A `SessionQueue` class that decides which session's work runs when. It gives you three guarantees:

1. **Per-session serialization.** At most one worker per session at a time. Memory writes don't race.
2. **Global concurrency cap.** No more than `max_concurrent` sessions running simultaneously. 100 sessions waking up at once doesn't spawn 100 workers.
3. **Retry with exponential backoff.** Transient failures (rate limits, network blips) get retried at 5s / 10s / 20s / 40s / 80s up to `MAX_RETRIES`, then the session is marked failed.

Plus two behaviors that make always-on systems correct:

- **Idle preemption via `_close` sentinel** (Decision 4). When a higher-priority task arrives for a session whose worker is idle, the queue writes a `_close` file into the worker's input dir. The worker sees it on its next poll and exits cleanly. We *never* `SIGKILL` a worker that's in the middle of writing files.
- **Graceful shutdown that detaches** (Decision 8). `shutdown()` stops accepting new work but leaves running workers alone. They finish their current task and exit via their own idle timeouts. On the next orchestrator startup, any session whose state isn't terminal is resumed.

## Why this is the second chapter

The queue is where "always-on" becomes real. Chapter 1 gave you a place to put state; Chapter 2 gives you the thing that actually runs work against that state, continuously, without races and without losing work to restarts.

## Status

The solution (re-exporting `sovereign_agent.session.queue`) is complete and covered by 7 tests in `tests/unit/test_queue.py`. The `starter.py` / `tests.py` / `demo.py` triple following the Chapter 1 template is future work tracked on the release checklist — the reference implementation and its tests already exist and can guide that work directly.

## Run the existing tests

```bash
pytest tests/unit/test_queue.py -v
```
