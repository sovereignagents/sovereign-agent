"""Chapter 5 solution.

Re-exports the production classes that make up the working agent. The
solution IS the framework — `tools/verify_chapter_drift.py` checks this
file and the corresponding production modules stay in sync.
"""

from sovereign_agent.executor import (  # noqa: F401
    DefaultExecutor,
    Executor,
    ExecutorResult,
)
from sovereign_agent.halves import Half, HalfResult  # noqa: F401
from sovereign_agent.halves.loop import LoopHalf  # noqa: F401
from sovereign_agent.halves.structured import Rule, StructuredHalf  # noqa: F401
from sovereign_agent.handoff import (  # noqa: F401
    Handoff,
    read_handoff,
    write_handoff,
)
from sovereign_agent.orchestrator import (  # noqa: F401
    Orchestrator,
    TaskResult,
    run_task,
)
from sovereign_agent.planner import DefaultPlanner, Planner, Subgoal  # noqa: F401
from sovereign_agent.tools import (  # noqa: F401
    ToolRegistry,
    ToolResult,
    make_builtin_registry,
    register_tool,
)
