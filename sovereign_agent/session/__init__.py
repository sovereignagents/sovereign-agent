"""Session substrate: the unit of everything.

See docs/architecture.md §1.1 and §2.3. Decision 1.
"""

from sovereign_agent.session.directory import (
    DEFAULT_SESSIONS_DIR,
    InvalidStateTransition,
    Session,
    SessionEscapeError,
    SessionNotFoundError,
    archive_session,
    create_session,
    list_sessions,
    load_session,
)
from sovereign_agent.session.state import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    SessionState,
    SessionStateName,
    is_transition_allowed,
    now_utc,
)

__all__ = [
    "DEFAULT_SESSIONS_DIR",
    "Session",
    "SessionState",
    "SessionStateName",
    "SessionEscapeError",
    "SessionNotFoundError",
    "InvalidStateTransition",
    "TERMINAL_STATES",
    "ALLOWED_TRANSITIONS",
    "create_session",
    "load_session",
    "list_sessions",
    "archive_session",
    "is_transition_allowed",
    "now_utc",
]
