"""Chapter 2 solution — re-exports the production SessionQueue."""

from sovereign_agent.session.queue import (  # noqa: F401
    QueuedTask,
    SessionQueue,
    TaskPriority,
)
