"""Chapter 4 starter — drift-corrected scheduler.

The interesting function is compute_next_run. It has two non-obvious
behaviors:

  1. ANCHORING: for interval tasks, anchor to task.next_run, NOT wall-clock
     now(). A task scheduled at 12:00:00 with interval 60s, computed at
     12:00:03, should return 12:01:00 — not 12:01:03.

  2. SKIP-AHEAD: when the system sleeps through many intervals, advance
     to the next FUTURE interval in one jump. Do not run missed intervals
     back-to-back.

Run `pytest chapters/chapter_04_scheduler/tests.py -v` to check.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ScheduleType = Literal["once", "interval", "cron"]

TaskFn = Callable[[], Awaitable[None]]


@dataclass
class ScheduledTask:
    id: str
    schedule_type: ScheduleType
    fn: TaskFn | None = None
    interval_s: int | None = None
    cron_expr: str | None = None
    timezone: str = "UTC"
    next_run: datetime | None = None
    enabled: bool = True


def compute_next_run(task: ScheduledTask, now: datetime | None = None) -> datetime | None:
    """Compute the next run time for `task`.

    - once: returns task.next_run if it's still in the future, else None.
    - interval: anchor to task.next_run; add interval_s repeatedly until
      the result is strictly in the future.
    - cron: use croniter with the task's timezone.
    """
    raise NotImplementedError
