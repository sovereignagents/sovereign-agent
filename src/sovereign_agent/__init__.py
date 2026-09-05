"""Sovereign Agent: an executable textbook for Zero-Employee Organizations.

Importing this package performs no filesystem, process, or network activity.
"""

from __future__ import annotations

from sovereign_agent.errors import Refusal
from sovereign_agent.ids import new_id
from sovereign_agent.models import Actor, Outcome, StatementOfWork
from sovereign_agent.organization import Organization

__version__ = "1.4.0"

__all__ = [
    "Actor",
    "Organization",
    "Outcome",
    "Refusal",
    "StatementOfWork",
    "__version__",
    "new_id",
]
