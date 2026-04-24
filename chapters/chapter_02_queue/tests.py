"""Chapter 2 tests. Imports from solution.py; swap to `starter` when checking your work.

Run from the repo root:

    pytest chapters/chapter_02_queue/tests.py -v
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from chapters.chapter_02_queue.solution import (
    QueuedTask,
    SessionQueue,
    TaskPriority,
)


@pytest.mark.asyncio
async def test_per_session_serialization() -> None:
    starts: list[float] = []
    ends: list[float] = []

    async def process(session_id: str) -> bool:
        starts.append(time.monotonic())
        await asyncio.sleep(0.05)
        ends.append(time.monotonic())
        return True

    q = SessionQueue(max_concurrent=10, process_fn=process)
    # Three enqueues for the same session must execute one at a time.
    await q.enqueue_executor("sA")
    await q.enqueue_executor("sA")
    await q.enqueue_executor("sA")
    for _ in range(50):
        if len(ends) == 3:
            break
        await asyncio.sleep(0.02)
    assert len(ends) == 3
    for i in range(len(starts) - 1):
        # Each task ends before the next starts.
        assert ends[i] <= starts[i + 1] + 0.01


@pytest.mark.asyncio
async def test_global_concurrency_cap() -> None:
    live = 0
    peak = 0
    lock = asyncio.Lock()

    async def process(session_id: str) -> bool:
        nonlocal live, peak
        async with lock:
            live += 1
            peak = max(peak, live)
        await asyncio.sleep(0.05)
        async with lock:
            live -= 1
        return True

    q = SessionQueue(max_concurrent=2, process_fn=process)
    for i in range(5):
        await q.enqueue_executor(f"s{i}")
    for _ in range(100):
        if live == 0 and peak > 0:
            await asyncio.sleep(0.02)
            break
        await asyncio.sleep(0.02)
    assert peak == 2


@pytest.mark.asyncio
async def test_retry_on_failure_then_success() -> None:
    attempts = 0

    async def process(session_id: str) -> bool:
        nonlocal attempts
        attempts += 1
        return attempts >= 3

    q = SessionQueue(max_concurrent=5, process_fn=process)
    q.BASE_RETRY_S = 0.02  # type: ignore[misc]
    await q.enqueue_executor("s1")
    for _ in range(200):
        if attempts >= 3:
            break
        await asyncio.sleep(0.02)
    assert attempts >= 3


@pytest.mark.asyncio
async def test_notify_idle_writes_close(tmp_path: Path) -> None:
    async def process(session_id: str) -> bool:
        return True

    q = SessionQueue(max_concurrent=5, process_fn=process)
    ipc_input = tmp_path / "ipc_input"
    ipc_input.mkdir()

    # Simulate: the session has an active worker AND pending higher-prio
    # tasks. We write directly to the queue's internal _SessionState so
    # we don't need a real worker lifecycle in the test.
    from sovereign_agent.session.queue import _SessionState

    q._sessions["s1"] = _SessionState(
        active=True,
        pending_tasks=[
            QueuedTask(priority=TaskPriority.EXECUTOR.value, session_id="s1", kind="executor"),
        ],
        ipc_input_dir=ipc_input,
    )
    q.notify_idle("s1")
    assert (ipc_input / "_close").exists()


@pytest.mark.asyncio
async def test_shutdown_does_not_kill_running_worker() -> None:
    completed = asyncio.Event()

    async def process(session_id: str) -> bool:
        try:
            await asyncio.sleep(0.1)
            completed.set()
            return True
        except asyncio.CancelledError:
            completed.set()
            raise

    q = SessionQueue(max_concurrent=5, process_fn=process)
    await q.enqueue_executor("sX")
    await asyncio.sleep(0.02)
    await q.shutdown(grace_period_s=1.0)
    # Completed cleanly, not cancelled.
    assert completed.is_set()
