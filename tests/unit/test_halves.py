"""Tests for LoopHalf and StructuredHalf."""

from __future__ import annotations

import json

import pytest

from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse, ToolCall
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.halves.structured import Rule, StructuredHalf
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.builtin import make_builtin_registry


@pytest.mark.asyncio
async def test_loop_half_runs_planner_then_executor_then_completes(
    fresh_session: Session,
) -> None:
    # Planner: returns a single loop subgoal. Executor: answers in one turn.
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "answer",
                "success_criterion": "has answer",
                "estimated_tool_calls": 0,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    client = FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),  # planner
            ScriptedResponse(content="hello world"),  # executor
        ]
    )
    tools = make_builtin_registry(fresh_session)
    planner = DefaultPlanner(model="fake", client=client)
    executor = DefaultExecutor(model="fake", client=client, tools=tools)
    half = LoopHalf(planner=planner, executor=executor)
    result = await half.run(fresh_session, {"task": "say hello"})
    assert result.success is True
    assert result.next_action == "complete"
    assert "hello world" in result.summary


@pytest.mark.asyncio
async def test_loop_half_hands_off_on_executor_handoff(fresh_session: Session) -> None:
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "needs confirm",
                "success_criterion": "confirmed",
                "estimated_tool_calls": 1,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    tc = ToolCall(
        id="c",
        name="handoff_to_structured",
        arguments={"reason": "confirm", "context": "", "data": {}},
    )
    client = FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[tc]),  # executor requests handoff
        ]
    )
    tools = make_builtin_registry(fresh_session)
    half = LoopHalf(
        planner=DefaultPlanner(model="fake", client=client),
        executor=DefaultExecutor(model="fake", client=client, tools=tools),
    )
    result = await half.run(fresh_session, {"task": "t"})
    assert result.next_action == "handoff_to_structured"


@pytest.mark.asyncio
async def test_loop_half_hands_off_when_subgoal_assigned_elsewhere(
    fresh_session: Session,
) -> None:
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "do it by rules",
                "success_criterion": "",
                "estimated_tool_calls": 1,
                "depends_on": [],
                "assigned_half": "structured",
            }
        ]
    )
    client = FakeLLMClient([ScriptedResponse(content=plan_json)])
    tools = make_builtin_registry(fresh_session)
    half = LoopHalf(
        planner=DefaultPlanner(model="fake", client=client),
        executor=DefaultExecutor(model="fake", client=client, tools=tools),
    )
    result = await half.run(fresh_session, {"task": "t"})
    assert result.next_action == "handoff_to_structured"
    # No executor tickets should have been created.
    from sovereign_agent.tickets.ticket import list_tickets

    exec_tickets = [t for t in list_tickets(fresh_session) if t.operation.startswith("executor.")]
    assert exec_tickets == []


# ---------------------------------------------------------------------------
# StructuredHalf
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_half_first_matching_rule_fires(fresh_session: Session) -> None:
    rules = [
        Rule(
            name="r1",
            condition=lambda d: d.get("action") == "greet",
            action=lambda d: {"response": "hello"},
        ),
        Rule(
            name="r2",
            condition=lambda d: d.get("action") == "farewell",
            action=lambda d: {"response": "goodbye"},
        ),
    ]
    half = StructuredHalf(rules=rules)
    result = await half.run(fresh_session, {"action": "farewell"})
    assert result.success is True
    assert result.output["rule"] == "r2"
    assert result.output["result"] == {"response": "goodbye"}


@pytest.mark.asyncio
async def test_structured_half_escalates_when_escalate_if_true(
    fresh_session: Session,
) -> None:
    rules = [
        Rule(
            name="risky",
            condition=lambda d: True,
            action=lambda d: {"done": True},
            escalate_if=lambda d: d.get("high_stakes", False),
        ),
    ]
    half = StructuredHalf(rules=rules)
    result = await half.run(fresh_session, {"high_stakes": True})
    assert result.next_action == "escalate"


@pytest.mark.asyncio
async def test_structured_half_escalates_when_no_rule_matches(
    fresh_session: Session,
) -> None:
    half = StructuredHalf(rules=[])
    result = await half.run(fresh_session, {"anything": True})
    assert result.next_action == "escalate"
    assert result.success is False
