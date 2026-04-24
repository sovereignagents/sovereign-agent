"""Internal helper for surfacing missing optional extras with a helpful message.

Used by modules under sovereign_agent that depend on optional deps, so that
`from sovereign_agent.voice import ...` without the [voice] extra installed
yields a clear instruction instead of a bare ModuleNotFoundError.
"""

from __future__ import annotations

import importlib
from typing import Any


class MissingExtraError(ImportError):
    """Raised when an optional dependency is required but not installed."""


def requires_extra(extra: str, *module_names: str) -> list[Any]:
    """Import the named modules; raise MissingExtraError with an install hint
    if any of them are missing.

    Usage:

        evidently = requires_extra("evidently", "evidently")[0]
    """
    missing: list[str] = []
    modules: list[Any] = []
    for name in module_names:
        try:
            modules.append(importlib.import_module(name))
        except ImportError:
            missing.append(name)
    if missing:
        raise MissingExtraError(
            f"sovereign-agent[{extra}] is not installed. "
            f"Missing modules: {', '.join(missing)}. "
            f"Run: pip install sovereign-agent[{extra}]"
        )
    return modules


__all__ = ["MissingExtraError", "requires_extra"]
