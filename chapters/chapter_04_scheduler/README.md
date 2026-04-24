# Chapter 4 — Drift-corrected scheduler

## What you'll build

A scheduler for recurring tasks — memory consolidation every 10 minutes, trace flushing every 30 seconds, idle session cleanup every hour — that does two subtle things right that every naive scheduler does wrong:

1. **Anchoring vs drift.** A "fire every 60 seconds" task anchors its next run to the *scheduled* time, not to `now()`. So a task that ran slightly late at 12:00:03 fires next at 12:01:00, not 12:01:03. Over a day this is the difference between a midnight cleanup that fires at 00:00:00 and one that drifts to 00:07:32.
2. **Skip-ahead on missed intervals.** If the system was asleep for 30 minutes, we do NOT run the 30 missed firings back-to-back on wake. We skip to the next future interval and run once.

Both fixes live in a five-line `compute_next_run` function. Both prevent classes of bug that take days to diagnose the first time they bite you.

## Why this is a chapter and not a lesson

Scheduling is load-bearing for the "always-on" part of always-on agents. Memory consolidation, trace flushing, orphan cleanup — these are the housekeeping tasks that make the framework robust across weeks and months of uptime. Getting them wrong looks fine in a demo and fails in production.

## Status

Implemented and tested. 8 tests in `tests/unit/test_scheduler.py` cover anchoring, skip-ahead, `once` tasks, cron with timezones, registration, and live firing.

The `starter.py` / `tests.py` / `demo.py` triple is future work.

## Run the existing tests

```bash
pytest tests/unit/test_scheduler.py -v
```
