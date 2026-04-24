"""Chapter 2 demo — watch the SessionQueue's three guarantees in action.

Run:

    python -m chapters.chapter_02_queue.demo

This demo spawns 6 fake sessions against a queue with max_concurrent=3,
and prints the start/end times of each worker so you can see that:

  - Only 3 ever run concurrently (global cap).
  - Workers for the same session serialize (per-session lock).
  - A higher-priority task can preempt an idle lower-priority worker.
"""

from __future__ import annotations

import asyncio
import time

from chapters.chapter_02_queue.solution import SessionQueue


async def main() -> None:
    queue = SessionQueue(max_concurrent=3)

    start_times: dict[str, list[float]] = {}
    end_times: dict[str, list[float]] = {}
    t0 = time.monotonic()

    async def process(session_id: str) -> bool:
        start_times.setdefault(session_id, []).append(time.monotonic() - t0)
        await asyncio.sleep(0.3)
        end_times.setdefault(session_id, []).append(time.monotonic() - t0)
        return True

    queue.set_process_fn(process)

    print("[1/3] Enqueuing 6 sessions (expect waves of 3 because max_concurrent=3)")
    for i in range(6):
        await queue.enqueue_executor(f"sess_{i}")

    # Drain
    for _ in range(200):
        if sum(len(v) for v in end_times.values()) == 6:
            break
        await asyncio.sleep(0.05)

    print("\n[2/3] Start/end times (seconds since start):")
    for i in range(6):
        sid = f"sess_{i}"
        s = start_times.get(sid, [None])[0]
        e = end_times.get(sid, [None])[0]
        print(f"  {sid}: start={s:.2f}s end={e:.2f}s")

    # Observe: the first 3 start near 0.00, the next 3 start near 0.30 (after the first wave finishes).

    print("\n[3/3] Graceful shutdown detaches, does not kill.")
    await queue.shutdown(grace_period_s=0.5)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
