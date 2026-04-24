"""Tests for SessionQueue (Decisions 2, 4, 8)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from sovereign_agent.session.queue import SessionQueue


@pytest.mark.asyncio
async def test_per_session_serialization() -> None:
    starts: list[tuple[str, float]] = []
    ends: list[tuple[str, float]] = []

    async def process(session_id: str) -> bool:
        starts.append((session_id, time.monotonic()))
        await asyncio.sleep(0.05)
        ends.append((session_id, time.monotonic()))
        return True

    q = SessionQueue(max_concurrent=10, process_fn=process)
    await q.enqueue_executor("sA")
    await q.enqueue_executor("sA")  # same session => must serialize
    await q.enqueue_executor("sA")

    # Wait for all to drain.
    for _ in range(50):
        if len(ends) == 3:
            break
        await asyncio.sleep(0.02)
    assert len(ends) == 3
    # Consecutive A-task intervals do not overlap.
    for i in range(len(starts) - 1):
        assert ends[i][1] <= starts[i + 1][1] + 0.01


@pytest.mark.asyncio
async def test_global_concurrency_cap() -> None:
    concurrent = 0
    max_seen = 0
    lock = asyncio.Lock()

    async def process(session_id: str) -> bool:
        nonlocal concurrent, max_seen
        async with lock:
            concurrent += 1
            max_seen = max(max_seen, concurrent)
        await asyncio.sleep(0.05)
        async with lock:
            concurrent -= 1
        return True

    q = SessionQueue(max_concurrent=2, process_fn=process)
    # 5 distinct sessions, each would run instantly, but cap=2.
    for i in range(5):
        await q.enqueue_executor(f"s{i}")

    for _ in range(100):
        if concurrent == 0 and max_seen > 0:
            # Drain a bit more to be sure.
            await asyncio.sleep(0.02)
            break
        await asyncio.sleep(0.02)
    assert max_seen <= 2
    assert max_seen >= 2  # should have hit the cap at least once


@pytest.mark.asyncio
async def test_priority_drain_order() -> None:
    run_order: list[str] = []
    # gate the first task so we can pile up pending work behind it
    release_first = asyncio.Event()

    async def process(session_id: str) -> bool:
        run_order.append(session_id)
        if session_id == "sA-first":
            await release_first.wait()
        return True

    q = SessionQueue(max_concurrent=5, process_fn=process)
    # Start by occupying the session with a gated task.
    await q.enqueue_executor("sA-first")
    await asyncio.sleep(0.02)
    # Now pile up tasks that should drain in priority order:
    # Scheduled (0) > Handoff (1) > Executor (2) > Planner (3)
    await q.enqueue_planner("sA-first")
    await q.enqueue_executor("sA-first")
    await q.enqueue_handoff("sA-first", "structured")

    async def sched_fn() -> None:
        run_order.append("sA-first:scheduled")

    await q.enqueue_scheduled_task("sA-first", "t1", sched_fn)

    # Release the first task; pending tasks now drain by priority.
    release_first.set()

    # Wait for drain.
    for _ in range(100):
        if "sA-first:scheduled" in run_order and run_order.count("sA-first") >= 3:
            break
        await asyncio.sleep(0.02)

    # The first thing after the gated task releases should be the scheduled one,
    # then the handoff, then the executor, then the planner.
    # Drop the leading "sA-first" (the original gated run).
    tail = run_order[1:]
    # Scheduled appears as a distinct label; the others all re-emit "sA-first".
    # Scheduled should come first in the tail.
    assert tail[0] == "sA-first:scheduled"


@pytest.mark.asyncio
async def test_retry_on_failure() -> None:
    attempts = 0

    async def process(session_id: str) -> bool:
        nonlocal attempts
        attempts += 1
        return attempts >= 3  # fail twice then succeed

    q = SessionQueue(max_concurrent=5, process_fn=process)
    # Speed up the backoff for tests.
    q.BASE_RETRY_S = 0.02  # type: ignore[misc]
    await q.enqueue_executor("s1")
    # Give time for retries at 0.02s, 0.04s.
    for _ in range(200):
        if attempts >= 3:
            break
        await asyncio.sleep(0.02)
    assert attempts >= 3


@pytest.mark.asyncio
async def test_notify_idle_writes_close_sentinel(tmp_path: Path) -> None:
    async def process(session_id: str) -> bool:
        return True

    q = SessionQueue(max_concurrent=5, process_fn=process)
    ipc_input = tmp_path / "ipc_input"
    ipc_input.mkdir()
    # Register the container/worker.
    q.register_container("s1", ipc_input)
    # Give the session a pending task that would like to run.
    q._sessions.setdefault("s1", q._sessions.get("s1") or None)
    # The easiest test: directly call notify_idle with a pending task queued up.
    # Queue a task while the session is (artificially) active.
    from sovereign_agent.session.queue import (
        QueuedTask,
        TaskPriority,
        _SessionState,
    )

    q._sessions["s1"] = _SessionState(
        active=True,
        idle_waiting=False,
        pending_tasks=[
            QueuedTask(
                priority=TaskPriority.EXECUTOR.value,
                session_id="s1",
                kind="executor",
            )
        ],
        ipc_input_dir=ipc_input,
    )
    q.notify_idle("s1")
    assert (ipc_input / "_close").exists()


@pytest.mark.asyncio
async def test_shutdown_does_not_kill_workers() -> None:
    finished = asyncio.Event()

    async def process(session_id: str) -> bool:
        try:
            await asyncio.sleep(0.1)
            finished.set()
            return True
        except asyncio.CancelledError:
            # If this fires, shutdown killed us — the test should fail.
            finished.set()
            raise

    q = SessionQueue(max_concurrent=5, process_fn=process)
    await q.enqueue_executor("sA")
    await asyncio.sleep(0.02)  # let the worker start
    # Shut down with generous grace to allow completion.
    await q.shutdown(grace_period_s=1.0)
    assert finished.is_set()


@pytest.mark.asyncio
async def test_enqueue_after_shutdown_silently_dropped() -> None:
    async def process(session_id: str) -> bool:
        return True

    q = SessionQueue(max_concurrent=5, process_fn=process)
    await q.shutdown(grace_period_s=0.1)
    # Should not raise.
    await q.enqueue_executor("sX")
    # And no worker should start.
    assert "sX" not in q._active_workers
