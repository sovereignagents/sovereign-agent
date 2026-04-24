"""End-to-end integration: planner + executor + tool call + complete_task.

Drives the entire loop half against a scripted FakeLLMClient and verifies
the on-disk state of the session at the end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse, ToolCall
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.observability.report import generate_session_report
from sovereign_agent.observability.trace import TraceReader
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import create_session
from sovereign_agent.tickets.state import TicketState
from sovereign_agent.tickets.ticket import list_tickets
from sovereign_agent.tools.builtin import make_builtin_registry


@pytest.mark.asyncio
async def test_full_loop_half_writes_file_and_reaches_complete(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session = create_session(
        scenario="e2e",
        task="Write 'hello' to greet.md and mark the task complete.",
        sessions_dir=sessions_dir,
    )

    # Scripted model turns:
    # 1. Planner: one subgoal assigned to loop.
    # 2. Executor turn 1: call write_file.
    # 3. Executor turn 2: call complete_task.
    # 4. Executor turn 3: brief final answer.
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "write greet.md with 'hello', then mark complete",
                "success_criterion": "file exists and session_complete is written",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    write_call = ToolCall(
        id="c1",
        name="write_file",
        arguments={"path": "greet.md", "content": "hello"},
    )
    complete_call = ToolCall(
        id="c2",
        name="complete_task",
        arguments={"result": {"wrote": "greet.md"}},
    )
    client = FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[write_call]),
            ScriptedResponse(tool_calls=[complete_call]),
            ScriptedResponse(content="Done: greet.md written and task complete."),
        ]
    )

    tools = make_builtin_registry(session)
    planner = DefaultPlanner(model="fake-planner", client=client)
    executor = DefaultExecutor(model="fake-executor", client=client, tools=tools)
    half = LoopHalf(planner=planner, executor=executor)

    result = await half.run(session, {"task": "write greet.md"})

    # LoopHalf succeeded
    assert result.success is True
    assert result.next_action == "complete"

    # File landed in workspace/
    assert (session.workspace_dir / "greet.md").read_text() == "hello"

    # session_complete.json was written by the complete_task tool
    assert (session.ipc_dir / "session_complete.json").exists()

    # Tickets: 1 planner ticket + 1 executor ticket, both SUCCESS.
    tickets = list_tickets(session)
    planner_tix = [t for t in tickets if t.operation.startswith("planner.")]
    executor_tix = [t for t in tickets if t.operation.startswith("executor.")]
    assert len(planner_tix) == 1
    assert len(executor_tix) == 1
    assert all(t.read_state() == TicketState.SUCCESS for t in tickets)

    # Every successful ticket has a manifest that still verifies.
    for t in tickets:
        manifest = t.read_manifest()
        assert manifest is not None
        assert manifest.verify() is True

    # Trace contains the expected event types.
    event_types = {e.event_type for e in TraceReader(session)}
    assert "planner.called" in event_types
    assert "planner.produced_subgoals" in event_types
    assert "executor.tool_called" in event_types

    # The generated report mentions both tickets by operation name.
    report = generate_session_report(session)
    assert "planner.plan" in report
    assert "executor.run_subgoal" in report
    assert session.session_id in report
