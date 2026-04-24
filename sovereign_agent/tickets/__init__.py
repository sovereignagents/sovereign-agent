"""Tickets: explicit state machine for long-running operations.

Decision 9 + Pattern D. See docs/architecture.md §2.7.
"""

from sovereign_agent.tickets.manifest import Manifest, OutputRecord
from sovereign_agent.tickets.state import (
    ALLOWED_TICKET_TRANSITIONS,
    TERMINAL_TICKET_STATES,
    TicketResult,
    TicketState,
    is_ticket_transition_allowed,
)
from sovereign_agent.tickets.ticket import Ticket, create_ticket, list_tickets

__all__ = [
    "Ticket",
    "TicketState",
    "TicketResult",
    "Manifest",
    "OutputRecord",
    "TERMINAL_TICKET_STATES",
    "ALLOWED_TICKET_TRANSITIONS",
    "is_ticket_transition_allowed",
    "create_ticket",
    "list_tickets",
]
