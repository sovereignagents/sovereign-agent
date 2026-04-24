"""Executor: run one subgoal via a ReAct-style tool-call loop.

See docs/architecture.md §2.13. Each executor call = one ticket. Each tool
call inside the loop = one nested ticket, so every action is independently
audit-traceable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sovereign_agent._internal.atomic import atomic_write_json, compute_sha256
from sovereign_agent._internal.llm_client import ChatMessage, LLMClient, ToolCall
from sovereign_agent.discovery import DiscoverySchema
from sovereign_agent.errors import SovereignError, wrap_unexpected
from sovereign_agent.planner import Subgoal
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc
from sovereign_agent.tickets.manifest import Manifest, OutputRecord
from sovereign_agent.tickets.ticket import Ticket, create_ticket
from sovereign_agent.tools.registry import ToolRegistry

log = logging.getLogger(__name__)


@dataclass
class ExecutorResult:
    subgoal_id: str
    success: bool
    final_answer: str
    tool_calls_made: list[dict] = field(default_factory=list)
    handoff_requested: bool = False
    handoff_payload: dict | None = None
    turns_used: int = 0
    # v0.2 Module 5 (HITL): when a tool returns requires_human_approval=True
    # the executor exits the ReAct loop and surfaces the pending request.
    # `awaiting_approval` is the request_id; the full request is also
    # written to ipc/awaiting_approval/<request_id>.json.
    awaiting_approval: str | None = None
    approval_request: dict | None = None


@runtime_checkable
class Executor(Protocol):
    name: str

    async def execute(
        self, subgoal: Subgoal, session: Session, max_turns: int = 8
    ) -> ExecutorResult: ...

    def discover(self) -> DiscoverySchema: ...


_DEFAULT_EXECUTOR_SYSTEM = """\
You are the EXECUTOR of an always-on agent. You have been given one SUBGOAL
and a set of tools. Use the tools to satisfy the subgoal's success criterion,
then respond with a plain-text final answer.

Be efficient. Prefer one well-chosen tool call over three speculative ones.
If the subgoal needs a destructive or high-stakes action, call
`handoff_to_structured` rather than performing the action yourself.
When the task is complete, call `complete_task` (if this is the final
subgoal) or simply return a short final-answer text.

You MAY emit multiple tool calls in a single response when they are
independent read-only operations (e.g. looking up three things at once).
The executor will run them concurrently. If you need one call's output
to inform the arguments of another, keep them in separate turns.
"""


# v0.2: how the executor should treat multi-tool-call turns.
#
# "respect_tool_flags" (default): use parallel_safe=True on the tool to
#     decide. Writes, handoffs, and complete_task are marked False and
#     always run alone; read-only tools are marked True and may batch.
# "never":        always run tool calls sequentially (v0.1.0 behaviour).
# "always":       run every batch in parallel regardless of flags. Useful
#     for debugging but dangerous in scenarios with writes.
PARALLELISM_POLICY_DEFAULT = "respect_tool_flags"
PARALLELISM_POLICY_NEVER = "never"
PARALLELISM_POLICY_ALWAYS = "always"


class DefaultExecutor:
    name = "default"

    def __init__(
        self,
        *,
        model: str,
        client: LLMClient,
        tools: ToolRegistry,
        system_prompt: str | None = None,
        parallelism_policy: str = PARALLELISM_POLICY_DEFAULT,
    ) -> None:
        self.model = model
        self.client = client
        self.tools = tools
        self.system_prompt = system_prompt or _DEFAULT_EXECUTOR_SYSTEM
        if parallelism_policy not in (
            PARALLELISM_POLICY_DEFAULT,
            PARALLELISM_POLICY_NEVER,
            PARALLELISM_POLICY_ALWAYS,
        ):
            raise ValueError(
                f"unknown parallelism_policy {parallelism_policy!r}; "
                f"expected one of respect_tool_flags|never|always"
            )
        self.parallelism_policy = parallelism_policy

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "executor",
            "description": "Default executor. Runs a ReAct loop with tool calls.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subgoal": {"type": "object"},
                    "max_turns": {"type": "integer", "default": 8},
                },
                "required": ["subgoal"],
            },
            "returns": {"type": "object"},
            "error_codes": ["SA_EXT_RATE_LIMITED", "SA_EXT_UNEXPECTED_RESPONSE"],
            "examples": [
                {
                    "input": {
                        "subgoal": {
                            "id": "sg_1",
                            "description": "fetch weather",
                            "success_criterion": "temperature returned",
                        }
                    },
                    "output": {"subgoal_id": "sg_1", "success": True},
                }
            ],
            "version": "0.1.0",
            "metadata": {"model": self.model},
        }

    async def execute(
        self, subgoal: Subgoal, session: Session, max_turns: int = 8
    ) -> ExecutorResult:
        ticket = create_ticket(session, operation=f"executor.run_subgoal/{subgoal.id}")
        return await _run_executor_via_ticket(ticket, self, subgoal, session, max_turns)


async def _run_executor_via_ticket(
    ticket: Ticket,
    executor: DefaultExecutor,
    subgoal: Subgoal,
    session: Session,
    max_turns: int,
) -> ExecutorResult:
    ticket.start()
    started = now_utc()
    try:
        result = await _react_loop(executor, subgoal, session, max_turns)
        raw_path = ticket.directory / "raw_output.json"
        atomic_write_json(
            raw_path,
            {
                "subgoal_id": result.subgoal_id,
                "success": result.success,
                "final_answer": result.final_answer,
                "tool_calls_made": result.tool_calls_made,
                "turns_used": result.turns_used,
                "handoff_requested": result.handoff_requested,
                "handoff_payload": result.handoff_payload,
            },
        )
        completed = now_utc()
        manifest = Manifest(
            ticket_id=ticket.ticket_id,
            operation=ticket.operation,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            outputs=[
                OutputRecord(
                    path=raw_path,
                    sha256=compute_sha256(raw_path),
                    size_bytes=raw_path.stat().st_size,
                )
            ],
            metrics={
                "tool_calls": len(result.tool_calls_made),
                "turns_used": result.turns_used,
                "handoff_requested": result.handoff_requested,
            },
        )
        tool_names = [tc["name"] for tc in result.tool_calls_made]
        summary = (
            f"Executor {'completed' if result.success else 'did not complete'} "
            f"subgoal {subgoal.id} in {result.turns_used} turn(s). "
            f"Made {len(result.tool_calls_made)} tool call(s)"
            + (f": {', '.join(tool_names)}." if tool_names else ".")
        )
        if result.handoff_requested:
            summary += " Handoff to structured half requested."
        ticket.succeed(manifest, summary)
        return result
    except SovereignError as exc:
        ticket.fail(exc.code, exc.message)
        raise
    except Exception as exc:  # noqa: BLE001
        wrapped = wrap_unexpected(exc)
        ticket.fail(wrapped.code, wrapped.message)
        raise wrapped from exc


async def _react_loop(
    executor: DefaultExecutor,
    subgoal: Subgoal,
    session: Session,
    max_turns: int,
) -> ExecutorResult:
    tools_as_openai = _registry_to_openai_tools(executor.tools)
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=executor.system_prompt),
        ChatMessage(
            role="user",
            content=(
                f"SUBGOAL {subgoal.id}: {subgoal.description}\n"
                f"SUCCESS CRITERION: {subgoal.success_criterion}\n"
                "Complete this subgoal using the tools available to you."
            ),
        ),
    ]
    tool_calls_made: list[dict] = []
    handoff_requested = False
    handoff_payload: dict | None = None
    final_answer = ""
    turn = 0

    while turn < max_turns:
        turn += 1
        response = await executor.client.chat(
            model=executor.model,
            messages=messages,
            tools=tools_as_openai or None,
            temperature=0.0,
        )
        if response.tool_calls:
            # Add assistant message (echoing the calls) before tool messages.
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )
            # v0.2: dispatch tool calls according to the parallelism policy.
            # Returns tool_outputs in the same order as response.tool_calls,
            # so the ChatMessage append order matches the request order the
            # model sees.
            tool_outputs = await _dispatch_tool_calls(executor, response.tool_calls, session)

            # v0.2 Module 5: scan for any tool that returned
            # requires_human_approval=True. If we find one, we stop the
            # loop, write an approval request, and return. The orchestrator
            # (or a resume_from_approval call) will re-enter once a human
            # has granted or denied.
            approval_index: int | None = None
            for i, tool_output in enumerate(tool_outputs):
                if tool_output.get("requires_human_approval"):
                    approval_index = i
                    break

            # Record every tool call in the trace, even if one of them
            # triggered an approval exit. Tool calls BEFORE the approval
            # index are fully committed (their side effects happened).
            # Tool calls AT the approval index are "proposed" — their
            # side effects also happened, but the LLM will not see the
            # next turn until a human decides.
            # Tool calls AFTER the approval index (in the same batch)
            # also ran, because we dispatched the whole batch; we still
            # log them for audit.
            for tc, tool_output in zip(response.tool_calls, tool_outputs, strict=True):
                tool_calls_made.append(
                    {
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "success": tool_output.get("success", True),
                        "summary": tool_output.get("summary", ""),
                        "requires_human_approval": tool_output.get(
                            "requires_human_approval", False
                        ),
                    }
                )
                if tc.name == "handoff_to_structured" and tool_output.get("success"):
                    handoff_requested = True
                    handoff_payload = dict(tc.arguments)
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=tc.id,
                        name=tc.name,
                        content=json.dumps(tool_output, default=str),
                    )
                )

            if approval_index is not None:
                # Import inside the function to avoid circular imports at
                # module load time (approval.py imports from session).
                from sovereign_agent.ipc.approval import (
                    build_request_from_tool_result,
                    write_approval_request,
                )

                tc = response.tool_calls[approval_index]
                tool_output = tool_outputs[approval_index]
                # ticket_id is set by execute() via the containing
                # ticket; here we use the subgoal's id as a stable proxy
                # since this branch runs before the enclosing execute()
                # returns. The real ticket_id is derivable from the trace
                # if stricter linkage is needed.
                ticket_id = f"exec_{subgoal.id}"
                request = build_request_from_tool_result(
                    session=session,
                    subgoal_id=subgoal.id,
                    ticket_id=ticket_id,
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    tool_arguments=tc.arguments,
                    tool_output=tool_output.get("output", {}),
                    tool_summary=tool_output.get("summary", ""),
                    reason=tool_output.get("output", {}).get("approval_reason", ""),
                )
                write_approval_request(session, request)
                return ExecutorResult(
                    subgoal_id=subgoal.id,
                    success=True,  # the executor reached a clean pause
                    final_answer=f"(awaiting human approval: {request.request_id})",
                    tool_calls_made=tool_calls_made,
                    turns_used=turn,
                    awaiting_approval=request.request_id,
                    approval_request=request.to_dict(),
                )

            if handoff_requested:
                final_answer = "(handoff requested)"
                return ExecutorResult(
                    subgoal_id=subgoal.id,
                    success=True,
                    final_answer=final_answer,
                    tool_calls_made=tool_calls_made,
                    handoff_requested=True,
                    handoff_payload=handoff_payload,
                    turns_used=turn,
                )
            # Continue loop — model will see tool outputs next turn.
            continue

        # No tool calls: treat as final answer.
        final_answer = response.content or ""
        return ExecutorResult(
            subgoal_id=subgoal.id,
            success=True,
            final_answer=final_answer,
            tool_calls_made=tool_calls_made,
            turns_used=turn,
        )

    # max_turns exhausted
    return ExecutorResult(
        subgoal_id=subgoal.id,
        success=False,
        final_answer=f"(max_turns={max_turns} exhausted without final answer)",
        tool_calls_made=tool_calls_made,
        turns_used=turn,
    )


async def _dispatch_tool_calls(
    executor: DefaultExecutor,
    calls: list[ToolCall],
    session: Session,
) -> list[dict]:
    """Dispatch a batch of tool calls according to the executor's parallelism
    policy. Preserves input order in the returned list.

    The policy groups calls into runs:
      * Policy "never"    → one run per call (fully sequential).
      * Policy "always"   → one run containing every call (fully parallel).
      * Policy "respect_tool_flags" (default) → contiguous parallel_safe
        calls are grouped into a parallel run; every parallel_safe=False
        call is its own single-element run. This preserves ordering
        guarantees: if the model emits [read, write, read] the writes
        still see every prior read's effects, and the final read sees
        the write's effects.
    """
    if not calls:
        return []

    # Build runs: each run is a list of (original_index, ToolCall).
    runs: list[list[tuple[int, ToolCall]]] = []
    if executor.parallelism_policy == PARALLELISM_POLICY_NEVER:
        runs = [[(i, c)] for i, c in enumerate(calls)]
    elif executor.parallelism_policy == PARALLELISM_POLICY_ALWAYS:
        runs = [list(enumerate(calls))]
    else:  # respect_tool_flags
        current: list[tuple[int, ToolCall]] = []
        for i, c in enumerate(calls):
            safe = _is_parallel_safe(executor, c.name)
            if safe:
                current.append((i, c))
            else:
                if current:
                    runs.append(current)
                    current = []
                runs.append([(i, c)])
        if current:
            runs.append(current)

    outputs: list[dict | None] = [None] * len(calls)
    for run in runs:
        if len(run) == 1:
            i, tc = run[0]
            outputs[i] = await _invoke_tool(executor, tc, session)
        else:
            # Concurrent group. asyncio.gather returns in input order.
            results = await asyncio.gather(
                *(_invoke_tool(executor, tc, session) for _, tc in run),
                return_exceptions=False,
            )
            for (i, _), result in zip(run, results, strict=True):
                outputs[i] = result

    # Every slot must be populated.
    assert all(o is not None for o in outputs), "parallelism dispatch lost a tool result"
    return [o for o in outputs if o is not None]


def _is_parallel_safe(executor: DefaultExecutor, tool_name: str) -> bool:
    """Check if a tool is registered as parallel_safe. Tools the executor
    cannot find are treated as parallel_unsafe (conservative default)."""
    try:
        tool = executor.tools.get(tool_name)
    except Exception:  # noqa: BLE001
        return False
    return bool(getattr(tool, "parallel_safe", False))


async def _invoke_tool(executor: DefaultExecutor, tc: ToolCall, session: Session) -> dict:
    try:
        tool = executor.tools.get(tc.name)
    except SovereignError as exc:
        return {
            "success": False,
            "error": exc.to_dict(),
            "summary": f"unknown tool: {tc.name}",
        }
    result = await tool.execute(**(tc.arguments or {}))
    # Trace the call.
    try:
        session.append_trace_event(
            {
                "event_type": "executor.tool_called",
                "actor": executor.name,
                "ticket_id": None,
                "timestamp": now_utc().isoformat(),
                "payload": {
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "success": result.success,
                    "summary": result.summary,
                },
            }
        )
    except Exception:  # noqa: BLE001
        # Tracing is best-effort; never let trace failures take down the agent.
        log.exception("failed to append trace event for tool_called")
    return result.to_dict()


def _registry_to_openai_tools(registry: ToolRegistry) -> list[dict]:
    """Translate the ToolRegistry into the list format OpenAI's tools param expects."""
    out: list[dict] = []
    for t in registry.list():
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
        )
    return out


async def resume_from_approval(
    executor: DefaultExecutor,
    subgoal: Subgoal,
    session: Session,
    request_id: str,
    max_turns: int = 8,
) -> ExecutorResult:
    """Resume a subgoal that exited via requires_human_approval.

    The approval decision must already have been recorded
    (ipc/approval_{granted,denied}/<request_id>.json). If no decision
    exists yet, raises SovereignIOError.

    The resumed executor runs a fresh ReAct loop, but its opening prompt
    includes:
      * the original subgoal
      * a summary of the tool calls made before the pause
      * the approval decision — granted or denied, with reason and
        optional override_output

    The LLM then decides how to proceed. On "granted" it typically
    acknowledges and continues (possibly calling complete_task). On
    "denied" it typically proposes an alternative approach.

    This keeps all state in the session directory. Nothing lives in
    memory across the human wait — which may be seconds, hours, or days.
    """
    from sovereign_agent.errors import IOError as SovereignIOError
    from sovereign_agent.ipc.approval import (
        find_decision,
        get_pending_approval,
    )

    # The request has been moved out of awaiting_approval when the
    # decision was recorded, so we fetch from the archived pair.
    decision = find_decision(session, request_id)
    if decision is None:
        # Still pending? Nothing to do.
        if get_pending_approval(session, request_id) is not None:
            raise SovereignIOError(
                code="SA_IO_NOT_FOUND",
                message=(f"approval {request_id!r} is still pending; no decision to resume from"),
                context={"session_id": session.session_id, "request_id": request_id},
            )
        raise SovereignIOError(
            code="SA_IO_NOT_FOUND",
            message=(
                f"no approval record with id {request_id!r} for session {session.session_id!r}"
            ),
            context={"session_id": session.session_id, "request_id": request_id},
        )

    # Build the decision summary the LLM will see.
    if decision.decision == "granted":
        outcome_text = (
            f"APPROVAL GRANTED by {decision.approver} at {decision.decided_at}. "
            f"Reason: {decision.reason or '(none)'}.\n"
        )
        if decision.override_output is not None:
            outcome_text += (
                f"The approver overrode the tool's output with: "
                f"{json.dumps(decision.override_output)}\n"
            )
        outcome_text += (
            "You may now proceed with the approved action or its "
            "consequences. If the approved action satisfies the subgoal, "
            "call complete_task. Otherwise continue as needed."
        )
    else:
        outcome_text = (
            f"APPROVAL DENIED by {decision.approver} at {decision.decided_at}. "
            f"Reason: {decision.reason or '(none)'}.\n"
            "You must NOT proceed with the denied action. Propose an "
            "alternative approach, request clarification, or call "
            "complete_task with a failure result if no viable alternative "
            "exists."
        )

    tools_as_openai = _registry_to_openai_tools(executor.tools)
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=executor.system_prompt),
        ChatMessage(
            role="user",
            content=(
                f"SUBGOAL {subgoal.id}: {subgoal.description}\n"
                f"SUCCESS CRITERION: {subgoal.success_criterion}\n\n"
                f"You previously requested approval for a tool call "
                f"(request_id={request_id}). That request has now been "
                f"decided:\n\n"
                f"{outcome_text}"
            ),
        ),
    ]

    tool_calls_made: list[dict] = []
    handoff_requested = False
    handoff_payload: dict | None = None
    turn = 0

    while turn < max_turns:
        turn += 1
        response = await executor.client.chat(
            model=executor.model,
            messages=messages,
            tools=tools_as_openai or None,
            temperature=0.0,
        )
        if response.tool_calls:
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )
            tool_outputs = await _dispatch_tool_calls(executor, response.tool_calls, session)

            # A resumed subgoal could in principle trigger another approval.
            # Handle that the same way.
            approval_index: int | None = None
            for i, tool_output in enumerate(tool_outputs):
                if tool_output.get("requires_human_approval"):
                    approval_index = i
                    break

            for tc, tool_output in zip(response.tool_calls, tool_outputs, strict=True):
                tool_calls_made.append(
                    {
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "success": tool_output.get("success", True),
                        "summary": tool_output.get("summary", ""),
                        "requires_human_approval": tool_output.get(
                            "requires_human_approval", False
                        ),
                    }
                )
                if tc.name == "handoff_to_structured" and tool_output.get("success"):
                    handoff_requested = True
                    handoff_payload = dict(tc.arguments)
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=tc.id,
                        name=tc.name,
                        content=json.dumps(tool_output, default=str),
                    )
                )

            if approval_index is not None:
                from sovereign_agent.ipc.approval import (
                    build_request_from_tool_result,
                    write_approval_request,
                )

                tc = response.tool_calls[approval_index]
                tool_output = tool_outputs[approval_index]
                ticket_id = f"exec_resume_{subgoal.id}"
                request = build_request_from_tool_result(
                    session=session,
                    subgoal_id=subgoal.id,
                    ticket_id=ticket_id,
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    tool_arguments=tc.arguments,
                    tool_output=tool_output.get("output", {}),
                    tool_summary=tool_output.get("summary", ""),
                    reason=tool_output.get("output", {}).get("approval_reason", ""),
                )
                write_approval_request(session, request)
                return ExecutorResult(
                    subgoal_id=subgoal.id,
                    success=True,
                    final_answer=f"(awaiting human approval: {request.request_id})",
                    tool_calls_made=tool_calls_made,
                    turns_used=turn,
                    awaiting_approval=request.request_id,
                    approval_request=request.to_dict(),
                )

            if handoff_requested:
                return ExecutorResult(
                    subgoal_id=subgoal.id,
                    success=True,
                    final_answer="(handoff requested)",
                    tool_calls_made=tool_calls_made,
                    handoff_requested=True,
                    handoff_payload=handoff_payload,
                    turns_used=turn,
                )
            continue

        # No tool calls — final answer.
        return ExecutorResult(
            subgoal_id=subgoal.id,
            success=True,
            final_answer=response.content or "",
            tool_calls_made=tool_calls_made,
            turns_used=turn,
        )

    return ExecutorResult(
        subgoal_id=subgoal.id,
        success=False,
        final_answer=f"(max_turns={max_turns} exhausted in resumed subgoal)",
        tool_calls_made=tool_calls_made,
        turns_used=turn,
    )


__all__ = [
    "DefaultExecutor",
    "Executor",
    "ExecutorResult",
    "PARALLELISM_POLICY_ALWAYS",
    "PARALLELISM_POLICY_DEFAULT",
    "PARALLELISM_POLICY_NEVER",
    "resume_from_approval",
]
