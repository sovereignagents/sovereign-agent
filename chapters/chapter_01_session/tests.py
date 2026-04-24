"""Chapter 1 tests. Run these against your starter.py as you work.

The tests import `solution` by default (which mirrors the production code
and will always pass). To test YOUR implementation, change the import
below to read `from starter import ...`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Swap this import for `from starter import ...` to test your work.
from chapters.chapter_01_session.solution import (
    InvalidStateTransition,
    SessionEscapeError,
    SessionNotFoundError,
    create_session,
    list_sessions,
    load_session,
)


@pytest.fixture()
def sessions_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    return d


def test_create_makes_all_subdirectories(sessions_dir: Path) -> None:
    s = create_session(scenario="test", task="x", sessions_dir=sessions_dir)
    for sub in (
        "memory/semantic",
        "memory/episodic",
        "memory/procedural",
        "ipc/input",
        "ipc/output",
        "logs/handoffs",
        "logs/tickets",
        "workspace",
    ):
        assert (s.directory / sub).is_dir(), f"missing {sub}"


def test_path_rejects_traversal(sessions_dir: Path) -> None:
    s = create_session(scenario="t", sessions_dir=sessions_dir)
    with pytest.raises(SessionEscapeError):
        s.path("../../etc/passwd")


def test_path_rejects_absolute(sessions_dir: Path) -> None:
    s = create_session(scenario="t", sessions_dir=sessions_dir)
    with pytest.raises(SessionEscapeError):
        s.path("/etc/passwd")


def test_state_transitions_forward_only(sessions_dir: Path) -> None:
    s = create_session(scenario="t", sessions_dir=sessions_dir)
    s.update_state(state="executing")
    with pytest.raises(InvalidStateTransition):
        s.update_state(state="planning")


def test_atomic_state_write(sessions_dir: Path) -> None:
    s = create_session(scenario="t", sessions_dir=sessions_dir)
    s.update_state(state="executing", planner={"subgoals": [{"id": "sg_1"}]})
    data = json.loads(s.session_json_path.read_text())
    assert data["state"] == "executing"
    assert data["planner"]["subgoals"] == [{"id": "sg_1"}]


def test_trace_append(sessions_dir: Path) -> None:
    s = create_session(scenario="t", sessions_dir=sessions_dir)
    s.append_trace_event({"event_type": "a", "actor": "x"})
    s.append_trace_event({"event_type": "b", "actor": "x"})
    lines = s.trace_path.read_text().strip().splitlines()
    assert [json.loads(line)["event_type"] for line in lines] == ["a", "b"]


def test_load_missing_raises(sessions_dir: Path) -> None:
    with pytest.raises(SessionNotFoundError):
        load_session("sess_nope", sessions_dir=sessions_dir)


def test_list_newest_first(sessions_dir: Path) -> None:
    import time

    s1 = create_session(scenario="a", sessions_dir=sessions_dir)
    time.sleep(0.01)
    s2 = create_session(scenario="b", sessions_dir=sessions_dir)
    listed = list_sessions(sessions_dir=sessions_dir)
    assert [x.session_id for x in listed] == [s2.session_id, s1.session_id]
