"""Eval judges — score completed sessions against a criterion.

Skeleton: the protocol is wired up and three built-in judges are declared,
but they return trivial scores for now. Replacing them with real LLM-backed
judges is the first lesson in the lessons feed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from sovereign_agent.discovery import DiscoverySchema
from sovereign_agent.observability.trace import TraceReader
from sovereign_agent.session.directory import Session
from sovereign_agent.tickets.state import TicketState
from sovereign_agent.tickets.ticket import list_tickets

Verdict = Literal["pass", "fail", "warning"]


@dataclass
class JudgeResult:
    judge_name: str
    score: float  # 0.0 - 1.0
    verdict: Verdict
    rationale: str
    evidence: list[dict] = field(default_factory=list)


@runtime_checkable
class Judge(Protocol):
    name: str

    async def score(self, session: Session) -> JudgeResult: ...

    def discover(self) -> DiscoverySchema: ...


class PlannerQualityJudge:
    """Scores whether a plan was produced and every subgoal was achievable.

    Placeholder: returns pass if any planner ticket reached SUCCESS, fail
    otherwise. Upgrade to LLM-backed judgment in a lesson.
    """

    name = "planner_quality"

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "observability",
            "description": "Heuristic judge: did the planner produce a plan?",
            "parameters": {"type": "object"},
            "returns": {"type": "object"},
            "error_codes": [],
            "examples": [{"input": {}, "output": {"score": 1.0, "verdict": "pass"}}],
            "version": "0.1.0",
            "metadata": {},
        }

    async def score(self, session: Session) -> JudgeResult:
        planner_tickets = [t for t in list_tickets(session) if t.operation.startswith("planner.")]
        if any(t.read_state() == TicketState.SUCCESS for t in planner_tickets):
            return JudgeResult(
                judge_name=self.name,
                score=1.0,
                verdict="pass",
                rationale="at least one planner ticket succeeded",
            )
        return JudgeResult(
            judge_name=self.name,
            score=0.0,
            verdict="fail",
            rationale="no planner ticket reached success",
        )


class ExecutorTrajectoryJudge:
    """Scores based on whether every executor ticket succeeded."""

    name = "executor_trajectory"

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "observability",
            "description": "Heuristic judge: did every executor ticket succeed?",
            "parameters": {"type": "object"},
            "returns": {"type": "object"},
            "error_codes": [],
            "examples": [{"input": {}, "output": {"score": 1.0, "verdict": "pass"}}],
            "version": "0.1.0",
            "metadata": {},
        }

    async def score(self, session: Session) -> JudgeResult:
        exec_tickets = [t for t in list_tickets(session) if t.operation.startswith("executor.")]
        if not exec_tickets:
            return JudgeResult(
                judge_name=self.name,
                score=0.5,
                verdict="warning",
                rationale="no executor tickets",
            )
        ok = sum(1 for t in exec_tickets if t.read_state() == TicketState.SUCCESS)
        score = ok / len(exec_tickets)
        verdict: Verdict = "pass" if score == 1.0 else ("fail" if score < 0.5 else "warning")
        return JudgeResult(
            judge_name=self.name,
            score=score,
            verdict=verdict,
            rationale=f"{ok}/{len(exec_tickets)} executor tickets succeeded",
        )


class MemoryUsageJudge:
    """Scores based on how many memory events appeared in the trace.

    Placeholder: just counts `memory.*` events. A real version would check
    whether the agent retrieved relevant facts when they were available.
    """

    name = "memory_usage"

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "observability",
            "description": "Heuristic judge: did the agent touch memory?",
            "parameters": {"type": "object"},
            "returns": {"type": "object"},
            "error_codes": [],
            "examples": [{"input": {}, "output": {"score": 1.0, "verdict": "pass"}}],
            "version": "0.1.0",
            "metadata": {},
        }

    async def score(self, session: Session) -> JudgeResult:
        count = sum(1 for e in TraceReader(session) if e.event_type.startswith("memory."))
        if count == 0:
            return JudgeResult(
                judge_name=self.name,
                score=0.0,
                verdict="warning",
                rationale="no memory events in trace",
            )
        return JudgeResult(
            judge_name=self.name,
            score=min(1.0, count / 5),
            verdict="pass",
            rationale=f"{count} memory events in trace",
        )


__all__ = [
    "Verdict",
    "JudgeResult",
    "Judge",
    "PlannerQualityJudge",
    "ExecutorTrajectoryJudge",
    "MemoryUsageJudge",
]
