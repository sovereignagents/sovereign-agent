"""Chapter 5 tests — the full working agent against the solution re-exports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chapters.chapter_05_planner_executor.solution import (
    DefaultExecutor,
    DefaultPlanner,
    LoopHalf,
    make_builtin_registry,
)
from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse, ToolCall
from sovereign_agent.errors import ValidationError
from sovereign_agent.planner import _parse_subgoals
from sovereign_agent.session.directory import create_session
from sovereign_agent.tickets.state import TicketState
from sovereign_agent.tickets.ticket import list_tickets


def test_parse_subgoals_plain() -> None:
    raw = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "a",
                "success_criterion": "b",
                "estimated_tool_calls": 1,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    sgs = _parse_subgoals(raw)
    assert len(sgs) == 1


def test_parse_subgoals_strips_markdown_fences() -> None:
    raw = '```json\n[{"id": "sg_1", "description": "a", "success_criterion": "b", "estimated_tool_calls": 1, "depends_on": [], "assigned_half": "loop"}]\n```'
    sgs = _parse_subgoals(raw)
    assert len(sgs) == 1


def test_parse_subgoals_raises_on_garbage() -> None:
    with pytest.raises(ValidationError):
        _parse_subgoals("not json at all")


@pytest.mark.asyncio
async def test_full_loop_half_end_to_end(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    session = create_session(
        scenario="ch5-test",
        task="write greet.md with hello and mark complete",
        sessions_dir=sessions_root,
    )

    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "do it",
                "success_criterion": "file exists",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    write_call = ToolCall(
        id="c1", name="write_file", arguments={"path": "greet.md", "content": "hello"}
    )
    complete_call = ToolCall(id="c2", name="complete_task", arguments={"result": {"ok": True}})
    client = FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[write_call]),
            ScriptedResponse(tool_calls=[complete_call]),
            ScriptedResponse(content="done"),
        ]
    )
    tools = make_builtin_registry(session)
    half = LoopHalf(
        planner=DefaultPlanner(model="fake", client=client),
        executor=DefaultExecutor(model="fake", client=client, tools=tools),
    )
    result = await half.run(session, {"task": "t"})
    assert result.next_action == "complete"
    # File landed.
    assert (session.workspace_dir / "greet.md").read_text() == "hello"
    # Both tickets succeeded and their manifests still verify.
    for t in list_tickets(session):
        assert t.read_state() == TicketState.SUCCESS
        m = t.read_manifest()
        assert m is not None and m.verify()
