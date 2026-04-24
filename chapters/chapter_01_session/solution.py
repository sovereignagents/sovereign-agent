"""Chapter 1 solution.

The solution IS the production code — this file just re-exports the
sovereign_agent.session modules so that students who fill in starter.py
can diff their work against the real thing.

The CI script tools/verify_chapter_drift.py checks that this file and
the corresponding production modules stay in sync.
"""

from sovereign_agent.session.directory import (  # noqa: F401
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
from sovereign_agent.session.state import (  # noqa: F401
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    SessionState,
    SessionStateName,
    is_transition_allowed,
    now_utc,
)
