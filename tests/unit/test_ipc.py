"""Tests for filesystem IPC (Decisions 3, 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.ipc.protocol import (
    clear_close_sentinel,
    is_close_sentinel,
    read_and_consume,
    write_close_sentinel,
    write_ipc_message,
)
from sovereign_agent.ipc.watcher import IpcWatcher
from sovereign_agent.session.directory import create_session


def test_write_ipc_message_atomic(tmp_path: Path) -> None:
    d = tmp_path / "out"
    paths = [write_ipc_message(d, {"i": i}) for i in range(100)]
    assert len(paths) == 100
    for p in paths:
        import json

        data = json.loads(p.read_text())
        assert "i" in data


def test_filenames_sort_chronologically(tmp_path: Path) -> None:
    d = tmp_path / "out"
    # Space each write across a millisecond boundary. Without the
    # sleep, fast hardware can pack all 20 writes into the same
    # millisecond — they'd share a prefix and sort order would depend
    # on the random hex suffix, which is meaningless. The
    # implementation's contract is "chronological across milliseconds,
    # collision-safe within one."
    import time

    paths = []
    for i in range(20):
        paths.append(write_ipc_message(d, {"i": i}))
        time.sleep(0.002)  # 2ms — reliably crosses the ms boundary
    names = [p.name for p in paths]
    assert names == sorted(names)


def test_close_sentinel_roundtrip(tmp_path: Path) -> None:
    write_close_sentinel(tmp_path)
    assert is_close_sentinel(tmp_path / "_close")
    assert not is_close_sentinel(tmp_path / "something.json")
    assert clear_close_sentinel(tmp_path) is True
    assert clear_close_sentinel(tmp_path) is False


def test_read_and_consume_skips_young(tmp_path: Path) -> None:
    d = tmp_path / "out"
    write_ipc_message(d, {"x": 1})
    # Immediate read should skip — file too young.
    assert read_and_consume(d, max_age_ms=1000) == []


def test_read_and_consume_returns_aged(tmp_path: Path) -> None:
    d = tmp_path / "out"
    write_ipc_message(d, {"x": 1})
    # With max_age_ms=0, we accept any file.
    result = read_and_consume(d, max_age_ms=0)
    assert len(result) == 1
    _, payload = result[0]
    assert payload == {"x": 1}


def test_read_and_consume_quarantines_malformed(tmp_path: Path) -> None:
    d = tmp_path / "out"
    d.mkdir()
    (d / "bad.json").write_text("not json")
    err_dir = tmp_path / "errors"
    result = read_and_consume(d, max_age_ms=0, error_dir=err_dir)
    assert result == []
    assert (err_dir / "bad.json").exists()


def test_read_and_consume_moves_to_archive(tmp_path: Path) -> None:
    d = tmp_path / "out"
    write_ipc_message(d, {"x": 1})
    archive = tmp_path / "archive"
    read_and_consume(d, max_age_ms=0, archive_dir=archive)
    # Original directory should no longer contain JSON message files.
    assert not any(p.suffix == ".json" for p in d.iterdir() if p.is_file())
    assert any(p.suffix == ".json" for p in archive.iterdir())


@pytest.mark.asyncio
async def test_watcher_fail_closed_on_multiple_handoffs(sessions_dir: Path) -> None:
    sess = create_session(scenario="t", sessions_dir=sessions_dir)
    # Write two handoff files simultaneously.
    (sess.ipc_dir / "handoff_to_structured.json").write_text('{"version":1}')
    (sess.ipc_dir / "handoff_to_research.json").write_text('{"version":1}')

    called: list[tuple[str, str, dict]] = []

    async def on_handoff(sid: str, target: str, payload: dict) -> None:
        called.append((sid, target, payload))

    watcher = IpcWatcher(
        sessions_dir=sessions_dir,
        on_handoff=on_handoff,
        poll_interval_s=0.01,
    )
    # Single tick directly.
    await watcher._tick()
    # No handoff should have been dispatched.
    assert called == []
    # Both files should have been moved to the malformed archive.
    malformed = sess.handoffs_audit_dir / "_malformed"
    assert malformed.exists()
    files = [p.name for p in malformed.iterdir() if p.is_file()]
    assert any("handoff_to_structured" in f for f in files)
    assert any("handoff_to_research" in f for f in files)


@pytest.mark.asyncio
async def test_watcher_dispatches_single_handoff(sessions_dir: Path) -> None:
    sess = create_session(scenario="t", sessions_dir=sessions_dir)
    import json

    (sess.ipc_dir / "handoff_to_structured.json").write_text(
        json.dumps({"version": 1, "session_id": sess.session_id, "reason": "x"})
    )

    called: list[tuple[str, str, dict]] = []

    async def on_handoff(sid: str, target: str, payload: dict) -> None:
        called.append((sid, target, payload))

    watcher = IpcWatcher(
        sessions_dir=sessions_dir,
        on_handoff=on_handoff,
        poll_interval_s=0.01,
    )
    await watcher._tick()
    assert len(called) == 1
    sid, target, payload = called[0]
    assert sid == sess.session_id
    assert target == "structured"
    # File should have been moved into logs/handoffs/.
    audit = [p for p in sess.handoffs_audit_dir.iterdir() if p.is_file() and p.suffix == ".json"]
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_watcher_session_complete(sessions_dir: Path) -> None:
    sess = create_session(scenario="t", sessions_dir=sessions_dir)
    import json

    (sess.ipc_dir / "session_complete.json").write_text(
        json.dumps({"session_id": sess.session_id, "result": {"ok": True}})
    )

    called: list[tuple[str, dict]] = []

    async def on_complete(sid: str, payload: dict) -> None:
        called.append((sid, payload))

    watcher = IpcWatcher(
        sessions_dir=sessions_dir,
        on_complete=on_complete,
        poll_interval_s=0.01,
    )
    await watcher._tick()
    assert len(called) == 1
    assert called[0][0] == sess.session_id
