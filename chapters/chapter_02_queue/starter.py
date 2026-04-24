"""Chapter 2 starter — fill in the SessionQueue.

Your job is to implement a SessionQueue with three guarantees:

  1. Per-session serialization: at most one worker per session at a time.
  2. Global concurrency cap: no more than `max_concurrent` sessions running.
  3. Retry with exponential backoff: transient failures get retried at
     BASE_RETRY_S * 2^(attempt-1), up to MAX_RETRIES.

Plus idle preemption (write _close into the worker's ipc_input_dir when
higher-priority work arrives for the same session) and graceful shutdown
(detach running workers, don't kill them).

Run `pytest chapters/chapter_02_queue/tests.py -v` to check your work.
Compare to `solution.py` when you're done.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import ClassVar


class TaskPriority(IntEnum):
    SCHEDULED = 0
    HANDOFF = 1
    EXECUTOR = 2
    PLANNER = 3


ProcessFn = Callable[[str], Awaitable[bool]]


@dataclass(order=True)
class QueuedTask:
    priority: int
    session_id: str = field(compare=False)
    kind: str = field(compare=False)
    scheduled_fn: Callable[[], Awaitable[None]] | None = field(default=None, compare=False)
    task_id: str | None = field(default=None, compare=False)
    direction: str | None = field(default=None, compare=False)


@dataclass
class _SessionState:
    active: bool = False
    idle_waiting: bool = False
    pending_tasks: list[QueuedTask] = field(default_factory=list)
    ipc_input_dir: Path | None = None
    retry_count: int = 0


class SessionQueue:
    MAX_RETRIES: ClassVar[int] = 5
    BASE_RETRY_S: ClassVar[float] = 5.0

    def __init__(
        self,
        max_concurrent: int = 5,
        process_fn: ProcessFn | None = None,
    ) -> None:
        raise NotImplementedError("fill in __init__")

    def set_process_fn(self, fn: ProcessFn) -> None:
        raise NotImplementedError

    async def enqueue_planner(self, session_id: str) -> None:
        raise NotImplementedError

    async def enqueue_executor(self, session_id: str) -> None:
        raise NotImplementedError

    async def enqueue_handoff(self, session_id: str, direction: str) -> None:
        raise NotImplementedError

    async def enqueue_scheduled_task(
        self,
        session_id: str,
        task_id: str,
        fn: Callable[[], Awaitable[None]],
    ) -> None:
        raise NotImplementedError

    def register_container(self, session_id: str, ipc_input_dir: Path) -> None:
        raise NotImplementedError

    def notify_idle(self, session_id: str) -> None:
        """When this session's worker is idle and higher-priority work is
        waiting, write _close into its ipc_input_dir so it exits cleanly."""
        raise NotImplementedError

    async def shutdown(self, grace_period_s: float = 30.0) -> None:
        """Stop accepting new work. Do NOT cancel/kill running workers.
        Wait up to grace_period_s then return."""
        raise NotImplementedError
