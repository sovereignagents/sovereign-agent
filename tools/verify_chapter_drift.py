"""CI check: chapter solutions must re-export the correct production modules.

This is the minitorch "tutorial IS the production code" discipline. Each
chapter's solution.py should re-export the symbols the chapter is teaching.
If someone edits `sovereign_agent/session/queue.py` but forgets to update
`chapters/chapter_02_queue/solution.py`, this check fails in CI.

Run:

    python tools/verify_chapter_drift.py

Exit code: 0 if all chapters match expectations; 1 otherwise.
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

# chapters/ is part of the repo but not an installed package. Ensure the
# repo root is on sys.path so `import chapters.chapter_NN.solution` works
# no matter where this script is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@dataclass
class ChapterExpectation:
    chapter_module: str
    must_export: tuple[str, ...]
    must_come_from: dict[str, str]  # symbol -> source module


CHAPTERS: tuple[ChapterExpectation, ...] = (
    ChapterExpectation(
        chapter_module="chapters.chapter_01_session.solution",
        must_export=(
            "Session",
            "SessionState",
            "create_session",
            "load_session",
            "list_sessions",
            "archive_session",
            "SessionEscapeError",
            "SessionNotFoundError",
            "InvalidStateTransition",
            "ALLOWED_TRANSITIONS",
            "TERMINAL_STATES",
            "is_transition_allowed",
            "now_utc",
        ),
        must_come_from={
            "Session": "sovereign_agent.session.directory",
            "create_session": "sovereign_agent.session.directory",
            "SessionState": "sovereign_agent.session.state",
        },
    ),
    ChapterExpectation(
        chapter_module="chapters.chapter_02_queue.solution",
        must_export=("SessionQueue", "TaskPriority", "QueuedTask"),
        must_come_from={"SessionQueue": "sovereign_agent.session.queue"},
    ),
    ChapterExpectation(
        chapter_module="chapters.chapter_03_ipc.solution",
        must_export=(
            "write_ipc_message",
            "read_and_consume",
            "IpcWatcher",
            "Ticket",
            "TicketState",
            "Manifest",
            "OutputRecord",
            "create_ticket",
        ),
        must_come_from={
            "IpcWatcher": "sovereign_agent.ipc.watcher",
            "Ticket": "sovereign_agent.tickets.ticket",
            "Manifest": "sovereign_agent.tickets.manifest",
        },
    ),
    ChapterExpectation(
        chapter_module="chapters.chapter_04_scheduler.solution",
        must_export=(
            "DriftCorrectedScheduler",
            "ScheduledTask",
            "compute_next_run",
        ),
        must_come_from={
            "DriftCorrectedScheduler": "sovereign_agent.scheduler.drift_corrected",
        },
    ),
    ChapterExpectation(
        chapter_module="chapters.chapter_05_planner_executor.solution",
        must_export=(
            "DefaultPlanner",
            "DefaultExecutor",
            "LoopHalf",
            "StructuredHalf",
            "Handoff",
            "Orchestrator",
            "run_task",
            "register_tool",
            "make_builtin_registry",
        ),
        must_come_from={
            "DefaultPlanner": "sovereign_agent.planner",
            "DefaultExecutor": "sovereign_agent.executor",
            "LoopHalf": "sovereign_agent.halves.loop",
            "Orchestrator": "sovereign_agent.orchestrator.main",
        },
    ),
)


def verify() -> list[str]:
    issues: list[str] = []
    for ch in CHAPTERS:
        try:
            mod = importlib.import_module(ch.chapter_module)
        except ImportError as exc:
            issues.append(f"{ch.chapter_module}: failed to import ({exc})")
            continue

        for name in ch.must_export:
            if not hasattr(mod, name):
                issues.append(f"{ch.chapter_module}: missing required export {name!r}")

        for name, expected_source in ch.must_come_from.items():
            obj = getattr(mod, name, None)
            if obj is None:
                continue  # already reported above
            actual_module = getattr(obj, "__module__", None)
            if actual_module != expected_source:
                issues.append(
                    f"{ch.chapter_module}: {name!r} was expected to come from "
                    f"{expected_source!r} but __module__={actual_module!r}"
                )
    return issues


def main() -> int:
    issues = verify()
    if issues:
        print(f"Chapter drift detected ({len(issues)} issue(s)):")
        for msg in issues:
            print(f"  - {msg}")
        return 1
    print(f"OK — all {len(CHAPTERS)} chapters' solutions match the production package.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
