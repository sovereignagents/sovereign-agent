"""Tests for DefaultPlanner and the subgoal parser."""

from __future__ import annotations

import json

import pytest

from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse
from sovereign_agent.errors import ValidationError
from sovereign_agent.planner import DefaultPlanner, Subgoal, _parse_subgoals
from sovereign_agent.session.directory import Session
from sovereign_agent.tickets.state import TicketState
from sovereign_agent.tickets.ticket import list_tickets

# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def test_parse_subgoals_plain_array() -> None:
    raw = """[
        {"id": "sg_1", "description": "do thing", "success_criterion": "done", "estimated_tool_calls": 1, "depends_on": [], "assigned_half": "loop"}
    ]"""
    subgoals = _parse_subgoals(raw)
    assert len(subgoals) == 1
    assert subgoals[0].id == "sg_1"


def test_parse_subgoals_strips_markdown_fences() -> None:
    raw = """```json
    [
        {"id": "sg_1", "description": "x", "success_criterion": "y", "estimated_tool_calls": 1, "depends_on": [], "assigned_half": "loop"}
    ]
    ```"""
    subgoals = _parse_subgoals(raw)
    assert len(subgoals) == 1


def test_parse_subgoals_handles_preamble() -> None:
    raw = """Sure! Here are your subgoals:
    [{"id": "sg_1", "description": "a", "success_criterion": "b", "estimated_tool_calls": 1, "depends_on": [], "assigned_half": "loop"}]
    Let me know if you need more."""
    subgoals = _parse_subgoals(raw)
    assert len(subgoals) == 1


def test_parse_subgoals_empty_raises() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _parse_subgoals("")
    assert exc_info.value.code == "SA_VAL_INVALID_PLANNER_OUTPUT"


def test_parse_subgoals_no_array_raises() -> None:
    with pytest.raises(ValidationError):
        _parse_subgoals("nothing to see here")


def test_parse_subgoals_malformed_json_raises() -> None:
    with pytest.raises(ValidationError):
        _parse_subgoals("[{not valid json]")


def test_parse_subgoals_auto_assigns_missing_ids() -> None:
    raw = json.dumps(
        [
            {
                "description": "a",
                "success_criterion": "b",
                "estimated_tool_calls": 1,
                "assigned_half": "loop",
            },
            {
                "description": "c",
                "success_criterion": "d",
                "estimated_tool_calls": 2,
                "assigned_half": "loop",
            },
        ]
    )
    subgoals = _parse_subgoals(raw)
    assert [sg.id for sg in subgoals] == ["sg_1", "sg_2"]


def test_parse_subgoals_deduplicates_ids() -> None:
    raw = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "a",
                "success_criterion": "",
                "estimated_tool_calls": 1,
                "assigned_half": "loop",
            },
            {
                "id": "sg_1",
                "description": "b",
                "success_criterion": "",
                "estimated_tool_calls": 1,
                "assigned_half": "loop",
            },
        ]
    )
    subgoals = _parse_subgoals(raw)
    assert subgoals[0].id == "sg_1"
    assert subgoals[1].id != "sg_1"


# ---------------------------------------------------------------------------
# DefaultPlanner (full ticket flow against FakeLLMClient)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_writes_ticket_manifest_on_success(fresh_session: Session) -> None:
    raw = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "fetch weather",
                "success_criterion": "temperature returned",
                "estimated_tool_calls": 1,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    client = FakeLLMClient([ScriptedResponse(content=raw)])
    planner = DefaultPlanner(model="fake-planner", client=client)
    subgoals = await planner.plan("get weather", {}, fresh_session)
    assert len(subgoals) == 1
    # One ticket was created and succeeded.
    tickets = list_tickets(fresh_session)
    assert len(tickets) == 1
    t = tickets[0]
    assert t.read_state() == TicketState.SUCCESS
    result = t.read_result()
    assert result.manifest is not None
    assert result.manifest.verify() is True
    # Summary mentions subgoal count.
    assert "1 subgoal" in result.summary


@pytest.mark.asyncio
async def test_planner_summary_not_raw_on_session(fresh_session: Session) -> None:
    raw = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "x",
                "success_criterion": "y",
                "estimated_tool_calls": 1,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    client = FakeLLMClient([ScriptedResponse(content=raw)])
    planner = DefaultPlanner(model="fake", client=client)
    await planner.plan("t", {}, fresh_session)
    tickets = list_tickets(fresh_session)
    t = tickets[0]
    # summary.md exists and is the short summary (Pattern B)
    assert t.summary_path.exists()
    assert "Planner produced" in t.read_summary()
    # raw_output.json exists and is the full subgoal list
    raw_path = t.directory / "raw_output.json"
    assert raw_path.exists()
    raw_data = json.loads(raw_path.read_text())
    assert isinstance(raw_data, list) and len(raw_data) == 1


@pytest.mark.asyncio
async def test_planner_marks_ticket_error_on_malformed_output(fresh_session: Session) -> None:
    client = FakeLLMClient([ScriptedResponse(content="this is not JSON")])
    planner = DefaultPlanner(model="fake", client=client)
    with pytest.raises(ValidationError):
        await planner.plan("t", {}, fresh_session)
    tickets = list_tickets(fresh_session)
    assert len(tickets) == 1
    assert tickets[0].read_state() == TicketState.ERROR
    result = tickets[0].read_result()
    assert result.error_code == "SA_VAL_INVALID_PLANNER_OUTPUT"


@pytest.mark.asyncio
async def test_planner_discover_schema_valid() -> None:
    from sovereign_agent.discovery import validate_schema

    planner = DefaultPlanner(model="fake", client=FakeLLMClient())
    validate_schema(planner.discover())


def test_subgoal_roundtrip() -> None:
    sg = Subgoal(
        id="sg_1",
        description="x",
        success_criterion="y",
        estimated_tool_calls=2,
        depends_on=["sg_0"],
        assigned_half="structured",
    )
    restored = Subgoal.from_dict(sg.to_dict())
    assert restored == sg
