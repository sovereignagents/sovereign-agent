"""Chapter 5 demo — the full working agent.

Runs a planner + executor + tool-call + complete_task trajectory offline
using FakeLLMClient, then prints the resulting session directory so you
can see every artifact the agent produced.

Run:

    python -m chapters.chapter_05_planner_executor.demo

With --real, uses a live LLM (requires NEBIUS_KEY):

    NEBIUS_KEY=... python -m chapters.chapter_05_planner_executor.demo --real

Session artifacts go to your user-data directory so you can inspect them
afterwards:

    Linux:   ~/.local/share/sovereign-agent/demos/ch5/
    macOS:   ~/Library/Application Support/sovereign-agent/demos/ch5/
    Windows: %LOCALAPPDATA%\\sovereign-agent\\demos\\ch5\\

Override with SOVEREIGN_AGENT_DATA_DIR=<path> if you'd rather pin it
somewhere specific.
"""

from __future__ import annotations

import asyncio
import json
import sys

from chapters.chapter_05_planner_executor.solution import (
    DefaultExecutor,
    DefaultPlanner,
    LoopHalf,
    make_builtin_registry,
)
from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    OpenAICompatibleClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent._internal.paths import demo_sessions_dir
from sovereign_agent.session.directory import create_session
from sovereign_agent.tickets.ticket import list_tickets


def _build_fake_client() -> FakeLLMClient:
    """Script a trajectory that:
    1. Plans one subgoal.
    2. Calls write_file to create greet.md.
    3. Calls complete_task to mark the session done.
    4. Returns a brief final answer.
    """
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "write greet.md with 'hello' and mark complete",
                "success_criterion": "file exists and session_complete written",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    write_call = ToolCall(
        id="c1",
        name="write_file",
        arguments={"path": "greet.md", "content": "hello"},
    )
    complete_call = ToolCall(
        id="c2",
        name="complete_task",
        arguments={"result": {"wrote": "greet.md"}},
    )
    return FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[write_call]),
            ScriptedResponse(tool_calls=[complete_call]),
            ScriptedResponse(content="Done: greet.md written and task marked complete."),
        ]
    )


async def run_demo(real: bool) -> None:
    sessions_root = demo_sessions_dir("ch5")
    print(f"Session artifacts will go in: {sessions_root}")
    print()
    session = create_session(
        scenario="ch5-demo",
        task="Write 'hello' to greet.md and mark the task complete.",
        sessions_dir=sessions_root,
    )

    print(f"[1/4] Created session: {session.session_id}")
    print(f"      Directory: {session.directory}")

    if real:
        from sovereign_agent.config import Config

        cfg = Config.from_env()
        print(f"      Using real LLM. Endpoint: {cfg.llm_base_url}")
        print(f"        planner:  {cfg.llm_planner_model}")
        print(f"        executor: {cfg.llm_executor_model}")
        client = OpenAICompatibleClient(
            base_url=cfg.llm_base_url,
            api_key_env=cfg.llm_api_key_env,
        )
        planner_model = cfg.llm_planner_model
        executor_model = cfg.llm_executor_model
    else:
        print("      Using FakeLLMClient (offline, deterministic, free).")
        client = _build_fake_client()
        planner_model = executor_model = "fake"

    tools = make_builtin_registry(session)
    planner = DefaultPlanner(model=planner_model, client=client)
    executor = DefaultExecutor(model=executor_model, client=client, tools=tools)
    half = LoopHalf(planner=planner, executor=executor)

    print("\n[2/4] Running the loop half (plan -> execute -> complete)...")
    result = await half.run(session, {"task": "write greet.md with 'hello' and mark complete"})
    print(f"      next_action: {result.next_action}")
    print(f"      summary:     {result.summary}")

    print("\n[3/4] Tickets produced:")
    for t in list_tickets(session):
        r = t.read_result()
        manifest = r.manifest
        print(
            f"      {t.ticket_id}  {t.operation:40s}  "
            f"{r.state.value:8s}  manifest_ok={manifest.verify() if manifest else 'n/a'}"
        )
        print(f"          summary: {r.summary[:100]}")

    print("\n[4/4] Side effects on disk:")
    greet = session.workspace_dir / "greet.md"
    complete = session.ipc_dir / "session_complete.json"
    print(f"      workspace/greet.md exists: {greet.exists()}")
    if greet.exists():
        print(f"          contents: {greet.read_text()!r}")
    print(f"      ipc/session_complete.json exists: {complete.exists()}")
    trace = session.trace_path
    if trace.exists():
        n_events = sum(1 for _ in trace.open())
        print(f"      logs/trace.jsonl: {n_events} events")

    print("\nDone. Inspect the session with:")
    print(f'      ls -R "{session.directory}"')
    print(f"      cat {session.trace_path}")


def main() -> None:
    real = "--real" in sys.argv
    asyncio.run(run_demo(real=real))


if __name__ == "__main__":
    main()
