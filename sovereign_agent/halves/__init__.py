"""Agent halves: loop (open-ended) and structured (rule-following).

See docs/architecture.md §2.15. A half is a mode of operation the agent can
be in. Halves communicate only through the session directory (no in-process
references).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from sovereign_agent.discovery import DiscoverySchema
from sovereign_agent.session.directory import Session

NextAction = Literal["complete", "handoff_to_loop", "handoff_to_structured", "escalate"]


@dataclass
class HalfResult:
    success: bool
    output: dict
    summary: str
    next_action: NextAction = "complete"
    handoff_payload: dict | None = None


@runtime_checkable
class Half(Protocol):
    name: str

    async def run(self, session: Session, input_payload: dict) -> HalfResult: ...

    def discover(self) -> DiscoverySchema: ...
