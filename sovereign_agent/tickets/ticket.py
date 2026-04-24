"""The Ticket class and module-level helpers.

Decision 9 + Pattern D from the architecture doc. Each long-running operation
gets a ticket directory at logs/tickets/tk_<id>/ with three files:

    state.json      - current state in the explicit state machine
    manifest.json   - proof-of-work record (once state is success)
    summary.md      - LLM-readable summary (always present after completion)

All writes are atomic. Transitions are forward-only. Transition to SUCCESS
is rejected if the provided Manifest does not verify.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import TYPE_CHECKING

from sovereign_agent._internal.atomic import atomic_write_json, atomic_write_text
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.errors import ValidationError
from sovereign_agent.session.state import now_utc
from sovereign_agent.tickets.manifest import Manifest
from sovereign_agent.tickets.state import (
    TicketResult,
    TicketState,
    is_ticket_transition_allowed,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sovereign_agent.session.directory import Session


def _generate_ticket_id() -> str:
    return f"tk_{secrets.token_hex(4)}"


class Ticket:
    """Handle to one ticket directory."""

    def __init__(self, session: Session, operation: str, ticket_id: str | None = None) -> None:
        self.session = session
        self.operation = operation
        self.ticket_id = ticket_id or _generate_ticket_id()
        self.directory = session.tickets_dir / self.ticket_id
        self._started_at: datetime | None = None
        self._state: TicketState = TicketState.PENDING
        # Create the directory and write the initial state file.
        self.directory.mkdir(parents=True, exist_ok=False)
        self._write_state(TicketState.PENDING, started_at=None, completed_at=None)

    # ------------------------------------------------------------------
    # Internal state file helpers
    # ------------------------------------------------------------------
    @property
    def state_path(self) -> Path:
        return self.directory / "state.json"

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    @property
    def summary_path(self) -> Path:
        return self.directory / "summary.md"

    def _write_state(
        self,
        state: TicketState,
        *,
        started_at: datetime | None,
        completed_at: datetime | None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        payload = {
            "ticket_id": self.ticket_id,
            "operation": self.operation,
            "state": state.value,
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "error_code": error_code,
            "error_message": error_message,
        }
        atomic_write_json(self.state_path, payload)
        self._state = state

    def _enforce_transition(self, proposed: TicketState) -> None:
        if not is_ticket_transition_allowed(self._state, proposed):
            raise ValidationError(
                code="SA_VAL_INVALID_STATE_TRANSITION",
                message=(f"invalid ticket transition: {self._state.value!r} -> {proposed.value!r}"),
                context={
                    "ticket_id": self.ticket_id,
                    "current": self._state.value,
                    "proposed": proposed.value,
                },
            )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Transition pending -> running."""
        self._enforce_transition(TicketState.RUNNING)
        self._started_at = now_utc()
        self._write_state(TicketState.RUNNING, started_at=self._started_at, completed_at=None)

    def succeed(self, manifest: Manifest, summary: str) -> None:
        """Transition running -> success.

        The manifest is verified (sha256 checks against every listed output file).
        If verification fails, this call raises and the ticket stays in RUNNING;
        callers typically recover by calling fail() with SA_IO_MANIFEST_INVALID.
        """
        self._enforce_transition(TicketState.SUCCESS)
        if not summary.strip():
            raise ValidationError(
                code="SA_VAL_MISSING_REQUIRED_FIELD",
                message="ticket.succeed() requires a non-empty summary",
                context={"ticket_id": self.ticket_id},
            )
        if not manifest.verify():
            raise SovereignIOError(
                code="SA_IO_MANIFEST_INVALID",
                message=(
                    f"manifest for ticket {self.ticket_id} did not verify: "
                    "one or more output files are missing or their sha256 "
                    "does not match."
                ),
                context={"ticket_id": self.ticket_id},
            )
        completed = now_utc()
        atomic_write_json(self.manifest_path, manifest.to_dict())
        atomic_write_text(self.summary_path, summary)
        self._write_state(TicketState.SUCCESS, started_at=self._started_at, completed_at=completed)

    def skip(self, reason: str) -> None:
        """Transition to skipped. Used when an operation determines no work is needed."""
        self._enforce_transition(TicketState.SKIPPED)
        completed = now_utc()
        summary = f"Skipped: {reason}"
        atomic_write_text(self.summary_path, summary)
        self._write_state(TicketState.SKIPPED, started_at=self._started_at, completed_at=completed)

    def fail(self, error_code: str, error_message: str) -> None:
        """Transition to error with a structured error code."""
        self._enforce_transition(TicketState.ERROR)
        completed = now_utc()
        # Summary is machine+human readable — agents branch on the code.
        summary = f"Error [{error_code}]: {error_message}"
        atomic_write_text(self.summary_path, summary)
        self._write_state(
            TicketState.ERROR,
            started_at=self._started_at,
            completed_at=completed,
            error_code=error_code,
            error_message=error_message,
        )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def read_state(self) -> TicketState:
        with open(self.state_path, encoding="utf-8") as f:
            data = json.load(f)
        return TicketState(data["state"])

    def read_summary(self) -> str:
        if not self.summary_path.exists():
            return ""
        return self.summary_path.read_text(encoding="utf-8")

    def read_manifest(self) -> Manifest | None:
        if not self.manifest_path.exists():
            return None
        with open(self.manifest_path, encoding="utf-8") as f:
            return Manifest.from_dict(json.load(f))

    def read_result(self) -> TicketResult:
        with open(self.state_path, encoding="utf-8") as f:
            data = json.load(f)
        raw_output = self.directory / "raw_output.json"
        return TicketResult(
            ticket_id=self.ticket_id,
            state=TicketState(data["state"]),
            summary=self.read_summary(),
            manifest=self.read_manifest(),
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
            raw_output_path=raw_output if raw_output.exists() else None,
            started_at=_parse_opt_dt(data.get("started_at")),
            completed_at=_parse_opt_dt(data.get("completed_at")),
        )

    def __repr__(self) -> str:
        return f"Ticket(id={self.ticket_id!r}, op={self.operation!r}, state={self._state.value!r})"


def _parse_opt_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    from sovereign_agent.session.state import _parse_dt

    return _parse_dt(value)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def create_ticket(session: Session, operation: str) -> Ticket:
    """Create a new ticket for an operation."""
    return Ticket(session=session, operation=operation)


def list_tickets(session: Session, state_filter: TicketState | None = None) -> list[Ticket]:
    """List all tickets in a session, optionally filtered by state."""
    out: list[Ticket] = []
    if not session.tickets_dir.exists():
        return out
    for entry in sorted(session.tickets_dir.iterdir()):
        if not entry.is_dir() or not entry.name.startswith("tk_"):
            continue
        state_file = entry / "state.json"
        if not state_file.exists():
            continue
        try:
            with open(state_file, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        state = TicketState(data["state"])
        if state_filter is not None and state != state_filter:
            continue
        # Reconstruct a Ticket handle without re-creating the directory.
        ticket = Ticket.__new__(Ticket)
        ticket.session = session
        ticket.operation = data["operation"]
        ticket.ticket_id = data["ticket_id"]
        ticket.directory = entry
        ticket._started_at = _parse_opt_dt(data.get("started_at"))
        ticket._state = state
        out.append(ticket)
    return out


__all__ = ["Ticket", "create_ticket", "list_tickets"]
