"""Chapter 4 demo — drift correction and missed-interval skipping.

Run:

    python -m chapters.chapter_04_scheduler.demo

Shows two behaviors of compute_next_run:

  1. ANCHORING: a task scheduled for 12:00:00 with interval 60s, computed at
     12:00:03, fires at 12:01:00 — not 12:01:03. No cumulative drift.

  2. SKIP-AHEAD: a task that should have fired 10 minutes ago returns the
     NEXT FUTURE slot, not 10 retroactive runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from chapters.chapter_04_scheduler.solution import ScheduledTask, compute_next_run


def utc(h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 4, 18, h, m, s, tzinfo=UTC)


def main() -> None:
    print("=== Drift correction ===")
    anchor = utc(12, 0, 0)
    task = ScheduledTask(id="t", schedule_type="interval", interval_s=60, next_run=anchor)
    # Clock has drifted by 3 seconds past the scheduled fire time.
    now = anchor + timedelta(seconds=3)
    nxt = compute_next_run(task, now)
    print(f"Scheduled fire time:   {anchor.isoformat()}")
    print(f"Clock 'now':           {now.isoformat()}")
    print(f"Next fire:             {nxt.isoformat()}")
    print(f"Anchored (not 12:01:03): {nxt == anchor + timedelta(seconds=60)}")

    print()
    print("=== Missed intervals skipped ===")
    anchor = utc(12, 0, 0)
    task = ScheduledTask(id="t", schedule_type="interval", interval_s=60, next_run=anchor)
    # Simulate the laptop sleeping for 10 minutes.
    now = anchor + timedelta(minutes=10, seconds=25)
    nxt = compute_next_run(task, now)
    gap = (nxt - anchor).total_seconds()
    n_skipped = int(gap / 60) - 1
    print(f"Scheduled fire time:   {anchor.isoformat()}")
    print(f"Clock 'now':           {now.isoformat()}  (10m25s late)")
    print(f"Next fire:             {nxt.isoformat()}")
    print(f"Skipped {n_skipped} missed intervals (single future fire, not 10 back-to-back)")

    print()
    print("=== Comparison: what a naive scheduler would do ===")
    naive_next = now + timedelta(seconds=60)
    print(f"Naive (now + interval): {naive_next.isoformat()}   <-- drifts forward")
    print(f"Anchored:               {nxt.isoformat()}          <-- stays on the minute")


if __name__ == "__main__":
    main()
