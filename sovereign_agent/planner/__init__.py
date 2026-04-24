"""Planner: turn a raw task into ordered subgoals.

See docs/architecture.md §2.13. The planner is one of the two stages of the
loop half; the other is the executor. We split the roles because reasoning
models are good at planning but wasteful for tool execution, and fast
tool-calling models are good at execution but less good at multi-step
planning.
"""

from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from sovereign_agent._internal.atomic import (
    atomic_write_json,
    compute_sha256,
)
from sovereign_agent._internal.llm_client import ChatMessage, LLMClient
from sovereign_agent.discovery import DiscoverySchema
from sovereign_agent.errors import SovereignError, ValidationError, wrap_unexpected
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc
from sovereign_agent.tickets.manifest import Manifest, OutputRecord
from sovereign_agent.tickets.ticket import Ticket, create_ticket

log = logging.getLogger(__name__)


AssignedHalf = Literal["loop", "structured"]
SubgoalStatus = Literal["pending", "in_progress", "done", "failed"]


@dataclass
class Subgoal:
    id: str
    description: str
    success_criterion: str
    estimated_tool_calls: int
    depends_on: list[str] = field(default_factory=list)
    assigned_half: AssignedHalf = "loop"
    status: SubgoalStatus = "pending"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "success_criterion": self.success_criterion,
            "estimated_tool_calls": self.estimated_tool_calls,
            "depends_on": list(self.depends_on),
            "assigned_half": self.assigned_half,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Subgoal:
        return cls(
            id=data["id"],
            description=data["description"],
            success_criterion=data.get("success_criterion", ""),
            estimated_tool_calls=int(data.get("estimated_tool_calls", 1)),
            depends_on=list(data.get("depends_on", [])),
            assigned_half=data.get("assigned_half", "loop"),
            status=data.get("status", "pending"),
        )


@runtime_checkable
class Planner(Protocol):
    name: str

    async def plan(self, task: str, context: dict, session: Session) -> list[Subgoal]: ...

    def discover(self) -> DiscoverySchema: ...


# ---------------------------------------------------------------------------
# DefaultPlanner — uses an LLM client to produce subgoals
# ---------------------------------------------------------------------------

_DEFAULT_PLANNER_SYSTEM = """\
You are the PLANNER of an always-on agent. Your job is to take a user task
and produce a small, ordered list of subgoals that, if executed in order,
will complete the task.

Output ONLY a JSON array (no prose, no markdown fences) with this shape:

  [
    {
      "id": "sg_1",
      "description": "<one sentence — what this subgoal accomplishes>",
      "success_criterion": "<how we know this subgoal is done>",
      "estimated_tool_calls": 1-5,
      "depends_on": ["sg_0", ...],
      "assigned_half": "loop" | "structured"
    },
    ...
  ]

Rules:
- Keep it small: usually 2-6 subgoals. Do not over-decompose.
- Each subgoal must be achievable with the tools described below.
- "loop" is the default half; use "structured" only for subgoals that need
  strict rule-following (e.g. a confirmation dialog before a destructive action).
- depends_on lists any earlier subgoals that must finish first.
"""


class DefaultPlanner:
    name = "default"

    def __init__(
        self,
        *,
        model: str,
        client: LLMClient,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.client = client
        self.system_prompt = system_prompt or _DEFAULT_PLANNER_SYSTEM

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "planner",
            "description": "Default planner. Uses a reasoning LLM to produce subgoals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "context": {"type": "object"},
                },
                "required": ["task"],
            },
            "returns": {
                "type": "array",
                "items": {"type": "object"},
            },
            "error_codes": [
                "SA_VAL_INVALID_PLANNER_OUTPUT",
                "SA_EXT_UNEXPECTED_RESPONSE",
                "SA_EXT_RATE_LIMITED",
            ],
            "examples": [
                {
                    "input": {"task": "find the weather in Edinburgh"},
                    "output": [
                        {
                            "id": "sg_1",
                            "description": "call get_weather for Edinburgh",
                            "success_criterion": "tool returns a temperature",
                            "estimated_tool_calls": 1,
                            "depends_on": [],
                            "assigned_half": "loop",
                        }
                    ],
                }
            ],
            "version": "0.1.0",
            "metadata": {"model": self.model},
        }

    async def plan(self, task: str, context: dict, session: Session) -> list[Subgoal]:
        ticket = create_ticket(session, operation="planner.plan")
        return await _run_planner_via_ticket(ticket, self, task, context, session)


async def _run_planner_via_ticket(
    ticket: Ticket,
    planner: DefaultPlanner,
    task: str,
    context: dict,
    session: Session,
) -> list[Subgoal]:
    ticket.start()
    started = now_utc()
    try:
        tools_summary = context.get("tools_summary") or ""
        user_prompt = _build_planner_user_prompt(task, tools_summary)
        messages = [
            ChatMessage(role="system", content=planner.system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        response = await planner.client.chat(
            model=planner.model, messages=messages, temperature=0.0
        )
        raw = response.content or ""
        subgoals = _parse_subgoals(raw)
        # Write raw output & manifest.
        raw_path = ticket.directory / "raw_output.json"
        atomic_write_json(raw_path, [sg.to_dict() for sg in subgoals])
        completed = now_utc()
        manifest = Manifest(
            ticket_id=ticket.ticket_id,
            operation="planner.plan",
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
                "num_subgoals": len(subgoals),
                "llm_tokens_in": response.input_tokens,
                "llm_tokens_out": response.output_tokens,
                "llm_model": response.model,
            },
        )
        loop_count = sum(1 for sg in subgoals if sg.assigned_half == "loop")
        struct_count = sum(1 for sg in subgoals if sg.assigned_half == "structured")
        est = sum(sg.estimated_tool_calls for sg in subgoals)
        summary = (
            f"Planner produced {len(subgoals)} subgoals. "
            f"{loop_count} to loop half, {struct_count} to structured half. "
            f"Estimated total tool calls: {est}."
        )
        ticket.succeed(manifest, summary)
        return subgoals
    except SovereignError as exc:
        ticket.fail(exc.code, exc.message)
        raise
    except Exception as exc:  # noqa: BLE001
        wrapped = wrap_unexpected(exc)
        ticket.fail(wrapped.code, wrapped.message)
        raise wrapped from exc


def _build_planner_user_prompt(task: str, tools_summary: str) -> str:
    lines = [f"TASK:\n{task}\n"]
    if tools_summary:
        lines.append("AVAILABLE TOOLS:\n" + tools_summary)
    lines.append("Respond with ONLY the JSON array of subgoals.")
    return "\n\n".join(lines)


def _parse_subgoals(raw: str) -> list[Subgoal]:
    """Defensive JSON parsing. Strips markdown fences, finds [ ... ]."""
    if not raw or not raw.strip():
        raise ValidationError(
            code="SA_VAL_INVALID_PLANNER_OUTPUT",
            message="planner returned empty content",
        )
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences.
        text = text.strip("`")
        # After stripping backticks, there may be a 'json\n' prefix.
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    # Find first '[' and last ']'.
    lb = text.find("[")
    rb = text.rfind("]")
    if lb == -1 or rb == -1 or rb < lb:
        raise ValidationError(
            code="SA_VAL_INVALID_PLANNER_OUTPUT",
            message="planner output did not contain a JSON array",
            context={"raw": raw[:500]},
        )
    fragment = text[lb : rb + 1]
    try:
        data = json.loads(fragment)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            code="SA_VAL_INVALID_PLANNER_OUTPUT",
            message=f"planner output JSON did not parse: {exc}",
            context={"raw": raw[:500]},
            cause=exc,
        ) from exc
    if not isinstance(data, list):
        raise ValidationError(
            code="SA_VAL_INVALID_PLANNER_OUTPUT",
            message=f"planner output must be a JSON array, got {type(data).__name__}",
        )
    out: list[Subgoal] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValidationError(
                code="SA_VAL_INVALID_PLANNER_OUTPUT",
                message=f"subgoal #{i} is not an object",
            )
        sid = item.get("id") or f"sg_{i + 1}"
        if sid in seen_ids:
            sid = f"{sid}_{secrets.token_hex(2)}"
        seen_ids.add(sid)
        item["id"] = sid
        try:
            out.append(Subgoal.from_dict(item))
        except KeyError as exc:
            raise ValidationError(
                code="SA_VAL_INVALID_PLANNER_OUTPUT",
                message=f"subgoal #{i} missing required field: {exc}",
                context={"subgoal": item},
            ) from exc
    return out


__all__ = [
    "Subgoal",
    "Planner",
    "DefaultPlanner",
    "_parse_subgoals",  # exported for tests
]
