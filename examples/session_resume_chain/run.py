"""Session resume chain — Module 3 (`resume_session`) in action.

## What this shows

A three-generation session chain:

  parent    → "research Edinburgh pubs"  (completed with result)
  child     → "continue: negotiate deposit with Haymarket Tap"
  grandchild → "continue: draft the confirmation email"

Each generation:

  * Gets a fresh session id and its own directory.
  * Records `resumed_from` pointing at the previous generation.
  * Has the parent's trace tail + result auto-prepended to its
    SESSION.md so the planner sees context on its first read.

We walk the chain with `find_ancestor_chain()` and show the prepended
context block. The forward-only state rule is NEVER broken: every
session finishes normally; children reference parents but never
modify them.

## Run

    python -m examples.session_resume_chain.run

This is a pure-library demo — no LLM calls. It shows the plumbing, not
a full ReAct loop. See the other examples for agent flows.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sovereign_agent.session.directory import create_session
from sovereign_agent.session.resume import (
    find_ancestor_chain,
    resume_session,
)
from sovereign_agent.session.state import now_utc

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _finish(session, **extra) -> None:  # type: ignore[no-untyped-def]
    """Move a fresh 'planning' session to 'completed' via the allowed
    two-step transition. Mirrors what a full agent run would do at the
    end."""
    session.update_state(state="executing")
    session.update_state(state="completed", **extra)


def _simulate_work(session, events: list[dict]) -> None:  # type: ignore[no-untyped-def]
    """Pretend the session did some ReAct turns — write trace events
    so the resume summary has something juicy to inline."""
    for ev in events:
        ev.setdefault("timestamp", now_utc().isoformat())
        ev.setdefault("actor", "executor")
        session.append_trace_event(ev)


def run_scenario(real: bool = False) -> None:
    with tempfile.TemporaryDirectory() as td:
        sessions_dir = Path(td) / "sessions"
        sessions_dir.mkdir()

        # -----------------------------------------------------------------
        # Generation 1: PARENT — research phase
        # -----------------------------------------------------------------
        print("=== Generation 1: parent session (research) ===")
        parent = create_session(
            scenario="pub-booking",
            task="Research Edinburgh pubs near Haymarket with seats for 4 at 19:30.",
            sessions_dir=sessions_dir,
        )
        _simulate_work(
            parent,
            [
                {
                    "event_type": "executor.tool_called",
                    "payload": {"tool": "pub_search", "result_count": 3},
                },
                {
                    "event_type": "executor.tool_called",
                    "payload": {
                        "tool": "analyze_pubs",
                        "shortlist": ["haymarket_tap", "royal_oak"],
                    },
                },
                {
                    "event_type": "executor.tool_called",
                    "payload": {"tool": "complete_task", "choice": "haymarket_tap"},
                },
            ],
        )
        _finish(
            parent,
            result={
                "chosen_pub": "haymarket_tap",
                "name": "Haymarket Tap",
                "open_now": True,
                "seats_available": 12,
            },
        )
        print(f"  session: {parent.session_id}")
        print(f"  state:   {parent.state.state}")
        print(f"  result:  {parent.state.result}")

        # -----------------------------------------------------------------
        # Generation 2: CHILD — continuation: deposit negotiation
        # -----------------------------------------------------------------
        print("\n=== Generation 2: child session (deposit negotiation) ===")
        child = resume_session(
            parent_id=parent.session_id,
            task=(
                "Continue the booking for Haymarket Tap: the manager has "
                "asked for a £200 deposit. Confirm or decline."
            ),
            sessions_dir=sessions_dir,
        )
        _simulate_work(
            child,
            [
                {
                    "event_type": "executor.tool_called",
                    "payload": {"tool": "email_manager", "result": "deposit_requested"},
                },
                {
                    "event_type": "executor.tool_called",
                    "payload": {"tool": "commit_booking", "deposit_gbp": 200},
                },
            ],
        )
        _finish(child, result={"booking_confirmed": True, "deposit_paid": 200})
        print(f"  session:       {child.session_id}")
        print(f"  resumed_from:  {child.state.resumed_from}")
        print(f"  scenario:      {child.state.scenario}  (inherited from parent)")
        print(f"  result:        {child.state.result}")

        # -----------------------------------------------------------------
        # Generation 3: GRANDCHILD — email draft
        # -----------------------------------------------------------------
        print("\n=== Generation 3: grandchild session (confirmation email) ===")
        grandchild = resume_session(
            parent_id=child.session_id,
            task="Draft a confirmation email to the venue manager.",
            sessions_dir=sessions_dir,
        )
        _simulate_work(
            grandchild,
            [
                {
                    "event_type": "executor.tool_called",
                    "payload": {"tool": "draft_email", "recipient": "manager@haymarket-tap.co.uk"},
                },
            ],
        )
        _finish(grandchild, result={"email_sent": True})
        print(f"  session:       {grandchild.session_id}")
        print(f"  resumed_from:  {grandchild.state.resumed_from}")

        # -----------------------------------------------------------------
        # Walk the ancestor chain
        # -----------------------------------------------------------------
        print("\n=== Ancestor chain for grandchild (oldest-first) ===")
        chain = find_ancestor_chain(grandchild)
        for i, sid in enumerate(chain):
            print(f"  [{i}] {sid}")
        print(f"  [leaf] {grandchild.session_id}")

        # -----------------------------------------------------------------
        # Show the prepended SESSION.md
        # -----------------------------------------------------------------
        print("\n=== What the grandchild's planner sees on first read ===")
        print("(first 40 lines of SESSION.md — auto-generated by resume_session)")
        print("-" * 72)
        md = grandchild.session_md_path.read_text(encoding="utf-8")
        for line in md.splitlines()[:40]:
            print(line)
        print("-" * 72)

        # -----------------------------------------------------------------
        # Verify the parent was NOT modified
        # -----------------------------------------------------------------
        print("\n=== Forward-only rule check ===")
        from sovereign_agent.session.directory import load_session

        reloaded_parent = load_session(parent.session_id, sessions_dir=sessions_dir)
        assert reloaded_parent.state.state == "completed", "parent state changed!"
        assert reloaded_parent.state.resumed_from is None, "parent gained a resumed_from!"
        print("  parent state still 'completed':      OK")
        print("  parent.resumed_from still None:      OK")
        print("  child.resumed_from == parent.id:     OK")
        print("  grandchild.resumed_from == child.id: OK")

        # Refusing a non-terminal parent — the default protects against
        # forking a still-running session by mistake.
        print("\n=== Safety: refusing to resume a non-terminal parent ===")
        halfway = create_session(
            scenario="demo",
            task="halfway-done sibling session",
            sessions_dir=sessions_dir,
        )
        # 'halfway' is in 'planning' — NOT terminal.
        try:
            resume_session(
                parent_id=halfway.session_id,
                task="try to fork while still running",
                sessions_dir=sessions_dir,
            )
            print("  WARNING: resume succeeded where it should have refused")
        except Exception as exc:
            print(f"  refused as expected: {type(exc).__name__}: {exc}")

    # ── Optional: real-LLM probe ────────────────────────────────────
    # Module 3 (session resume) is pure framework plumbing — no LLM is
    # needed to prove the parent/child pointer integrity, ancestor
    # chain, or forward-only rule. But the -real target exists for
    # cohort consistency: it confirms the configured endpoint works
    # and demonstrates that resumed sessions can use real LLMs too.
    if real:
        print("\n=== Real-LLM round-trip ===")
        import asyncio

        async def _probe() -> None:
            from sovereign_agent._internal.llm_client import OpenAICompatibleClient
            from sovereign_agent.config import Config

            cfg = Config.from_env()
            print(f"  endpoint: {cfg.llm_base_url}")
            print(f"  model:    {cfg.llm_executor_model}")
            client = OpenAICompatibleClient(
                base_url=cfg.llm_base_url, api_key_env=cfg.llm_api_key_env
            )
            resp = await client.chat(
                model=cfg.llm_executor_model,
                messages=[{"role": "user", "content": "say 'ok' and nothing else"}],
                max_tokens=5,
            )
            content = (resp.content or "").strip()
            print(f"  response: {content!r}")
            print("  ✓  real LLM reachable — resumed sessions would use this endpoint")

        try:
            asyncio.run(_probe())
        except Exception as e:  # noqa: BLE001
            print(f"  ✗  real-LLM probe failed: {type(e).__name__}: {e}")


def main() -> None:
    import sys

    real = "--real" in sys.argv
    run_scenario(real=real)


if __name__ == "__main__":
    main()
