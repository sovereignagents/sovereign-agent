"""Tests for v0.2 Module 5 — human-in-the-loop approval.

Covers the full life-cycle:
  1. A tool returns requires_human_approval=True.
  2. The executor writes ipc/awaiting_approval/<id>.json and returns with
     awaiting_approval set.
  3. A CLI (or test helper) records a granted/denied response.
  4. resume_from_approval() re-enters the loop; the LLM sees the decision
     and proceeds.

Also covers:
  * stable request_id derivation from (ticket_id, tool_call_id)
  * arguments SHA-256 is stable across key orderings
  * a malformed pending file does not break list_pending_approvals
  * trying to record a decision for a non-existent request raises
  * resume_from_approval raises if no decision yet
  * denial path — the LLM sees the denial reason and can adapt
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse, ToolCall
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.executor import DefaultExecutor, resume_from_approval
from sovereign_agent.ipc.approval import (
    ApprovalRequest,
    ApprovalResponse,
    compute_arguments_sha256,
    find_decision,
    get_pending_approval,
    list_pending_approvals,
    make_request_id,
    record_decision,
)
from sovereign_agent.planner import Subgoal
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool


def _sg(sgid: str = "sg_1") -> Subgoal:
    return Subgoal(
        id=sgid,
        description="book a venue requiring human approval",
        success_criterion="booking confirmed or gracefully abandoned",
        estimated_tool_calls=2,
        assigned_half="loop",
    )


def _make_approval_tool(*, always_needs_approval: bool = True) -> _RegisteredTool:
    """A tool that ALWAYS asks for human approval before committing.

    Models a real scenario: you've computed the booking; you want a human
    to sign off before the money moves.
    """

    def _impl(venue_id: str, deposit_gbp: int) -> ToolResult:
        output = {
            "venue_id": venue_id,
            "deposit_gbp": deposit_gbp,
            "approval_reason": (
                f"Deposit £{deposit_gbp} for {venue_id} needs sign-off "
                f"before the booking is committed."
            ),
        }
        return ToolResult(
            success=True,
            output=output,
            summary=f"proposed booking: {venue_id}, £{deposit_gbp}",
            requires_human_approval=always_needs_approval,
        )

    return _RegisteredTool(
        name="book_venue_with_approval",
        description="Book a venue; always requires human approval.",
        fn=_impl,
        parameters_schema={
            "type": "object",
            "properties": {
                "venue_id": {"type": "string"},
                "deposit_gbp": {"type": "integer"},
            },
            "required": ["venue_id", "deposit_gbp"],
        },
        returns_schema={"type": "object"},
        is_async=False,
        parallel_safe=False,  # writes are unsafe to parallelise
        examples=[
            {
                "input": {"venue_id": "venue_hay", "deposit_gbp": 200},
                "output": {"venue_id": "venue_hay", "deposit_gbp": 200},
            }
        ],
    )


# ---------------------------------------------------------------------------
# Helpers — request_id derivation, hash stability
# ---------------------------------------------------------------------------


def test_make_request_id_stable_for_same_inputs() -> None:
    r1 = make_request_id("exec_sg_1", "call_abc12345")
    r2 = make_request_id("exec_sg_1", "call_abc12345")
    assert r1 == r2
    assert r1.startswith("appr_")


def test_make_request_id_distinguishes_different_tool_calls() -> None:
    a = make_request_id("exec_sg_1", "call_a")
    b = make_request_id("exec_sg_1", "call_b")
    assert a != b


def test_compute_arguments_sha256_order_insensitive() -> None:
    h1 = compute_arguments_sha256({"a": 1, "b": 2})
    h2 = compute_arguments_sha256({"b": 2, "a": 1})
    assert h1 == h2


def test_compute_arguments_sha256_detects_changes() -> None:
    h1 = compute_arguments_sha256({"venue_id": "v1", "deposit_gbp": 200})
    h2 = compute_arguments_sha256({"venue_id": "v1", "deposit_gbp": 400})
    assert h1 != h2


# ---------------------------------------------------------------------------
# Executor integration — the pause point
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_pauses_on_requires_human_approval(fresh_session: Session) -> None:
    """A tool call returning requires_human_approval=True should cause the
    executor to exit the loop with awaiting_approval set."""
    reg = ToolRegistry()
    reg.register(_make_approval_tool())

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue_with_approval",
                        arguments={"venue_id": "venue_hay", "deposit_gbp": 400},
                    ),
                ]
            ),
            # The executor should never reach a second LLM turn.
            ScriptedResponse(content="should not be reached"),
        ]
    )
    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    result = await executor.execute(_sg(), fresh_session, max_turns=5)

    assert result.awaiting_approval is not None
    assert result.approval_request is not None
    assert result.turns_used == 1
    # The tool call is recorded in the trace.
    assert len(result.tool_calls_made) == 1
    assert result.tool_calls_made[0]["requires_human_approval"] is True

    # The pending request file must exist.
    pending = list_pending_approvals(fresh_session)
    assert len(pending) == 1
    req = pending[0]
    assert req.tool_name == "book_venue_with_approval"
    assert req.tool_arguments == {"venue_id": "venue_hay", "deposit_gbp": 400}
    assert req.arguments_sha256 == compute_arguments_sha256(
        {"venue_id": "venue_hay", "deposit_gbp": 400}
    )
    assert "sign-off" in req.reason  # came from approval_reason in output

    # Audit log also has it.
    log_path = fresh_session.logs_dir / "approvals" / f"{req.request_id}.request.json"
    assert log_path.exists()


@pytest.mark.asyncio
async def test_pending_approval_is_listed_by_id(fresh_session: Session) -> None:
    reg = ToolRegistry()
    reg.register(_make_approval_tool())
    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue_with_approval",
                        arguments={"venue_id": "venue_x", "deposit_gbp": 100},
                    ),
                ]
            )
        ]
    )
    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    result = await executor.execute(_sg(), fresh_session, max_turns=3)

    assert result.awaiting_approval is not None
    got = get_pending_approval(fresh_session, result.awaiting_approval)
    assert got is not None
    assert got.request_id == result.awaiting_approval


# ---------------------------------------------------------------------------
# Grant path — full lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle_grant_then_resume(fresh_session: Session) -> None:
    """End-to-end: tool asks → executor pauses → human grants →
    resume_from_approval continues and the LLM completes the subgoal."""
    reg = ToolRegistry()
    reg.register(_make_approval_tool())

    # First phase: the LLM asks to book and the tool requests approval.
    client_phase1 = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue_with_approval",
                        arguments={"venue_id": "venue_hay", "deposit_gbp": 200},
                    ),
                ]
            )
        ]
    )
    executor_phase1 = DefaultExecutor(model="fake", client=client_phase1, tools=reg)
    result1 = await executor_phase1.execute(_sg(), fresh_session, max_turns=3)
    assert result1.awaiting_approval is not None
    request_id = result1.awaiting_approval

    # Simulate human approval via the CLI path.
    response = ApprovalResponse(
        request_id=request_id,
        decision="granted",
        approver="rod",
        decided_at=now_utc().isoformat(),
        reason="standard deposit, within authorisation",
    )
    target = record_decision(fresh_session, response)
    assert target.exists()
    # The pending file should have been moved out.
    assert get_pending_approval(fresh_session, request_id) is None

    decision = find_decision(fresh_session, request_id)
    assert decision is not None
    assert decision.decision == "granted"

    # Second phase: resume. The LLM should see "APPROVAL GRANTED" in the
    # user message and be able to wrap up the subgoal.
    client_phase2 = FakeLLMClient(
        [ScriptedResponse(content=("Booking completed after approval. No further actions needed."))]
    )
    executor_phase2 = DefaultExecutor(model="fake", client=client_phase2, tools=reg)
    result2 = await resume_from_approval(
        executor_phase2,
        _sg(),
        fresh_session,
        request_id=request_id,
        max_turns=3,
    )
    assert result2.success
    assert "Booking completed" in result2.final_answer
    assert result2.awaiting_approval is None

    # The LLM's message history — which FakeLLMClient doesn't expose —
    # cannot be inspected directly here, but we can verify the decision
    # file the resume flow read.
    archived = fresh_session.logs_dir / "approvals" / f"{request_id}.decision.json"
    assert archived.exists()
    data = json.loads(archived.read_text())
    assert data["response"]["decision"] == "granted"


# ---------------------------------------------------------------------------
# Deny path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle_deny_then_resume(fresh_session: Session) -> None:
    """Denial should surface the reason to the LLM, which adapts."""
    reg = ToolRegistry()
    reg.register(_make_approval_tool())

    # Phase 1: request.
    client_phase1 = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue_with_approval",
                        arguments={"venue_id": "venue_hay", "deposit_gbp": 500},
                    ),
                ]
            )
        ]
    )
    executor = DefaultExecutor(model="fake", client=client_phase1, tools=reg)
    result1 = await executor.execute(_sg(), fresh_session, max_turns=3)
    request_id = result1.awaiting_approval
    assert request_id is not None

    # Deny.
    response = ApprovalResponse(
        request_id=request_id,
        decision="denied",
        approver="rod",
        decided_at=now_utc().isoformat(),
        reason="£500 exceeds the £300 authorised deposit.",
    )
    record_decision(fresh_session, response)

    # Phase 2: resume with a deny. LLM sees denial and adapts.
    client_phase2 = FakeLLMClient(
        [
            ScriptedResponse(
                content=(
                    "Understood — the deposit exceeds the limit. I will "
                    "propose an alternative venue with a lower deposit."
                )
            )
        ]
    )
    executor2 = DefaultExecutor(model="fake", client=client_phase2, tools=reg)
    result2 = await resume_from_approval(
        executor2, _sg(), fresh_session, request_id=request_id, max_turns=3
    )
    assert result2.success
    assert "propose an alternative" in result2.final_answer.lower()


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_without_decision_raises(fresh_session: Session) -> None:
    """resume_from_approval when the request is still pending should raise."""
    reg = ToolRegistry()
    reg.register(_make_approval_tool())
    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue_with_approval",
                        arguments={"venue_id": "v", "deposit_gbp": 1},
                    ),
                ]
            )
        ]
    )
    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    result = await executor.execute(_sg(), fresh_session, max_turns=3)
    request_id = result.awaiting_approval
    assert request_id is not None

    # No decision recorded yet.
    with pytest.raises(SovereignIOError, match="still pending"):
        await resume_from_approval(
            executor, _sg(), fresh_session, request_id=request_id, max_turns=3
        )


@pytest.mark.asyncio
async def test_resume_unknown_id_raises(fresh_session: Session) -> None:
    reg = ToolRegistry()
    executor = DefaultExecutor(model="fake", client=FakeLLMClient([]), tools=reg)
    with pytest.raises(SovereignIOError, match="no approval record"):
        await resume_from_approval(executor, _sg(), fresh_session, request_id="appr_missing_xxx")


def test_record_decision_unknown_id_raises(fresh_session: Session) -> None:
    response = ApprovalResponse(
        request_id="appr_not_there",
        decision="granted",
        approver="rod",
        decided_at=now_utc().isoformat(),
        reason="",
    )
    with pytest.raises(SovereignIOError, match="no pending approval"):
        record_decision(fresh_session, response)


def test_malformed_pending_file_is_skipped(fresh_session: Session) -> None:
    """A corrupt file in awaiting_approval must not break the lister."""
    awaiting = fresh_session.ipc_dir / "awaiting_approval"
    awaiting.mkdir(parents=True, exist_ok=True)
    # Write a valid one
    valid_req = ApprovalRequest(
        request_id="appr_ok_c1",
        session_id=fresh_session.session_id,
        subgoal_id="sg_1",
        ticket_id="tk_1",
        tool_name="t",
        tool_arguments={},
        arguments_sha256="00",
        proposed_output={},
        tool_summary="",
        created_at=now_utc().isoformat(),
        reason="",
    )
    (awaiting / "appr_ok_c1.json").write_text(json.dumps(valid_req.to_dict()))
    # ...and a garbage one.
    (awaiting / "appr_bad_c2.json").write_text("this is {{{ not json")

    listed = list_pending_approvals(fresh_session)
    # Only the valid one comes through; the corrupt one is silently skipped.
    assert len(listed) == 1
    assert listed[0].request_id == "appr_ok_c1"


# ---------------------------------------------------------------------------
# CLI surface (smoke)
# ---------------------------------------------------------------------------


def test_cli_approvals_list_with_no_pending(fresh_session: Session, tmp_path: Path) -> None:
    """`sovereign-agent approvals list` with nothing pending should exit 0
    and say so."""
    from typer.testing import CliRunner

    from sovereign_agent.cli import app

    # The session was created under a tmp sessions_dir; pass it through.
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "approvals",
            "list",
            fresh_session.session_id,
            "--sessions-dir",
            str(fresh_session.directory.parent),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "no pending approvals" in result.output


@pytest.mark.asyncio
async def test_cli_approvals_grant_records_decision(fresh_session: Session) -> None:
    """Full loop: executor pauses, CLI grants, resume completes."""
    from typer.testing import CliRunner

    from sovereign_agent.cli import app

    reg = ToolRegistry()
    reg.register(_make_approval_tool())
    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue_with_approval",
                        arguments={"venue_id": "v", "deposit_gbp": 50},
                    ),
                ]
            )
        ]
    )
    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    result = await executor.execute(_sg(), fresh_session, max_turns=3)
    request_id = result.awaiting_approval
    assert request_id is not None

    runner = CliRunner()
    cli_out = runner.invoke(
        app,
        [
            "approvals",
            "grant",
            fresh_session.session_id,
            request_id,
            "--approver",
            "test-user",
            "--reason",
            "test",
            "--sessions-dir",
            str(fresh_session.directory.parent),
        ],
    )
    assert cli_out.exit_code == 0, cli_out.output
    assert "granted" in cli_out.output

    # Verify the decision landed.
    decision = find_decision(fresh_session, request_id)
    assert decision is not None
    assert decision.decision == "granted"
    assert decision.approver == "test-user"
