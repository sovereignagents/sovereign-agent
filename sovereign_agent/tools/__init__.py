"""Tools: the capability layer. See docs/architecture.md §2.14."""

from sovereign_agent.tools.builtin import make_builtin_registry
from sovereign_agent.tools.registry import (
    ToolRegistry,
    ToolResult,
    global_registry,
    register_tool,
)

__all__ = [
    "ToolRegistry",
    "ToolResult",
    "register_tool",
    "global_registry",
    "make_builtin_registry",
]
