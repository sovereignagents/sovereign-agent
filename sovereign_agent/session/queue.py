"""SessionQueue: the central coordinator.

Decisions 2 (three guarantees), 4 (idle preemption via sentinel), 8 (graceful
shutdown detaches rather than kills). See docs/architecture.md §2.4.

Guarantees:
  1. Per-session serialization: at most one worker per session at a time.
  2. Global concurrency cap: no more than `max_concurrent` sessions running.
  3. Retry with exponential backoff: transient failures don't take down a session.

Plus:
  4. Priority-draining per session (SCHEDULED > HANDOFF > EXECUTOR > PLANNER).
  5. Idle preemption: higher-priority tasks can preempt an idle worker via
     the `_close` sentinel (the worker exits cleanly, it is not killed).
  6. Graceful shutdown: `shutdown()` detaches active workers (does not kill
     them); the next orchestrator startup resumes unfinished sessions.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import ClassVar

from sovereign_agent.ipc.protocol import write_close_sentinel

log = logging.getLogger(__name__)


class TaskPriority(IntEnum):
    """Lower integer = higher priority. Drain order is ascending."""

    SCHEDULED = 0
    HANDOFF = 1
    EXECUTOR = 2
    PLANNER = 3


ProcessFn = Callable[[str], Awaitable[bool]]
"""(session_id) -> success. True => task completed normally. False => retry."""

ScheduledFn = Callable[[], Awaitable[None]]


@dataclass(order=True)
class QueuedTask:
    priority: int
    session_id: str = field(compare=False)
    kind: str = field(compare=False)  # "planner" | "executor" | "handoff" | "scheduled"
    scheduled_fn: ScheduledFn | None = field(default=None, compare=False)
    task_id: str | None = field(default=None, compare=False)
    direction: str | None = field(default=None, compare=False)  # for handoffs


@dataclass
class _SessionState:
    active: bool = False
    idle_waiting: bool = False
    is_scheduled_task: bool = False
    pending_tasks: list[QueuedTask] = field(default_factory=list)
    ipc_input_dir: Path | None = None
    retry_count: int = 0


class SessionQueue:
    """Single-process, asyncio-based queue.

    Uses one asyncio.Lock to serialize state transitions. The lock is released
    before running user code so that other enqueues do not block. Worker
    execution uses asyncio.create_task so that `enqueue_*` returns quickly.
    """

    MAX_RETRIES: ClassVar[int] = 5
    BASE_RETRY_S: ClassVar[float] = 5.0

    def __init__(
        self,
        max_concurrent: int = 5,
        process_fn: ProcessFn | None = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self._process_fn: ProcessFn | None = process_fn
        self._lock = asyncio.Lock()
        self._sessions: dict[str, _SessionState] = {}
        self._waiting: list[QueuedTask] = []
        self._active_count = 0
        self._shutting_down = False
        self._active_workers: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_process_fn(self, fn: ProcessFn) -> None:
        self._process_fn = fn

    # ------------------------------------------------------------------
    # Enqueue methods
    # ------------------------------------------------------------------
    async def enqueue_planner(self, session_id: str) -> None:
        await self._enqueue(
            QueuedTask(priority=TaskPriority.PLANNER.value, session_id=session_id, kind="planner")
        )

    async def enqueue_executor(self, session_id: str) -> None:
        await self._enqueue(
            QueuedTask(priority=TaskPriority.EXECUTOR.value, session_id=session_id, kind="executor")
        )

    async def enqueue_handoff(self, session_id: str, direction: str) -> None:
        await self._enqueue(
            QueuedTask(
                priority=TaskPriority.HANDOFF.value,
                session_id=session_id,
                kind="handoff",
                direction=direction,
            )
        )

    async def enqueue_scheduled_task(self, session_id: str, task_id: str, fn: ScheduledFn) -> None:
        await self._enqueue(
            QueuedTask(
                priority=TaskPriority.SCHEDULED.value,
                session_id=session_id,
                kind="scheduled",
                scheduled_fn=fn,
                task_id=task_id,
            )
        )

    async def _enqueue(self, task: QueuedTask) -> None:
        if self._shutting_down:
            log.info("dropping task for session %s: queue is shutting down", task.session_id)
            return
        async with self._lock:
            sess = self._sessions.setdefault(task.session_id, _SessionState())

            if sess.active:
                # Serialize: add to this session's pending list, sorted by priority.
                sess.pending_tasks.append(task)
                sess.pending_tasks.sort(key=lambda t: t.priority)
                # If the active worker is idle and a higher-priority task is waiting,
                # ask it to wind down cleanly (idle preemption).
                if sess.idle_waiting and any(
                    t.priority < sess.pending_tasks[-1].priority + 1 for t in sess.pending_tasks
                ):
                    self._send_close(sess)
                return

            if self._active_count >= self.max_concurrent:
                # Hold in global waiting queue.
                self._waiting.append(task)
                self._waiting.sort(key=lambda t: t.priority)
                return

            # Otherwise, start immediately.
            self._active_count += 1
            sess.active = True
            sess.is_scheduled_task = task.kind == "scheduled"
        # Launch outside the lock.
        runner = asyncio.create_task(self._run_task(task))
        self._active_workers[task.session_id] = runner

    # ------------------------------------------------------------------
    # Container / worker registration
    # ------------------------------------------------------------------
    def register_container(self, session_id: str, ipc_input_dir: Path) -> None:
        """Called by the worker spawner to record where _close should be written."""
        sess = self._sessions.setdefault(session_id, _SessionState())
        sess.ipc_input_dir = ipc_input_dir

    def unregister_container(self, session_id: str) -> None:
        sess = self._sessions.get(session_id)
        if sess is not None:
            sess.ipc_input_dir = None

    def notify_idle(self, session_id: str) -> None:
        """The worker is idle — if higher-priority work is waiting, ask it to exit."""
        sess = self._sessions.get(session_id)
        if sess is None:
            return
        sess.idle_waiting = True
        if sess.pending_tasks:
            self._send_close(sess)

    def _send_close(self, sess: _SessionState) -> None:
        if sess.ipc_input_dir is None:
            return
        try:
            write_close_sentinel(sess.ipc_input_dir)
        except Exception:  # noqa: BLE001
            log.exception("failed to write _close sentinel")

    # ------------------------------------------------------------------
    # Running tasks
    # ------------------------------------------------------------------
    async def _run_task(self, task: QueuedTask) -> None:
        sid = task.session_id
        sess = self._sessions[sid]
        try:
            if task.kind == "scheduled" and task.scheduled_fn is not None:
                await task.scheduled_fn()
                success = True
            else:
                if self._process_fn is None:
                    raise RuntimeError("SessionQueue: process_fn is not set")
                success = await self._process_fn(sid)
        except Exception:  # noqa: BLE001
            log.exception("task raised for session %s (kind=%s)", sid, task.kind)
            success = False

        if success:
            sess.retry_count = 0
            await self._after_task(sid, completed_task=task)
        else:
            await self._handle_failure(sid, task)

    async def _handle_failure(self, sid: str, task: QueuedTask) -> None:
        sess = self._sessions[sid]
        sess.retry_count += 1
        if sess.retry_count > self.MAX_RETRIES:
            log.error(
                "session %s: max retries (%d) exceeded; giving up",
                sid,
                self.MAX_RETRIES,
            )
            sess.retry_count = 0
            await self._after_task(sid, completed_task=task)
            return
        # Exponential backoff: 5s, 10s, 20s, 40s, 80s.
        delay = self.BASE_RETRY_S * (2 ** (sess.retry_count - 1))
        log.warning(
            "session %s failed (attempt %d); retrying in %.1fs",
            sid,
            sess.retry_count,
            delay,
        )

        # Schedule the retry after the backoff delay, without blocking other
        # sessions. Release this session's slot during the wait.
        await self._release_slot(sid)

        async def _delayed_retry() -> None:
            await asyncio.sleep(delay)
            if self._shutting_down:
                return
            # Re-enqueue the same kind of task. We don't reuse the original
            # QueuedTask object because its priority may have shifted.
            if task.kind == "planner":
                await self.enqueue_planner(sid)
            elif task.kind == "executor":
                await self.enqueue_executor(sid)
            elif task.kind == "handoff" and task.direction is not None:
                await self.enqueue_handoff(sid, task.direction)
            elif task.kind == "scheduled" and task.scheduled_fn is not None and task.task_id:
                await self.enqueue_scheduled_task(sid, task.task_id, task.scheduled_fn)

        asyncio.create_task(_delayed_retry())

    async def _release_slot(self, sid: str) -> None:
        async with self._lock:
            sess = self._sessions.get(sid)
            if sess is not None:
                sess.active = False
                sess.idle_waiting = False
            self._active_count = max(0, self._active_count - 1)
            self._active_workers.pop(sid, None)
            self._maybe_start_from_waiting()

    async def _after_task(self, sid: str, completed_task: QueuedTask) -> None:
        async with self._lock:
            sess = self._sessions.get(sid)
            if sess is None:
                return
            self._active_workers.pop(sid, None)
            if sess.pending_tasks:
                # Run the highest-priority pending task for this session next.
                sess.pending_tasks.sort(key=lambda t: t.priority)
                next_task = sess.pending_tasks.pop(0)
                sess.idle_waiting = False
                sess.is_scheduled_task = next_task.kind == "scheduled"
                # Stay active.
            else:
                sess.active = False
                sess.idle_waiting = False
                self._active_count = max(0, self._active_count - 1)
                next_task = None

            if next_task is None:
                self._maybe_start_from_waiting()
                return

        # Run the next pending task for this session, outside the lock.
        runner = asyncio.create_task(self._run_task(next_task))
        self._active_workers[sid] = runner

    def _maybe_start_from_waiting(self) -> None:
        """Pull the highest-priority waiting task, if capacity allows.

        Must be called while holding self._lock.
        """
        while self._waiting and self._active_count < self.max_concurrent:
            self._waiting.sort(key=lambda t: t.priority)
            # Find the first waiting task whose session isn't currently active.
            picked: QueuedTask | None = None
            for i, wt in enumerate(self._waiting):
                sess = self._sessions.get(wt.session_id)
                if sess is None or not sess.active:
                    picked = wt
                    del self._waiting[i]
                    break
            if picked is None:
                return
            sess = self._sessions.setdefault(picked.session_id, _SessionState())
            sess.active = True
            sess.is_scheduled_task = picked.kind == "scheduled"
            self._active_count += 1
            runner = asyncio.create_task(self._run_task(picked))
            self._active_workers[picked.session_id] = runner

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    async def shutdown(self, grace_period_s: float = 30.0) -> None:
        """Graceful shutdown: stop accepting new work, detach active workers,
        wait briefly for them to finish, then exit.

        Does NOT kill workers (Decision 8). Active tasks continue to run; on
        the next orchestrator startup, any session whose state isn't terminal
        will be resumed.
        """
        self._shutting_down = True
        active = list(self._active_workers.items())
        if active:
            log.info(
                "shutdown: %d active worker(s) detached (not killed): %s",
                len(active),
                ", ".join(sid for sid, _ in active),
            )
        # Give them a chance to complete.
        try:
            await asyncio.wait_for(
                asyncio.gather(*(t for _, t in active), return_exceptions=True),
                timeout=grace_period_s,
            )
        except TimeoutError:
            log.info(
                "shutdown: grace period elapsed; %d worker(s) still running — leaving them",
                sum(1 for _, t in active if not t.done()),
            )


__all__ = ["SessionQueue", "TaskPriority", "QueuedTask"]
