"""Tests for DefaultExecutor and its ReAct loop."""

from __future__ import annotations

import pytest

from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse, ToolCall
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.planner import Subgoal
from sovereign_agent.session.directory import Session
from sovereign_agent.tickets.state import TicketState
from sovereign_agent.tickets.ticket import list_tickets
from sovereign_agent.tools.builtin import make_builtin_registry


def _sg(sgid: str = "sg_1") -> Subgoal:
    return Subgoal(
        id=sgid,
        description="fetch weather",
        success_criterion="temperature returned",
        estimated_tool_calls=1,
        assigned_half="loop",
    )


@pytest.mark.asyncio
async def test_executor_completes_on_plain_content(fresh_session: Session) -> None:
    client = FakeLLMClient([ScriptedResponse(content="The weather is rainy, 18C.")])
    tools = make_builtin_registry(fresh_session)
    executor = DefaultExecutor(model="fake", client=client, tools=tools)
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    assert result.success is True
    assert result.turns_used == 1
    assert "rainy" in result.final_answer
    # One executor ticket; it succeeded.
    tickets = [t for t in list_tickets(fresh_session) if t.operation.startswith("executor")]
    assert len(tickets) == 1
    assert tickets[0].read_state() == TicketState.SUCCESS


@pytest.mark.asyncio
async def test_executor_invokes_tool_then_finalizes(fresh_session: Session) -> None:
    # Turn 1: call write_file, Turn 2: answer.
    tc1 = ToolCall(id="c1", name="write_file", arguments={"path": "out.md", "content": "hi"})
    client = FakeLLMClient(
        [
            ScriptedResponse(tool_calls=[tc1]),
            ScriptedResponse(content="Wrote out.md with 'hi'."),
        ]
    )
    tools = make_builtin_registry(fresh_session)
    executor = DefaultExecutor(model="fake", client=client, tools=tools)
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    assert result.success is True
    assert result.turns_used == 2
    assert len(result.tool_calls_made) == 1
    assert result.tool_calls_made[0]["name"] == "write_file"
    assert result.tool_calls_made[0]["success"] is True
    # The file actually got written.
    assert (fresh_session.workspace_dir / "out.md").read_text() == "hi"


@pytest.mark.asyncio
async def test_executor_handoff_stops_loop(fresh_session: Session) -> None:
    tc = ToolCall(
        id="c1",
        name="handoff_to_structured",
        arguments={"reason": "confirm", "context": "destructive", "data": {"action": "x"}},
    )
    # Only one response needed: executor exits on handoff.
    client = FakeLLMClient([ScriptedResponse(tool_calls=[tc])])
    tools = make_builtin_registry(fresh_session)
    executor = DefaultExecutor(model="fake", client=client, tools=tools)
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    assert result.handoff_requested is True
    assert result.handoff_payload is not None
    assert result.handoff_payload["reason"] == "confirm"
    # Side effect: handoff file was written.
    assert (fresh_session.ipc_dir / "handoff_to_structured.json").exists()


@pytest.mark.asyncio
async def test_executor_max_turns_exhausted(fresh_session: Session) -> None:
    # Every turn: call list_files. It never decides to finalize.
    tc = ToolCall(id="c", name="list_files", arguments={"path": "."})
    client = FakeLLMClient([ScriptedResponse(tool_calls=[tc]) for _ in range(10)])
    tools = make_builtin_registry(fresh_session)
    executor = DefaultExecutor(model="fake", client=client, tools=tools)
    result = await executor.execute(_sg(), fresh_session, max_turns=3)
    assert result.success is False
    assert result.turns_used == 3
    assert "max_turns=3 exhausted" in result.final_answer


@pytest.mark.asyncio
async def test_executor_trace_writes_per_tool_call(fresh_session: Session) -> None:
    tc = ToolCall(id="c1", name="list_files", arguments={"path": "."})
    client = FakeLLMClient(
        [
            ScriptedResponse(tool_calls=[tc]),
            ScriptedResponse(content="done"),
        ]
    )
    tools = make_builtin_registry(fresh_session)
    executor = DefaultExecutor(model="fake", client=client, tools=tools)
    await executor.execute(_sg(), fresh_session, max_turns=4)
    # The trace should contain at least one executor.tool_called event.
    from sovereign_agent.observability.trace import TraceReader

    events = [e.event_type for e in TraceReader(fresh_session)]
    assert "executor.tool_called" in events


@pytest.mark.asyncio
async def test_executor_unknown_tool_does_not_crash(fresh_session: Session) -> None:
    tc = ToolCall(id="c", name="nonexistent_tool", arguments={})
    client = FakeLLMClient(
        [
            ScriptedResponse(tool_calls=[tc]),
            ScriptedResponse(content="I couldn't find that tool."),
        ]
    )
    tools = make_builtin_registry(fresh_session)
    executor = DefaultExecutor(model="fake", client=client, tools=tools)
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    assert result.success is True
    # Tool call recorded as failed.
    assert result.tool_calls_made[0]["name"] == "nonexistent_tool"
    assert result.tool_calls_made[0]["success"] is False


@pytest.mark.asyncio
async def test_executor_discover_schema_valid() -> None:
    from sovereign_agent.discovery import validate_schema
    from sovereign_agent.tools.registry import ToolRegistry

    executor = DefaultExecutor(model="fake", client=FakeLLMClient(), tools=ToolRegistry())
    validate_schema(executor.discover())
