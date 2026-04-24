"""Tests for v0.2 Module 3 — session resume.

Covers:
  * resume_session() creates a child with resumed_from pointing at parent
  * Parent's scenario, user_id are inherited when not overridden
  * Child has its own fresh session_id; parent is untouched
  * Refusal to resume from an in-progress parent; override via flag
  * Session.parent_session() returns a usable Session handle
  * Session.parent_session() returns None when parent dir is missing
  * build_parent_context_summary() includes trace tail, tickets, result
  * Parent-context block is prepended to child's SESSION.md
  * resumed_from field round-trips through session.json
  * Missing resumed_from in old session.json files is tolerated (backward compat)
  * find_ancestor_chain() walks multi-level resume chains in oldest-first order
  * find_ancestor_chain() is defensive against cycles
  * find_ancestor_chain() stops cleanly when an ancestor directory is missing
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sovereign_agent.errors import ValidationError
from sovereign_agent.session.directory import (
    Session,
    SessionNotFoundError,
    create_session,
    load_session,
)
from sovereign_agent.session.resume import (
    build_parent_context_summary,
    find_ancestor_chain,
    resume_session,
)
from sovereign_agent.session.state import now_utc


def _finish(session: Session, **extra) -> None:
    """Move a fresh 'planning' session to 'completed' via the allowed
    two-step transition. Tests use this when they need a terminal parent
    as their starting point."""
    session.update_state(state="executing")
    session.update_state(state="completed", **extra)


# ---------------------------------------------------------------------------
# resumed_from round-trips through session.json
# ---------------------------------------------------------------------------


def test_resumed_from_is_saved_and_reloaded(sessions_dir: Path) -> None:
    """A session created with resumed_from must persist the value and
    reload it correctly."""
    parent = create_session(
        scenario="demo",
        task="parent task",
        sessions_dir=sessions_dir,
    )
    child = create_session(
        scenario="demo",
        task="child task",
        sessions_dir=sessions_dir,
        resumed_from=parent.session_id,
    )
    assert child.state.resumed_from == parent.session_id

    # Reload from disk — the field is really persisted, not just set in memory.
    reloaded = load_session(child.session_id, sessions_dir=sessions_dir)
    assert reloaded.state.resumed_from == parent.session_id


def test_old_session_json_without_resumed_from_still_loads(
    sessions_dir: Path,
) -> None:
    """SessionState.from_dict must tolerate session.json files written
    before v0.2 (no resumed_from key)."""
    s = create_session(scenario="demo", sessions_dir=sessions_dir)

    # Simulate an older session.json by stripping the key.
    raw = json.loads(s.session_json_path.read_text())
    raw.pop("resumed_from", None)
    s.session_json_path.write_text(json.dumps(raw))

    reloaded = load_session(s.session_id, sessions_dir=sessions_dir)
    assert reloaded.state.resumed_from is None  # default


# ---------------------------------------------------------------------------
# resume_session() — happy path
# ---------------------------------------------------------------------------


def test_resume_session_creates_linked_child(sessions_dir: Path) -> None:
    parent = create_session(
        scenario="demo",
        task="parent task",
        sessions_dir=sessions_dir,
    )
    # Make the parent terminal.
    _finish(parent, result={"ok": True})

    child = resume_session(
        parent_id=parent.session_id,
        task="continuation task",
        sessions_dir=sessions_dir,
    )

    assert child.session_id != parent.session_id
    assert child.state.resumed_from == parent.session_id
    # Scenario inherited by default.
    assert child.state.scenario == parent.state.scenario

    # Parent must not have been touched.
    reloaded_parent = load_session(parent.session_id, sessions_dir=sessions_dir)
    assert reloaded_parent.state.state == "completed"
    assert reloaded_parent.state.resumed_from is None


def test_resume_session_scenario_can_be_overridden(sessions_dir: Path) -> None:
    parent = create_session(
        scenario="scenario_a",
        sessions_dir=sessions_dir,
    )
    _finish(parent)
    child = resume_session(
        parent_id=parent.session_id,
        task="continue with a different scenario",
        sessions_dir=sessions_dir,
        scenario="scenario_b",
    )
    assert child.state.scenario == "scenario_b"
    assert parent.state.scenario == "scenario_a"  # still


def test_resume_session_user_id_inherits_from_parent(sessions_dir: Path) -> None:
    parent = create_session(
        scenario="demo",
        sessions_dir=sessions_dir,
        user_id="rod",
    )
    _finish(parent)
    child = resume_session(
        parent_id=parent.session_id,
        task="continue",
        sessions_dir=sessions_dir,
    )
    assert child.state.user_id == "rod"


def test_resume_session_user_id_override_wins(sessions_dir: Path) -> None:
    parent = create_session(
        scenario="demo",
        sessions_dir=sessions_dir,
        user_id="rod",
    )
    _finish(parent)
    child = resume_session(
        parent_id=parent.session_id,
        task="continue",
        sessions_dir=sessions_dir,
        user_id="alice",
    )
    assert child.state.user_id == "alice"


# ---------------------------------------------------------------------------
# resume_session() — refusal / override policy
# ---------------------------------------------------------------------------


def test_resume_session_refuses_unfinished_parent(sessions_dir: Path) -> None:
    parent = create_session(
        scenario="demo",
        sessions_dir=sessions_dir,
    )
    # Parent is still 'planning' — not terminal.
    with pytest.raises(ValidationError, match="not terminal"):
        resume_session(
            parent_id=parent.session_id,
            task="continue",
            sessions_dir=sessions_dir,
        )


def test_resume_session_allows_unfinished_parent_with_flag(
    sessions_dir: Path,
) -> None:
    """Explicit override for advanced callers: sometimes you really do
    want to fork off a still-running session."""
    parent = create_session(
        scenario="demo",
        sessions_dir=sessions_dir,
    )
    child = resume_session(
        parent_id=parent.session_id,
        task="continue mid-flight",
        sessions_dir=sessions_dir,
        allow_unfinished_parent=True,
    )
    assert child.state.resumed_from == parent.session_id


def test_resume_session_missing_parent_raises(sessions_dir: Path) -> None:
    with pytest.raises(SessionNotFoundError):
        resume_session(
            parent_id="sess_nonexistent",
            task="continue",
            sessions_dir=sessions_dir,
        )


# ---------------------------------------------------------------------------
# Session.parent_session()
# ---------------------------------------------------------------------------


def test_parent_session_none_when_no_parent(sessions_dir: Path) -> None:
    s = create_session(scenario="demo", sessions_dir=sessions_dir)
    assert s.parent_session() is None


def test_parent_session_returns_parent_handle(sessions_dir: Path) -> None:
    parent = create_session(scenario="demo", sessions_dir=sessions_dir)
    _finish(parent, result={"v": 1})

    child = resume_session(
        parent_id=parent.session_id,
        sessions_dir=sessions_dir,
    )

    got = child.parent_session()
    assert got is not None
    assert got.session_id == parent.session_id
    # The returned handle is fully usable — we can read its state.
    assert got.state.state == "completed"
    assert got.state.result == {"v": 1}


def test_parent_session_none_when_parent_dir_missing(sessions_dir: Path) -> None:
    """If an ancestor has been deleted/archived, parent_session() returns
    None cleanly rather than raising. Lets callers degrade gracefully."""
    import shutil

    parent = create_session(scenario="demo", sessions_dir=sessions_dir)
    _finish(parent)
    child = resume_session(
        parent_id=parent.session_id,
        sessions_dir=sessions_dir,
    )
    # Delete the parent out from under the child.
    shutil.rmtree(parent.directory)
    assert child.parent_session() is None


# ---------------------------------------------------------------------------
# build_parent_context_summary()
# ---------------------------------------------------------------------------


def test_parent_context_summary_core_fields(sessions_dir: Path) -> None:
    parent = create_session(
        scenario="code_review",
        task="review foo.py",
        sessions_dir=sessions_dir,
    )
    _finish(parent, result={"findings": 3})
    summary = build_parent_context_summary(parent)
    assert parent.session_id in summary
    assert "code_review" in summary
    assert "completed" in summary
    # Result is JSON-pretty-printed so the planner can read it.
    assert "findings" in summary
    assert "3" in summary


def test_parent_context_summary_includes_trace_tail(sessions_dir: Path) -> None:
    """Appended trace events should surface (capped) in the summary."""
    parent = create_session(scenario="demo", sessions_dir=sessions_dir)
    # Write a handful of trace events.
    for i in range(5):
        parent.append_trace_event(
            {
                "event_type": "executor.tool_called",
                "actor": "default",
                "ticket_id": f"tk_{i}",
                "timestamp": now_utc().isoformat(),
                "payload": {"i": i},
            }
        )
    _finish(parent)

    summary = build_parent_context_summary(parent, trace_summary_lines=3)
    assert "trace tail" in summary.lower()
    # Most recent three events should appear.
    assert '"i": 4' in summary or '"i":4' in summary
    assert '"i": 3' in summary or '"i":3' in summary
    assert '"i": 2' in summary or '"i":2' in summary


def test_parent_context_summary_no_trace_is_ok(sessions_dir: Path) -> None:
    """No trace.jsonl yet? Summary must still render without exploding."""
    parent = create_session(scenario="demo", sessions_dir=sessions_dir)
    _finish(parent)
    summary = build_parent_context_summary(parent)
    assert parent.session_id in summary


def test_parent_context_is_prepended_to_child_session_md(
    sessions_dir: Path,
) -> None:
    """resume_session inlines the summary at the TOP of SESSION.md so the
    planner sees it on first read."""
    parent = create_session(
        scenario="demo",
        task="original task",
        sessions_dir=sessions_dir,
    )
    _finish(parent, result={"done": True})

    child = resume_session(
        parent_id=parent.session_id,
        task="new continuation task",
        sessions_dir=sessions_dir,
    )
    md = child.session_md_path.read_text(encoding="utf-8")
    # Parent context appears first.
    assert md.lstrip().startswith("## Parent session context")
    # Child's OWN task body is still present afterwards.
    assert "new continuation task" in md
    # And the reference to the parent is there.
    assert parent.session_id in md


# ---------------------------------------------------------------------------
# find_ancestor_chain()
# ---------------------------------------------------------------------------


def test_ancestor_chain_empty_when_no_parent(sessions_dir: Path) -> None:
    s = create_session(scenario="demo", sessions_dir=sessions_dir)
    assert find_ancestor_chain(s) == []


def test_ancestor_chain_single_parent(sessions_dir: Path) -> None:
    a = create_session(scenario="demo", sessions_dir=sessions_dir)
    _finish(a)
    b = resume_session(parent_id=a.session_id, sessions_dir=sessions_dir)
    chain = find_ancestor_chain(b)
    assert chain == [a.session_id]


def test_ancestor_chain_multi_level_oldest_first(sessions_dir: Path) -> None:
    """Chain of three: a -> b -> c. find_ancestor_chain(c) == [a, b]."""
    a = create_session(scenario="demo", sessions_dir=sessions_dir)
    _finish(a)
    b = resume_session(parent_id=a.session_id, sessions_dir=sessions_dir)
    _finish(b)
    c = resume_session(parent_id=b.session_id, sessions_dir=sessions_dir)
    chain = find_ancestor_chain(c)
    assert chain == [a.session_id, b.session_id]


def test_ancestor_chain_stops_at_missing_ancestor(sessions_dir: Path) -> None:
    """If a middle ancestor is gone, chain returns only what's reachable
    from the child. This is a graceful-degradation choice."""
    import shutil

    a = create_session(scenario="demo", sessions_dir=sessions_dir)
    _finish(a)
    b = resume_session(parent_id=a.session_id, sessions_dir=sessions_dir)
    _finish(b)
    c = resume_session(parent_id=b.session_id, sessions_dir=sessions_dir)
    # Delete `a`. From c we can still reach b, but walking into b's
    # parent returns None because a is gone.
    shutil.rmtree(a.directory)
    chain = find_ancestor_chain(c)
    assert chain == [b.session_id]


def test_ancestor_chain_breaks_cycle(sessions_dir: Path) -> None:
    """Should not exist naturally, but be defensive: a cycle must not
    cause an infinite loop."""
    a = create_session(scenario="demo", sessions_dir=sessions_dir)
    b = create_session(scenario="demo", sessions_dir=sessions_dir)
    # Hand-construct a cycle: a.resumed_from=b, b.resumed_from=a.
    a.update_state(resumed_from=b.session_id)
    b.update_state(resumed_from=a.session_id)
    chain = find_ancestor_chain(a)
    # Chain contains b (one step out of the cycle); does not loop forever.
    assert b.session_id in chain
    assert len(chain) <= 2


# ---------------------------------------------------------------------------
# CLI — sessions resume
# ---------------------------------------------------------------------------


def test_cli_sessions_resume_creates_linked_session(sessions_dir: Path) -> None:
    """The `sovereign-agent sessions resume` command should produce a new
    session linked to the parent and echo the new session id."""
    from typer.testing import CliRunner

    from sovereign_agent.cli import app

    parent = create_session(
        scenario="demo",
        task="parent work",
        sessions_dir=sessions_dir,
    )
    _finish(parent, result={"x": 1})

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sessions",
            "resume",
            parent.session_id,
            "--task",
            "continue the work",
            "--sessions-dir",
            str(sessions_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "new session:" in result.output
    assert f"resumed_from: {parent.session_id}" in result.output

    # A new session directory exists next to the parent with resumed_from set.
    siblings = [p.name for p in sessions_dir.iterdir() if p.is_dir()]
    assert parent.session_id in siblings
    child_ids = [s for s in siblings if s != parent.session_id]
    assert len(child_ids) == 1
    child = load_session(child_ids[0], sessions_dir=sessions_dir)
    assert child.state.resumed_from == parent.session_id


def test_cli_sessions_resume_refuses_unfinished_parent(
    sessions_dir: Path,
) -> None:
    """Parity with the library: the CLI refuses non-terminal parents
    unless the override flag is provided."""
    from typer.testing import CliRunner

    from sovereign_agent.cli import app

    parent = create_session(scenario="demo", sessions_dir=sessions_dir)
    # parent is in 'planning' — not terminal
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "sessions",
            "resume",
            parent.session_id,
            "--sessions-dir",
            str(sessions_dir),
        ],
    )
    assert result.exit_code == 1
    assert "not terminal" in result.output or "not terminal" in str(result.exception)
