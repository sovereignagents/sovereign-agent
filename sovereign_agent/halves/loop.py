"""LoopHalf: the default half for open-ended tasks.

Runs the planner, then iterates subgoals through the executor. Stops early
on handoff request or on the first failure (see execute_policy).
"""

from __future__ import annotations

import logging

from sovereign_agent.discovery import DiscoverySchema
from sovereign_agent.executor import DefaultExecutor, ExecutorResult
from sovereign_agent.halves import HalfResult
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc

log = logging.getLogger(__name__)


class LoopHalf:
    name = "loop"

    def __init__(self, *, planner: DefaultPlanner, executor: DefaultExecutor) -> None:
        self.planner = planner
        self.executor = executor

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "half",
            "description": "Default loop half: planner + executor ReAct loop.",
            "parameters": {
                "type": "object",
                "properties": {"task": {"type": "string"}, "context": {"type": "object"}},
                "required": ["task"],
            },
            "returns": {"type": "object"},
            "error_codes": ["SA_VAL_INVALID_PLANNER_OUTPUT"],
            "examples": [
                {
                    "input": {"task": "weather in Edinburgh"},
                    "output": {"success": True, "next_action": "complete"},
                }
            ],
            "version": "0.1.0",
            "metadata": {},
        }

    async def run(self, session: Session, input_payload: dict) -> HalfResult:
        task = input_payload.get("task") or ""
        context = input_payload.get("context") or {}

        # Planner.
        session.append_trace_event(
            {
                "event_type": "planner.called",
                "actor": self.planner.name,
                "timestamp": now_utc().isoformat(),
                "payload": {"task_preview": task[:200]},
            }
        )
        subgoals = await self.planner.plan(task, context, session)
        session.append_trace_event(
            {
                "event_type": "planner.produced_subgoals",
                "actor": self.planner.name,
                "timestamp": now_utc().isoformat(),
                "payload": {"num_subgoals": len(subgoals)},
            }
        )
        session.update_state(
            state="executing",
            planner={"subgoals": [sg.to_dict() for sg in subgoals]},
        )

        # Executor: one subgoal at a time.
        executor_results: list[ExecutorResult] = []
        for sg in subgoals:
            if sg.assigned_half != "loop":
                # Subgoal belongs to another half; stop and hand off.
                return HalfResult(
                    success=True,
                    output={
                        "subgoal_id": sg.id,
                        "assigned_half": sg.assigned_half,
                        "executor_results": [_execresult_to_dict(r) for r in executor_results],
                    },
                    summary=f"subgoal {sg.id} is assigned to {sg.assigned_half}; handing off",
                    next_action=(
                        "handoff_to_structured"
                        if sg.assigned_half == "structured"
                        else "handoff_to_loop"
                    ),
                    handoff_payload={
                        "subgoal": sg.to_dict(),
                        "prior_results": [_execresult_to_dict(r) for r in executor_results],
                    },
                )
            result = await self.executor.execute(sg, session)
            executor_results.append(result)
            if result.handoff_requested:
                return HalfResult(
                    success=True,
                    output={
                        "subgoal_id": sg.id,
                        "executor_results": [_execresult_to_dict(r) for r in executor_results],
                    },
                    summary=f"executor requested handoff to structured from {sg.id}",
                    next_action="handoff_to_structured",
                    handoff_payload=result.handoff_payload or {},
                )
            if not result.success:
                return HalfResult(
                    success=False,
                    output={
                        "subgoal_id": sg.id,
                        "executor_results": [_execresult_to_dict(r) for r in executor_results],
                    },
                    summary=f"executor failed on {sg.id}: {result.final_answer}",
                    next_action="escalate",
                )

        # All subgoals completed successfully.
        final_answer = executor_results[-1].final_answer if executor_results else ""
        return HalfResult(
            success=True,
            output={
                "final_answer": final_answer,
                "executor_results": [_execresult_to_dict(r) for r in executor_results],
            },
            summary=(
                f"loop half completed {len(executor_results)} subgoal(s); "
                f"final answer: {final_answer[:120]}"
            ),
            next_action="complete",
        )


def _execresult_to_dict(r: ExecutorResult) -> dict:
    return {
        "subgoal_id": r.subgoal_id,
        "success": r.success,
        "final_answer": r.final_answer,
        "turns_used": r.turns_used,
        "tool_calls_made": r.tool_calls_made,
        "handoff_requested": r.handoff_requested,
    }


__all__ = ["LoopHalf"]
