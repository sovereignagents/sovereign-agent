"""Tests for Session, SessionState, and session directory layout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sovereign_agent.session.directory import (
    InvalidStateTransition,
    Session,
    SessionEscapeError,
    SessionNotFoundError,
    archive_session,
    create_session,
    list_sessions,
    load_session,
)


def test_create_session_creates_all_subdirectories(sessions_dir: Path) -> None:
    s = create_session(scenario="t", task="x", sessions_dir=sessions_dir)
    for sub in (
        "memory",
        "memory/semantic",
        "memory/episodic",
        "memory/procedural",
        "ipc",
        "ipc/input",
        "ipc/output",
        "logs",
        "logs/handoffs",
        "logs/tickets",
        "workspace",
        "extras",
    ):
        assert (s.directory / sub).is_dir(), f"missing {sub}"


def test_create_session_writes_session_json_and_md(sessions_dir: Path) -> None:
    s = create_session(scenario="t", task="hello world", sessions_dir=sessions_dir)
    assert s.session_json_path.is_file()
    assert s.session_md_path.is_file()
    assert "hello world" in s.session_md_path.read_text()


def test_session_create_roundtrip(sessions_dir: Path) -> None:
    s = create_session(scenario="t", task="x", sessions_dir=sessions_dir)
    loaded = load_session(s.session_id, sessions_dir=sessions_dir)
    assert loaded.session_id == s.session_id
    assert loaded.state.scenario == "t"
    assert loaded.state.state == "planning"


def test_session_path_rejects_traversal(fresh_session: Session) -> None:
    with pytest.raises(SessionEscapeError):
        fresh_session.path("../../etc/passwd")


def test_session_path_rejects_absolute(fresh_session: Session) -> None:
    with pytest.raises(SessionEscapeError):
        fresh_session.path("/etc/passwd")


def test_session_path_rejects_symlink_escape(fresh_session: Session, tmp_path: Path) -> None:
    outside = tmp_path / "outside_target"
    outside.mkdir()
    # Create a symlink inside the session pointing outside.
    link = fresh_session.directory / "workspace" / "escape"
    link.symlink_to(outside)
    with pytest.raises(SessionEscapeError):
        fresh_session.path("workspace/escape/anything")


def test_session_state_transitions_forward_only(fresh_session: Session) -> None:
    fresh_session.update_state(state="executing")
    # planning -> executing OK. executing -> planning NOT OK.
    with pytest.raises(InvalidStateTransition):
        fresh_session.update_state(state="planning")


def test_session_state_update_atomic(fresh_session: Session) -> None:
    # Simulate: after the write we can still parse it as valid JSON.
    fresh_session.update_state(state="executing", planner={"subgoals": [{"id": "sg_1"}]})
    raw = fresh_session.session_json_path.read_text()
    data = json.loads(raw)
    assert data["state"] == "executing"
    assert data["planner"]["subgoals"] == [{"id": "sg_1"}]


def test_session_trace_event_append(fresh_session: Session) -> None:
    fresh_session.append_trace_event({"event_type": "t1", "actor": "x"})
    fresh_session.append_trace_event({"event_type": "t2", "actor": "x"})
    lines = fresh_session.trace_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "t1"
    assert json.loads(lines[1])["event_type"] == "t2"


def test_session_trace_event_too_large(fresh_session: Session) -> None:
    from sovereign_agent.errors import IOError as SovereignIOError

    big_payload = {"event_type": "t", "actor": "x", "payload": {"blob": "x" * 10000}}
    with pytest.raises(SovereignIOError):
        fresh_session.append_trace_event(big_payload)


def test_session_not_found_raises(sessions_dir: Path) -> None:
    with pytest.raises(SessionNotFoundError):
        load_session("sess_nonexistent", sessions_dir=sessions_dir)


def test_list_sessions_orders_newest_first(sessions_dir: Path) -> None:
    import time

    s1 = create_session(scenario="a", sessions_dir=sessions_dir)
    time.sleep(0.01)
    s2 = create_session(scenario="b", sessions_dir=sessions_dir)
    listed = list_sessions(sessions_dir=sessions_dir)
    assert [x.session_id for x in listed][:2] == [s2.session_id, s1.session_id]


def test_list_sessions_filters_by_state(sessions_dir: Path) -> None:
    s1 = create_session(scenario="a", sessions_dir=sessions_dir)
    s2 = create_session(scenario="b", sessions_dir=sessions_dir)
    # planning -> executing -> completed (forward-only chain)
    s2.update_state(state="executing")
    s2.mark_complete({"x": 1})
    done = list_sessions(state_filter="completed", sessions_dir=sessions_dir)
    assert [x.session_id for x in done] == [s2.session_id]
    _ = s1  # keep it around


def test_archive_session_rejects_non_terminal(fresh_session: Session) -> None:
    from sovereign_agent.errors import ValidationError

    with pytest.raises(ValidationError):
        archive_session(fresh_session)


def test_archive_session_moves_terminal(sessions_dir: Path) -> None:
    s = create_session(scenario="t", sessions_dir=sessions_dir)
    s.update_state(state="executing")
    s.mark_complete({"x": 1})
    original = s.directory
    dest = archive_session(s)
    assert not original.exists()
    assert dest.exists()
    assert dest.name == original.name
