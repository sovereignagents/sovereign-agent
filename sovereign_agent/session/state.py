"""The SessionState dataclass and its allowed state transitions.

Decision 1 from the architecture doc: all per-task state lives in the session
directory. `session.json` is the machine-readable state file. This module
defines its schema and the forward-only transition rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

# Allowed values for the `state` field. Forward-only: once a session reaches
# a terminal state (completed, failed, escalated), it cannot move again.
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

# Allowed transitions. Anything not in this map is rejected by update_state().
# Keys are current states; values are sets of allowed next states.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "planning": frozenset({"executing", "handed_off_to_structured", "failed", "escalated"}),
    "executing": frozenset(
        {
            "executing",  # allow updating the executor stats without changing phase
            "handed_off_to_structured",
            "handed_off_to_research",
            "completed",
            "failed",
            "escalated",
        }
    ),
    "handed_off_to_structured": frozenset({"executing", "completed", "failed", "escalated"}),
    "handed_off_to_research": frozenset({"executing", "completed", "failed", "escalated"}),
    # Terminal states can't transition.
    "completed": frozenset(),
    "failed": frozenset(),
    "escalated": frozenset(),
}


@dataclass
class SessionState:
    """The contents of session.json, as a dataclass.

    Version 1 of the schema. If this changes incompatibly in a future release,
    bump `version` and provide a migration.
    """

    session_id: str
    created_at: datetime
    updated_at: datetime
    scenario: str
    state: SessionStateName = "planning"
    version: int = 1
    user_id: str | None = None
    current_half: Literal["loop", "structured"] = "loop"
    planner: dict = field(default_factory=dict)
    executor: dict = field(default_factory=dict)
    structured: dict = field(default_factory=dict)
    memory: dict = field(default_factory=dict)
    handoff_history: list[dict] = field(default_factory=list)
    bare_mode: bool = False
    config_overrides: dict = field(default_factory=dict)
    result: dict | None = None
    # v0.2 Module 3: session resume — if set, this session is a continuation
    # of the referenced parent session. The parent is untouched (forward-only
    # rule) and this field is purely a pointer. See session/resume.py.
    resumed_from: str | None = None

    def to_dict(self) -> dict:
        """Serializable form for session.json."""
        return {
            "session_id": self.session_id,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "scenario": self.scenario,
            "state": self.state,
            "user_id": self.user_id,
            "current_half": self.current_half,
            "planner": self.planner,
            "executor": self.executor,
            "structured": self.structured,
            "memory": self.memory,
            "handoff_history": self.handoff_history,
            "bare_mode": self.bare_mode,
            "config_overrides": self.config_overrides,
            "result": self.result,
            "resumed_from": self.resumed_from,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionState:
        """Deserialize from session.json contents."""
        return cls(
            session_id=data["session_id"],
            version=data.get("version", 1),
            created_at=_parse_dt(data["created_at"]),
            updated_at=_parse_dt(data["updated_at"]),
            scenario=data["scenario"],
            state=data.get("state", "planning"),
            user_id=data.get("user_id"),
            current_half=data.get("current_half", "loop"),
            planner=data.get("planner", {}),
            executor=data.get("executor", {}),
            structured=data.get("structured", {}),
            memory=data.get("memory", {}),
            handoff_history=data.get("handoff_history", []),
            bare_mode=data.get("bare_mode", False),
            config_overrides=data.get("config_overrides", {}),
            result=data.get("result"),
            resumed_from=data.get("resumed_from"),
        )

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


def _parse_dt(value: Any) -> datetime:
    """Parse an ISO-8601 datetime, tolerating both 'Z' suffix and +00:00."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise TypeError(f"expected ISO-8601 string or datetime, got {type(value).__name__}")
    # Python's fromisoformat handles '+00:00' natively in 3.11+ and tolerates 'Z' in 3.11+ too.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def now_utc() -> datetime:
    """Canonical 'now' with timezone info. Always use this rather than datetime.utcnow()."""
    return datetime.now(tz=UTC)


def is_transition_allowed(current: str, proposed: str) -> bool:
    """Check whether a state transition is allowed.

    Same-state 'transitions' are allowed where noted in ALLOWED_TRANSITIONS
    (e.g. executing -> executing, to update stats without changing phase).
    """
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        return False
    return proposed in allowed


__all__ = [
    "SessionState",
    "SessionStateName",
    "TERMINAL_STATES",
    "ALLOWED_TRANSITIONS",
    "is_transition_allowed",
    "now_utc",
]
