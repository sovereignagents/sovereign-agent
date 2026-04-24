"""Chapter 4 tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from chapters.chapter_04_scheduler.solution import (
    ScheduledTask,
    compute_next_run,
)


def _utc(h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 4, 18, h, m, s, tzinfo=UTC)


def test_interval_anchors_not_drifts() -> None:
    anchor = _utc(12, 0, 0)
    task = ScheduledTask(id="t", schedule_type="interval", interval_s=60, next_run=anchor)
    now = anchor + timedelta(seconds=3)
    assert compute_next_run(task, now) == anchor + timedelta(seconds=60)


def test_interval_skips_missed_intervals() -> None:
    anchor = _utc(12, 0, 0)
    task = ScheduledTask(id="t", schedule_type="interval", interval_s=60, next_run=anchor)
    now = anchor + timedelta(minutes=10, seconds=25)
    nxt = compute_next_run(task, now)
    assert nxt is not None
    assert nxt > now
    # Still interval-aligned.
    assert (nxt - anchor).total_seconds() % 60 == 0


def test_interval_first_run_is_interval_seconds_away() -> None:
    task = ScheduledTask(id="t", schedule_type="interval", interval_s=60)
    nxt = compute_next_run(task)
    delta = (nxt - datetime.now(tz=UTC)).total_seconds()
    assert 59 <= delta <= 61


def test_once_returns_none_after_first_run() -> None:
    past = datetime.now(tz=UTC) - timedelta(seconds=1)
    task = ScheduledTask(id="t", schedule_type="once", next_run=past)
    assert compute_next_run(task) is None


def test_once_returns_scheduled_time_if_future() -> None:
    future = datetime.now(tz=UTC) + timedelta(minutes=30)
    task = ScheduledTask(id="t", schedule_type="once", next_run=future)
    assert compute_next_run(task) == future
