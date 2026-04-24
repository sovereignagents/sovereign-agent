"""Drift-corrected scheduler (Decision 6).

Recurring tasks have their next-run time anchored to their SCHEDULED time,
not to wall-clock now(). This prevents cumulative drift: a "every 10 minutes"
task fires at minute 0, 10, 20, 30, ... even if individual runs take a
second or two.

When intervals are missed (e.g. the system slept), we skip to the next
future interval rather than running all missed intervals back-to-back.

See docs/architecture.md §2.10.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

log = logging.getLogger(__name__)


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
    # Scheduled-task consumers may want this forwarded to the SessionQueue
    # rather than invoked directly; see DriftCorrectedScheduler.run for the hook.
    session_id: str | None = None
    metadata: dict = field(default_factory=dict)


def compute_next_run(task: ScheduledTask, now: datetime | None = None) -> datetime | None:
    """Compute the next run time for `task`.

    - For `once`: return None after the first run (caller responsibility to
      detect this and unregister).
    - For `interval`: anchor to task.next_run and advance by interval_s until
      we land in the future. Returns that future time.
    - For `cron`: use croniter with the task's timezone.

    `now` defaults to datetime.now(timezone.utc).
    """
    now = now or datetime.now(tz=UTC)

    if task.schedule_type == "once":
        # Caller sets next_run at registration. We return it unchanged the
        # first time and None thereafter.
        if task.next_run is None:
            return None
        if now < task.next_run:
            return task.next_run
        return None

    if task.schedule_type == "interval":
        if task.interval_s is None or task.interval_s <= 0:
            raise ValueError(f"interval task {task.id!r} must have a positive interval_s")
        # Anchor: if next_run was never set, start from now rounded forward
        # by interval_s so the first fire is interval_s away (not immediate).
        if task.next_run is None:
            return now + timedelta(seconds=task.interval_s)
        nxt = task.next_run + timedelta(seconds=task.interval_s)
        # Skip missed intervals in one jump.
        while nxt <= now:
            nxt += timedelta(seconds=task.interval_s)
        return nxt

    if task.schedule_type == "cron":
        if task.cron_expr is None:
            raise ValueError(f"cron task {task.id!r} must have a cron_expr")
        try:
            from croniter import croniter
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "croniter is required for cron-type scheduled tasks. "
                "Install the base sovereign-agent dependencies or add croniter."
            ) from exc
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(task.timezone)
        except Exception:  # pragma: no cover
            tz = UTC
        local_now = now.astimezone(tz)
        it = croniter(task.cron_expr, local_now)
        nxt_local = it.get_next(datetime)
        return nxt_local.astimezone(UTC)

    raise ValueError(f"unknown schedule_type: {task.schedule_type!r}")


class DriftCorrectedScheduler:
    """Scheduler that manages a set of recurring tasks.

    On each tick, any task whose next_run <= now is dispatched. By default,
    dispatch means "call task.fn() directly as an asyncio task". Callers who
    want to route through the SessionQueue wrap their task's fn accordingly.
    """

    def __init__(self, poll_interval_s: float = 1.0) -> None:
        self.tasks: dict[str, ScheduledTask] = {}
        self.poll_interval_s = poll_interval_s
        self._running = False

    def register(self, task: ScheduledTask) -> None:
        if task.next_run is None:
            task.next_run = compute_next_run(task)
        self.tasks[task.id] = task
        log.info(
            "scheduler: registered %s (type=%s, next_run=%s)",
            task.id,
            task.schedule_type,
            task.next_run,
        )

    def unregister(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)

    async def run(self) -> None:
        self._running = True
        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self.poll_interval_s)
        finally:
            self._running = False

    async def _tick(self) -> None:
        now = datetime.now(tz=UTC)
        for task in list(self.tasks.values()):
            if not task.enabled:
                continue
            if task.next_run is None or task.next_run > now:
                continue
            # Fire.
            asyncio.create_task(self._fire(task))
            # Advance schedule.
            if task.schedule_type == "once":
                self.unregister(task.id)
            else:
                task.next_run = compute_next_run(task, now)

    async def _fire(self, task: ScheduledTask) -> None:
        if task.fn is None:
            return
        try:
            await task.fn()
        except Exception:  # noqa: BLE001
            log.exception("scheduled task %s failed", task.id)

    async def shutdown(self) -> None:
        self._running = False


__all__ = [
    "ScheduleType",
    "ScheduledTask",
    "DriftCorrectedScheduler",
    "compute_next_run",
]
