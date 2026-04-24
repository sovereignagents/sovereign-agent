"""Ticket state machine types.

Decision 9 from the architecture doc. Every long-running operation is a
ticket with an explicit state:

    pending  -> running  -> success
                         |
                         -> skipped
                         |
                         -> error

Forward-only. Once a ticket is terminal (success/skipped/error), it can't move.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sovereign_agent.tickets.manifest import Manifest


class TicketState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


TERMINAL_TICKET_STATES: frozenset[TicketState] = frozenset(
    {TicketState.SUCCESS, TicketState.SKIPPED, TicketState.ERROR}
)

ALLOWED_TICKET_TRANSITIONS: dict[TicketState, frozenset[TicketState]] = {
    TicketState.PENDING: frozenset({TicketState.RUNNING, TicketState.SKIPPED, TicketState.ERROR}),
    TicketState.RUNNING: frozenset({TicketState.SUCCESS, TicketState.SKIPPED, TicketState.ERROR}),
    TicketState.SUCCESS: frozenset(),
    TicketState.SKIPPED: frozenset(),
    TicketState.ERROR: frozenset(),
}


@dataclass
class TicketResult:
    """What an agent sees when it polls a ticket.

    Agents read `summary`, not `raw_output_path`. This is Pattern B
    ("summary artifacts") in effect: the summary keeps the agent's context
    focused on its current decision while the raw output is archived for
    later inspection.
    """

    ticket_id: str
    state: TicketState
    summary: str
    manifest: Manifest | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_output_path: Path | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


def is_ticket_transition_allowed(current: TicketState, proposed: TicketState) -> bool:
    return proposed in ALLOWED_TICKET_TRANSITIONS.get(current, frozenset())


__all__ = [
    "TicketState",
    "TERMINAL_TICKET_STATES",
    "ALLOWED_TICKET_TRANSITIONS",
    "TicketResult",
    "is_ticket_transition_allowed",
]
