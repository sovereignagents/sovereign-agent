"""Chapter 1 demo — see the session substrate in action.

Run from anywhere (the library handles paths correctly):

    python -m chapters.chapter_01_session.demo

Creates two sessions in your user-data directory and prints where
they live so you can inspect the files afterwards. The location
depends on your OS:

    Linux:   ~/.local/share/sovereign-agent/demos/ch1/
    macOS:   ~/Library/Application Support/sovereign-agent/demos/ch1/
    Windows: %LOCALAPPDATA%\\sovereign-agent\\demos\\ch1\\

Override with SOVEREIGN_AGENT_DATA_DIR=<path> if you'd rather pin it
somewhere specific (useful for teaching — you can delete + rerun to
start fresh every time).
"""

from __future__ import annotations

from pathlib import Path

from chapters.chapter_01_session.solution import (
    create_session,
    list_sessions,
    load_session,
)
from sovereign_agent._internal.paths import demo_sessions_dir


def main() -> None:
    sessions_dir = demo_sessions_dir("ch1")
    print(f"Session artifacts will go in: {sessions_dir}")
    print()

    # Step 1: create a session.
    session = create_session(
        scenario="chapter_1_demo",
        task="Illustrate the session directory layout.",
        sessions_dir=sessions_dir,
    )
    print(f"[1/5] Created session: {session.session_id}")
    print(f"      Directory: {session.directory}")

    # Step 2: emit a couple of trace events.
    session.append_trace_event({"event_type": "demo.started", "actor": "demo"})
    session.append_trace_event(
        {"event_type": "demo.note", "actor": "demo", "payload": {"msg": "hello"}}
    )
    print("[2/5] Appended 2 trace events to logs/trace.jsonl")

    # Step 3: transition state.
    session.update_state(state="executing", planner={"num_subgoals": 2})
    print("[3/5] State: planning -> executing")

    # Step 4: reload from disk. Proves persistence.
    reloaded = load_session(session.session_id, sessions_dir=sessions_dir)
    assert reloaded.state.state == "executing"
    assert reloaded.state.planner == {"num_subgoals": 2}
    print("[4/5] Reloaded from disk; state matches.")

    # Step 5: print the directory tree.
    print("[5/5] Directory tree:")
    _print_tree(session.directory)

    print()
    print("All sessions in this demo directory:")
    for s in list_sessions(sessions_dir=sessions_dir):
        print(f"  {s.session_id}  state={s.state.state}")


def _print_tree(root: Path, prefix: str = "  ") -> None:
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        depth = len(rel.parts) - 1
        indent = prefix + "  " * depth
        marker = "/" if p.is_dir() else ""
        size = ""
        if p.is_file():
            size = f"  ({p.stat().st_size}B)"
        print(f"{indent}{p.name}{marker}{size}")


if __name__ == "__main__":
    main()
