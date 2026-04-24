"""Session: handle to one session directory.

Implements Decision 1 from the architecture: every task gets its own directory
at sessions/sess_<12-hex>/ and all state for that task lives there.

The Session class is the only way to read or write files in the session
directory that the rest of the framework uses. Direct filesystem access is
discouraged because Session.path() enforces traversal safety.
"""

from __future__ import annotations

import json
import secrets
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from sovereign_agent._internal.atomic import atomic_append_jsonl, atomic_write_json
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.errors import ValidationError
from sovereign_agent.session.state import (
    SessionState,
    SessionStateName,
    is_transition_allowed,
    now_utc,
)

if TYPE_CHECKING:
    pass

DEFAULT_SESSIONS_DIR = Path("sessions")

_DEFAULT_SESSION_MD_TEMPLATE = """# Session {session_id}

**Scenario:** {scenario}
**Created:** {created_at}

## Your task

(The loop half reads this file on every turn. The initial task description
has been written below by the orchestrator when the session was created.
Additional per-session instructions — constraints, identity, voice — can
be added by the scenario author.)

## Task description

{task}

## Constraints

- Be honest when you do not know something.
- Prefer reading memory over guessing.
- When the task is ambiguous, ask for clarification rather than inventing an answer.
"""


class SessionEscapeError(SovereignIOError):
    """Raised by Session.path() when a requested path resolves outside the session dir."""

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(
            code="SA_IO_SESSION_ESCAPE",
            message=message,
            context=context or {},
        )


class SessionNotFoundError(SovereignIOError):
    """Raised by load_session() when the session directory is missing."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            code="SA_IO_NOT_FOUND",
            message=f"session {session_id!r} not found",
            context={"session_id": session_id},
        )


class InvalidStateTransition(ValidationError):
    """Raised by Session.update_state() when a proposed transition is not allowed."""

    def __init__(self, current: str, proposed: str) -> None:
        super().__init__(
            code="SA_VAL_INVALID_STATE_TRANSITION",
            message=(
                f"invalid session state transition: {current!r} -> {proposed!r}. "
                "State transitions are forward-only and must follow ALLOWED_TRANSITIONS."
            ),
            context={"current": current, "proposed": proposed},
        )


class Session:
    """Handle to one session directory. See docs/architecture.md §1.3 for the layout."""

    def __init__(
        self,
        session_id: str,
        directory: Path,
        state: SessionState,
    ) -> None:
        self.session_id = session_id
        self.directory = directory
        self.state = state

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------
    def path(self, relative: str | Path) -> Path:
        """Resolve a relative path inside the session directory.

        Raises SessionEscapeError if the resolved path is outside the session
        directory — including via symlinks. Callers should always go through
        this method rather than manipulating paths directly.
        """
        base = self.directory.resolve()
        # Disallow absolute relatives (a caller passing '/etc/passwd' is
        # almost certainly a bug).
        rel = Path(relative)
        if rel.is_absolute():
            raise SessionEscapeError(
                f"absolute path not allowed: {relative!r}",
                {"requested": str(relative), "session_dir": str(base)},
            )
        candidate = (base / rel).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise SessionEscapeError(
                f"path {relative!r} escapes session directory",
                {"requested": str(relative), "resolved": str(candidate), "session_dir": str(base)},
            ) from exc
        return candidate

    # ------------------------------------------------------------------
    # Subdirectory accessors
    # ------------------------------------------------------------------
    @property
    def memory_dir(self) -> Path:
        return self.directory / "memory"

    @property
    def ipc_dir(self) -> Path:
        return self.directory / "ipc"

    @property
    def ipc_input_dir(self) -> Path:
        return self.ipc_dir / "input"

    @property
    def ipc_output_dir(self) -> Path:
        return self.ipc_dir / "output"

    @property
    def logs_dir(self) -> Path:
        return self.directory / "logs"

    @property
    def trace_path(self) -> Path:
        return self.logs_dir / "trace.jsonl"

    @property
    def tickets_dir(self) -> Path:
        return self.logs_dir / "tickets"

    @property
    def handoffs_audit_dir(self) -> Path:
        return self.logs_dir / "handoffs"

    @property
    def workspace_dir(self) -> Path:
        return self.directory / "workspace"

    @property
    def extras_dir(self) -> Path:
        return self.directory / "extras"

    @property
    def session_json_path(self) -> Path:
        return self.directory / "session.json"

    @property
    def session_md_path(self) -> Path:
        return self.directory / "SESSION.md"

    # ------------------------------------------------------------------
    # v0.2 Module 3: resumed-from parent helpers
    # ------------------------------------------------------------------
    def parent_session(self) -> Session | None:
        """If this session was created via resume_session, return a Session
        handle for the parent. Returns None if there's no parent, or if the
        parent's directory is no longer on disk (e.g. archived).

        The parent is returned as a fully usable Session object — you can
        read its trace, tickets, memory, etc. Writing to the parent from
        here is discouraged: the forward-only rule means parents should
        not be modified.
        """
        if self.state.resumed_from is None:
            return None
        parent_dir = self.directory.parent / self.state.resumed_from
        parent_json = parent_dir / "session.json"
        if not parent_dir.exists() or not parent_json.exists():
            return None
        try:
            with open(parent_json, encoding="utf-8") as f:
                data = json.load(f)
            parent_state = SessionState.from_dict(data)
        except (OSError, json.JSONDecodeError, KeyError):
            return None
        return Session(self.state.resumed_from, parent_dir, parent_state)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def reload_state(self) -> SessionState:
        """Re-read session.json from disk.

        Useful after another process has updated it — e.g. the orchestrator
        reading state changes written by a worker.
        """
        with open(self.session_json_path, encoding="utf-8") as f:
            data = json.load(f)
        self.state = SessionState.from_dict(data)
        return self.state

    def update_state(self, **changes: object) -> None:
        """Atomically update one or more fields of session.json.

        If `state` is among the changes, validates the transition.
        Always updates `updated_at`.
        """
        if "state" in changes:
            proposed = str(changes["state"])
            if not is_transition_allowed(self.state.state, proposed):  # type: ignore[arg-type]
                raise InvalidStateTransition(self.state.state, proposed)

        # Apply changes to the in-memory state object.
        for key, value in changes.items():
            if not hasattr(self.state, key):
                raise AttributeError(f"SessionState has no field {key!r}")
            setattr(self.state, key, value)
        self.state.updated_at = now_utc()

        atomic_write_json(self.session_json_path, self.state.to_dict())

    # ------------------------------------------------------------------
    # Trace events
    # ------------------------------------------------------------------
    def append_trace_event(self, event: dict) -> None:
        """Append one event to logs/trace.jsonl. O_APPEND, atomic per-write."""
        atomic_append_jsonl(self.trace_path, event)

    # ------------------------------------------------------------------
    # Lifecycle shortcuts
    # ------------------------------------------------------------------
    def mark_complete(self, result: dict) -> None:
        self.update_state(state="completed", result=result)

    def mark_failed(self, reason: str) -> None:
        self.update_state(state="failed", result={"reason": reason})

    def mark_escalated(self, reason: str) -> None:
        self.update_state(state="escalated", result={"reason": reason})

    def __repr__(self) -> str:
        return f"Session(id={self.session_id!r}, state={self.state.state!r})"


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------


def _generate_session_id() -> str:
    """Generate a 12-hex session id. Collision probability is vanishingly small."""
    return f"sess_{secrets.token_hex(6)}"


def _make_subdirs(directory: Path) -> None:
    """Create every subdirectory the layout requires."""
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
    user_id: str | None = None,
    config_overrides: dict | None = None,
    sessions_dir: Path | None = None,
    session_id: str | None = None,
    resumed_from: str | None = None,
) -> Session:
    """Create a new session directory and return a Session handle.

    - Generates a 12-hex session id (or uses the provided one, for tests).
    - Creates every subdirectory in the layout.
    - Writes an initial session.json with state='planning'.
    - Writes a default SESSION.md using the template.

    v0.2 Module 3: `resumed_from` is recorded in session.json when set. The
    new session is otherwise independent — the parent's directory is not
    touched. Use sovereign_agent.session.resume.resume_session() for the
    higher-level API that also populates parent-context hints.
    """
    sessions_root = sessions_dir or DEFAULT_SESSIONS_DIR
    sid = session_id or _generate_session_id()
    directory = sessions_root / sid
    if directory.exists():
        # Extremely unlikely; still, fail loudly rather than overwrite.
        raise SovereignIOError(
            code="SA_IO_ATOMIC_WRITE_FAILED",
            message=f"session directory already exists: {directory}",
            context={"session_id": sid},
        )
    directory.mkdir(parents=True, exist_ok=False)
    _make_subdirs(directory)

    now = now_utc()
    state = SessionState(
        session_id=sid,
        created_at=now,
        updated_at=now,
        scenario=scenario,
        state="planning",
        user_id=user_id,
        config_overrides=config_overrides or {},
        resumed_from=resumed_from,
    )
    atomic_write_json(directory / "session.json", state.to_dict())

    # Default SESSION.md
    md = _DEFAULT_SESSION_MD_TEMPLATE.format(
        session_id=sid,
        scenario=scenario,
        created_at=now.isoformat(),
        task=task or "(no task description provided)",
    )
    (directory / "SESSION.md").write_text(md, encoding="utf-8")

    return Session(sid, directory, state)


def load_session(
    session_id: str,
    sessions_dir: Path | None = None,
) -> Session:
    """Load an existing session by id."""
    sessions_root = sessions_dir or DEFAULT_SESSIONS_DIR
    directory = sessions_root / session_id
    session_json = directory / "session.json"
    if not directory.exists() or not session_json.exists():
        raise SessionNotFoundError(session_id)
    with open(session_json, encoding="utf-8") as f:
        data = json.load(f)
    state = SessionState.from_dict(data)
    return Session(session_id, directory, state)


def list_sessions(
    state_filter: SessionStateName | None = None,
    sessions_dir: Path | None = None,
) -> list[Session]:
    """List all sessions under sessions_dir.

    Returned ordered by created_at descending (newest first).
    """
    sessions_root = sessions_dir or DEFAULT_SESSIONS_DIR
    if not sessions_root.exists():
        return []
    sessions: list[Session] = []
    for entry in sessions_root.iterdir():
        if not entry.is_dir() or not entry.name.startswith("sess_"):
            continue
        if not (entry / "session.json").exists():
            continue
        try:
            session = load_session(entry.name, sessions_dir=sessions_root)
        except Exception:
            # Corrupt session dirs are skipped silently — list should be safe
            # even when some sessions are broken. Doctor will surface them
            # separately.
            continue
        if state_filter is not None and session.state.state != state_filter:
            continue
        sessions.append(session)
    sessions.sort(key=lambda s: s.state.created_at, reverse=True)
    return sessions


def archive_session(session: Session, archive_dir: Path | None = None) -> Path:
    """Move a completed session into an archive subdirectory.

    Used by the default scheduled cleanup task. The session remains on disk
    and inspectable; it's just no longer in the active sessions directory.
    """
    if not session.state.is_terminal():
        raise ValidationError(
            code="SA_VAL_INVALID_STATE_TRANSITION",
            message=f"cannot archive non-terminal session (state={session.state.state})",
            context={"session_id": session.session_id, "state": session.state.state},
        )
    archive = archive_dir or (session.directory.parent / "archive")
    archive.mkdir(parents=True, exist_ok=True)
    dest = archive / session.directory.name
    shutil.move(str(session.directory), str(dest))
    return dest


__all__ = [
    "DEFAULT_SESSIONS_DIR",
    "Session",
    "SessionEscapeError",
    "SessionNotFoundError",
    "InvalidStateTransition",
    "create_session",
    "load_session",
    "list_sessions",
    "archive_session",
]
