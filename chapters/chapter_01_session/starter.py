"""Chapter 1 starter — the student fills in these bodies.

Read README.md first. Your job is to implement the pieces marked with
`raise NotImplementedError`. When tests.py passes, compare your work
to solution.py (which re-exports the production code) to see how the
official implementation handles each concern.

All other classes and helpers come from the production package so you
can focus on the Session substrate itself.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# You may use these helpers from the framework — they're what the real code uses too.
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.errors import ValidationError

# ---------------------------------------------------------------------------
# Exceptions — provided for you
# ---------------------------------------------------------------------------


class SessionEscapeError(SovereignIOError):
    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(
            code="SA_IO_SESSION_ESCAPE",
            message=message,
            context=context or {},
        )


class SessionNotFoundError(SovereignIOError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            code="SA_IO_NOT_FOUND",
            message=f"session {session_id!r} not found",
            context={"session_id": session_id},
        )


class InvalidStateTransition(ValidationError):
    def __init__(self, current: str, proposed: str) -> None:
        super().__init__(
            code="SA_VAL_INVALID_STATE_TRANSITION",
            message=f"invalid transition: {current!r} -> {proposed!r}",
            context={"current": current, "proposed": proposed},
        )


# ---------------------------------------------------------------------------
# State — provided for you
# ---------------------------------------------------------------------------

SessionStateName = Literal[
    "planning",
    "executing",
    "handed_off_to_structured",
    "handed_off_to_research",
    "completed",
    "failed",
    "escalated",
]

TERMINAL_STATES: frozenset[str] = frozenset({"completed", "failed", "escalated"})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "planning": frozenset({"executing", "handed_off_to_structured", "failed", "escalated"}),
    "executing": frozenset(
        {
            "executing",
            "handed_off_to_structured",
            "handed_off_to_research",
            "completed",
            "failed",
            "escalated",
        }
    ),
    "handed_off_to_structured": frozenset({"executing", "completed", "failed", "escalated"}),
    "handed_off_to_research": frozenset({"executing", "completed", "failed", "escalated"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "escalated": frozenset(),
}


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class SessionState:
    session_id: str
    created_at: datetime
    updated_at: datetime
    scenario: str
    state: SessionStateName = "planning"
    version: int = 1
    planner: dict = field(default_factory=dict)
    executor: dict = field(default_factory=dict)
    result: dict | None = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "scenario": self.scenario,
            "state": self.state,
            "planner": self.planner,
            "executor": self.executor,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SessionState:
        return cls(
            session_id=d["session_id"],
            version=d.get("version", 1),
            created_at=_parse_dt(d["created_at"]),
            updated_at=_parse_dt(d["updated_at"]),
            scenario=d["scenario"],
            state=d.get("state", "planning"),
            planner=d.get("planner", {}),
            executor=d.get("executor", {}),
            result=d.get("result"),
        )

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# TODO: Session class
# ---------------------------------------------------------------------------


class Session:
    """Handle to one session directory."""

    def __init__(self, session_id: str, directory: Path, state: SessionState) -> None:
        self.session_id = session_id
        self.directory = directory
        self.state = state

    @property
    def session_json_path(self) -> Path:
        return self.directory / "session.json"

    @property
    def trace_path(self) -> Path:
        return self.directory / "logs" / "trace.jsonl"

    # ------------------------------------------------------------------
    # TODO 1: path() — traversal-safe path resolution.
    #
    # Requirements:
    #   - reject absolute paths (raise SessionEscapeError)
    #   - reject anything that resolves outside self.directory (via symlinks too)
    #   - return the resolved absolute Path on success
    # ------------------------------------------------------------------
    def path(self, relative: str | Path) -> Path:
        raise NotImplementedError("TODO 1: implement traversal-safe path resolution")

    # ------------------------------------------------------------------
    # TODO 2: update_state() — atomic write of session.json.
    #
    # Requirements:
    #   - if `state` is among changes, enforce ALLOWED_TRANSITIONS
    #   - update self.state in memory
    #   - always bump updated_at to now_utc()
    #   - write session.json atomically (atomic_write_json is provided)
    # ------------------------------------------------------------------
    def update_state(self, **changes: object) -> None:
        raise NotImplementedError("TODO 2: implement atomic state update with transition check")

    # ------------------------------------------------------------------
    # TODO 3: append_trace_event() — atomic append to logs/trace.jsonl.
    #
    # Hint: atomic_append_jsonl is provided.
    # ------------------------------------------------------------------
    def append_trace_event(self, event: dict) -> None:
        raise NotImplementedError("TODO 3: append event to trace.jsonl atomically")

    # ------------------------------------------------------------------
    # Lifecycle shortcuts (provided once the above TODOs work)
    # ------------------------------------------------------------------
    def mark_complete(self, result: dict) -> None:
        self.update_state(state="completed", result=result)

    def mark_failed(self, reason: str) -> None:
        self.update_state(state="failed", result={"reason": reason})


# ---------------------------------------------------------------------------
# TODO 4: create_session / load_session / list_sessions
# ---------------------------------------------------------------------------

DEFAULT_SESSIONS_DIR = Path("sessions")


def _generate_session_id() -> str:
    return f"sess_{secrets.token_hex(6)}"


def _make_subdirs(directory: Path) -> None:
    for sub in (
        "memory",
        "memory/semantic",
        "memory/episodic",
        "memory/procedural",
        "ipc",
        "ipc/input",
        "ipc/output",
        "logs",
        "logs/handoffs",
        "logs/tickets",
        "workspace",
        "extras",
    ):
        (directory / sub).mkdir(parents=True, exist_ok=True)


def create_session(
    scenario: str,
    task: str = "",
    sessions_dir: Path | None = None,
) -> Session:
    # TODO 4a: generate an id, make the directory tree, write session.json,
    # write a minimal SESSION.md, return the Session object.
    raise NotImplementedError("TODO 4a: create_session")


def load_session(
    session_id: str,
    sessions_dir: Path | None = None,
) -> Session:
    # TODO 4b: read session.json from sessions/<id>/ and return a Session.
    # Raise SessionNotFoundError if the dir or file is missing.
    raise NotImplementedError("TODO 4b: load_session")


def list_sessions(
    state_filter: SessionStateName | None = None,
    sessions_dir: Path | None = None,
) -> list[Session]:
    # TODO 4c: iterate sessions_dir, load each, optionally filter by state,
    # return list sorted newest-first.
    raise NotImplementedError("TODO 4c: list_sessions")


__all__ = [
    "Session",
    "SessionState",
    "SessionEscapeError",
    "SessionNotFoundError",
    "InvalidStateTransition",
    "create_session",
    "load_session",
    "list_sessions",
    "DEFAULT_SESSIONS_DIR",
]
