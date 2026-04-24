"""Chapter 3 tests — IPC writes, ticket transitions, manifest verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chapters.chapter_03_ipc.solution import (
    Manifest,
    OutputRecord,
    TicketState,
    create_ticket,
    read_and_consume,
    write_ipc_message,
)
from sovereign_agent._internal.atomic import atomic_write_json, compute_sha256
from sovereign_agent.session.directory import create_session
from sovereign_agent.session.state import now_utc


def test_write_ipc_message_produces_valid_json(tmp_path: Path) -> None:
    out = tmp_path / "out"
    path = write_ipc_message(out, {"x": 1})
    assert path.exists()
    assert json.loads(path.read_text()) == {"x": 1}


def test_ipc_message_filenames_sort_chronologically(tmp_path: Path) -> None:
    out = tmp_path / "out"
    # Space the writes apart so each lands in a distinct millisecond.
    # Without this, fast hardware (modern Apple Silicon, etc.) can
    # complete all 5 writes inside a single millisecond — they'd all
    # share a prefix and sort order would depend on the random hex
    # suffix, which is meaningless. The implementation's contract is
    # "chronological across milliseconds, collision-safe within one."
    import time

    names = []
    for i in range(5):
        names.append(write_ipc_message(out, {"i": i}).name)
        time.sleep(0.002)  # 2ms — reliably crosses the millisecond boundary
    # Chronological prefix means sort order equals creation order.
    assert names == sorted(names)


def test_read_and_consume_returns_payloads(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_ipc_message(out, {"msg": "hi"})
    consumed = read_and_consume(out, max_age_ms=0)
    assert len(consumed) == 1
    _, payload = consumed[0]
    assert payload == {"msg": "hi"}


def test_ticket_happy_path(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session = create_session(scenario="ch3-test", sessions_dir=sessions_dir)

    t = create_ticket(session, operation="op")
    t.start()
    out = t.directory / "raw_output.json"
    atomic_write_json(out, {"ok": True})
    m = Manifest(
        ticket_id=t.ticket_id,
        operation="op",
        started_at=now_utc(),
        completed_at=now_utc(),
        duration_ms=0,
        outputs=[OutputRecord(path=out, sha256=compute_sha256(out), size_bytes=out.stat().st_size)],
    )
    t.succeed(m, "done")
    assert t.read_state() == TicketState.SUCCESS
    assert m.verify() is True


def test_ticket_rejects_bad_manifest(tmp_path: Path) -> None:
    from sovereign_agent.errors import IOError as SovereignIOError

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session = create_session(scenario="ch3-test", sessions_dir=sessions_dir)

    t = create_ticket(session, operation="op")
    t.start()
    out = t.directory / "raw_output.json"
    atomic_write_json(out, {"ok": True})
    m = Manifest(
        ticket_id=t.ticket_id,
        operation="op",
        started_at=now_utc(),
        completed_at=now_utc(),
        duration_ms=0,
        outputs=[OutputRecord(path=out, sha256="f" * 64, size_bytes=out.stat().st_size)],
    )
    with pytest.raises(SovereignIOError):
        t.succeed(m, "should reject")
    # Stays RUNNING — caller decides how to recover.
    assert t.read_state() == TicketState.RUNNING


def test_manifest_verify_detects_tampering(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session = create_session(scenario="ch3-test", sessions_dir=sessions_dir)

    t = create_ticket(session, operation="op")
    t.start()
    out = t.directory / "raw_output.json"
    atomic_write_json(out, {"ok": True})
    m = Manifest(
        ticket_id=t.ticket_id,
        operation="op",
        started_at=now_utc(),
        completed_at=now_utc(),
        duration_ms=0,
        outputs=[OutputRecord(path=out, sha256=compute_sha256(out), size_bytes=out.stat().st_size)],
    )
    t.succeed(m, "done")
    # Tamper after the fact.
    out.write_text('{"tampered": true}')
    assert m.verify() is False
