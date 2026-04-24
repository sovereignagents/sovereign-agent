"""sovereign-agent: a framework for building always-on AI agents that you actually own.

The ~30 public names below are the supported API surface. Anything not in
__all__ is internal and may change between minor versions.

See docs/architecture.md for the architecture. See README.md for the
quickstart.
"""

from __future__ import annotations

# Config
from sovereign_agent.config import Config

# Discovery (Pattern A)
from sovereign_agent.discovery import Discoverable, DiscoverySchema, discoverable

# Errors (Pattern C)
from sovereign_agent.errors import (
    ErrorCategory,
    ExternalError,
    IOError,
    SovereignError,
    SystemError,
    ToolError,
    ValidationError,
)
from sovereign_agent.executor import DefaultExecutor, Executor, ExecutorResult

# Halves
from sovereign_agent.halves import Half, HalfResult
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.halves.structured import Rule, StructuredHalf

# Handoff
from sovereign_agent.handoff import Handoff, read_handoff, write_handoff

# IPC (Decisions 3, 4)
from sovereign_agent.ipc import IpcWatcher, send_input, write_ipc_message

# Memory (skeleton; API stable)
from sovereign_agent.memory import (
    MemoryConsolidation,
    MemoryEntry,
    MemoryRetrieval,
    MemoryStore,
    MemoryType,
)

# Observability
from sovereign_agent.observability import (
    ExecutorTrajectoryJudge,
    Judge,
    JudgeResult,
    MemoryUsageJudge,
    PlannerQualityJudge,
    TraceEvent,
    TraceReader,
    generate_session_report,
)

# Orchestrator
from sovereign_agent.orchestrator import Orchestrator, TaskResult, run_task

# Planner / Executor
from sovereign_agent.planner import DefaultPlanner, Planner, Subgoal

# Scheduler (Decision 6)
from sovereign_agent.scheduler import DriftCorrectedScheduler, ScheduledTask

# Session (Decision 1)
from sovereign_agent.session import (
    Session,
    SessionState,
    archive_session,
    create_session,
    list_sessions,
    load_session,
)

# SessionQueue (Decisions 2, 4, 8)
from sovereign_agent.session.queue import SessionQueue, TaskPriority

# Tickets (Decision 9 + Pattern D)
from sovereign_agent.tickets import (
    Manifest,
    OutputRecord,
    Ticket,
    TicketResult,
    TicketState,
    create_ticket,
    list_tickets,
)

# Tools
from sovereign_agent.tools import (
    ToolRegistry,
    ToolResult,
    global_registry,
    make_builtin_registry,
    register_tool,
)

__version__ = "0.2.0a1"

__all__ = [
    # errors
    "SovereignError",
    "SystemError",
    "ValidationError",
    "IOError",
    "ExternalError",
    "ToolError",
    "ErrorCategory",
    # discovery
    "Discoverable",
    "DiscoverySchema",
    "discoverable",
    # session
    "Session",
    "SessionState",
    "create_session",
    "load_session",
    "list_sessions",
    "archive_session",
    # queue
    "SessionQueue",
    "TaskPriority",
    # tickets
    "Ticket",
    "TicketState",
    "TicketResult",
    "Manifest",
    "OutputRecord",
    "create_ticket",
    "list_tickets",
    # ipc
    "IpcWatcher",
    "write_ipc_message",
    "send_input",
    # scheduler
    "DriftCorrectedScheduler",
    "ScheduledTask",
    # tools
    "ToolRegistry",
    "ToolResult",
    "register_tool",
    "global_registry",
    "make_builtin_registry",
    # planner / executor
    "Planner",
    "Subgoal",
    "DefaultPlanner",
    "Executor",
    "ExecutorResult",
    "DefaultExecutor",
    # halves
    "Half",
    "HalfResult",
    "LoopHalf",
    "StructuredHalf",
    "Rule",
    # handoff
    "Handoff",
    "write_handoff",
    "read_handoff",
    # orchestrator
    "Orchestrator",
    "TaskResult",
    "run_task",
    # config
    "Config",
    # observability
    "TraceEvent",
    "TraceReader",
    "Judge",
    "JudgeResult",
    "PlannerQualityJudge",
    "ExecutorTrajectoryJudge",
    "MemoryUsageJudge",
    "generate_session_report",
    # memory
    "MemoryType",
    "MemoryEntry",
    "MemoryStore",
    "MemoryRetrieval",
    "MemoryConsolidation",
    "__version__",
]
