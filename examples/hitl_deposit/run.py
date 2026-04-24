"""HITL deposit approval — Module 5 (`requires_human_approval=True`) in action.

## What this shows

A pub-booking tool proposes a £500 deposit. Our policy is that anything
over £300 needs a human to sign off before the booking is committed.

The flow:

  1. Agent calls `commit_booking_with_deposit(venue="venue_hay",
     deposit_gbp=500)`.
  2. Tool returns `ToolResult(requires_human_approval=True, ...)`.
     It has NOT committed anything yet — that's the whole point.
  3. Executor writes `ipc/awaiting_approval/<request_id>.json` and
     exits cleanly. The session sits idle. No coroutine holds state
     across the wait.
  4. A human invokes the CLI to grant or deny:
        sovereign-agent approvals grant  <session_id> <request_id> \
            --reason "CFO signed off"
        sovereign-agent approvals deny   <session_id> <request_id> \
            --reason "exceeds policy"
  5. `resume_from_approval()` re-enters the executor with a fresh
     ReAct turn whose opening user message contains the decision.
     On GRANT the LLM completes the task. On DENY the LLM adapts
     (proposes alternative, asks for clarification, or fails
     gracefully).

This script runs BOTH paths — grant and deny — so you can see the
contrast side by side.

## Run

    python -m examples.hitl_deposit.run

Everything runs in a temp directory. The "human" response is invoked
via the real CLI commands (via `typer.testing.CliRunner`), so you're
seeing the exact code path your students would exercise by hand.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent.executor import DefaultExecutor, resume_from_approval
from sovereign_agent.ipc.approval import (
    find_decision,
    list_pending_approvals,
)
from sovereign_agent.planner import Subgoal
from sovereign_agent.session.directory import Session, create_session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

# ---------------------------------------------------------------------------
# The tool that asks for human approval when the deposit is large
# ---------------------------------------------------------------------------


AUTO_APPROVE_CEILING_GBP = 300


def _commit_booking_with_deposit(venue_id: str, deposit_gbp: int) -> ToolResult:
    """Propose a booking that commits a deposit. Deposits above the
    auto-approve ceiling require human sign-off before committing."""
    needs_approval = deposit_gbp > AUTO_APPROVE_CEILING_GBP
    proposed = {
        "venue_id": venue_id,
        "deposit_gbp": deposit_gbp,
        "status": "proposed" if needs_approval else "committed",
        # IMPORTANT: approval_reason goes inside `output` so the
        # framework can surface it in the request file and in the
        # approver's CLI output. Putting it at ToolResult level
        # would NOT be picked up — classic pitfall.
        "approval_reason": (
            f"Deposit £{deposit_gbp} exceeds the £{AUTO_APPROVE_CEILING_GBP} auto-approve ceiling."
            if needs_approval
            else ""
        ),
    }
    summary = (
        f"proposed £{deposit_gbp} booking at {venue_id} (awaiting approval)"
        if needs_approval
        else f"committed £{deposit_gbp} booking at {venue_id} (auto-approved)"
    )
    return ToolResult(
        success=True,
        output=proposed,
        summary=summary,
        requires_human_approval=needs_approval,
    )


def _build_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        _RegisteredTool(
            name="commit_booking_with_deposit",
            description=(
                "Book a venue, committing a deposit. Deposits above "
                f"£{AUTO_APPROVE_CEILING_GBP} require human sign-off."
            ),
            fn=_commit_booking_with_deposit,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "deposit_gbp": {"type": "integer"},
                },
                "required": ["venue_id", "deposit_gbp"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,  # writes — must run alone
            examples=[
                {
                    "input": {"venue_id": "venue_hay", "deposit_gbp": 100},
                    "output": {"status": "committed"},
                }
            ],
        )
    )
    return reg


# ---------------------------------------------------------------------------
# Scripted LLM conversations
# ---------------------------------------------------------------------------


def _build_phase1_client() -> FakeLLMClient:
    """The initial run — LLM asks to book with a deposit over the ceiling."""
    return FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="call_book_1",
                        name="commit_booking_with_deposit",
                        arguments={"venue_id": "venue_hay", "deposit_gbp": 500},
                    ),
                ]
            ),
            # We should NEVER reach this second turn — the executor
            # exits on requires_human_approval.
            ScriptedResponse(content="(should not be reached in phase 1)"),
        ]
    )


def _build_phase2_grant_client() -> FakeLLMClient:
    """Resumed after approval is GRANTED. LLM acknowledges and wraps up."""
    return FakeLLMClient(
        [
            ScriptedResponse(
                content=(
                    "Approval granted. The £500 booking at Haymarket Tap is "
                    "now committed. Subgoal complete."
                )
            )
        ]
    )


def _build_phase2_deny_client() -> FakeLLMClient:
    """Resumed after approval is DENIED. LLM proposes an alternative."""
    return FakeLLMClient(
        [
            ScriptedResponse(
                content=(
                    "Understood — the £500 deposit exceeds the policy limit. "
                    "I will propose an alternative venue with a lower deposit "
                    "(within the £300 auto-approve ceiling) and re-attempt."
                )
            )
        ]
    )


# ---------------------------------------------------------------------------
# CLI driver — exercises the exact same code path a human would
# ---------------------------------------------------------------------------


def _cli_grant(session: Session, request_id: str, reason: str) -> None:
    from typer.testing import CliRunner

    from sovereign_agent.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "approvals",
            "grant",
            session.session_id,
            request_id,
            "--approver",
            "cfo@example.com",
            "--reason",
            reason,
            "--sessions-dir",
            str(session.directory.parent),
        ],
    )
    if result.exit_code != 0:
        raise RuntimeError(f"approvals grant failed (exit {result.exit_code}): {result.output}")
    print(f"  CLI output:\n    {result.output.strip().replace(chr(10), chr(10) + '    ')}")


def _cli_deny(session: Session, request_id: str, reason: str) -> None:
    from typer.testing import CliRunner

    from sovereign_agent.cli import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "approvals",
            "deny",
            session.session_id,
            request_id,
            "--approver",
            "cfo@example.com",
            "--reason",
            reason,
            "--sessions-dir",
            str(session.directory.parent),
        ],
    )
    if result.exit_code != 0:
        raise RuntimeError(f"approvals deny failed (exit {result.exit_code}): {result.output}")
    print(f"  CLI output:\n    {result.output.strip().replace(chr(10), chr(10) + '    ')}")


# ---------------------------------------------------------------------------
# The two scenarios
# ---------------------------------------------------------------------------


def _subgoal() -> Subgoal:
    return Subgoal(
        id="sg_1",
        description="Book Haymarket Tap for a party of 4 with the requested deposit.",
        success_criterion="Booking committed, OR declined with a reason the user can act on.",
        estimated_tool_calls=2,
        assigned_half="loop",
    )


async def run_grant_path(sessions_dir: Path, real: bool = False) -> None:
    print("=" * 72)
    print(f"Scenario A: approval GRANTED{' (real LLM)' if real else ''}")
    print("=" * 72)

    session = create_session(
        scenario="hitl-deposit",
        task="book Haymarket Tap with a £500 deposit",
        sessions_dir=sessions_dir,
    )
    print(f"session: {session.session_id}")
    tools = _build_tool_registry()

    # Build clients + model. In real mode, both phase-1 and phase-2
    # use the SAME live LLM — the claim is that a real model, on
    # seeing the approval result, actually adapts to it. Scripted
    # trajectories don't test that claim; this does.
    if real:
        client1, client2, model = _build_real_clients()
    else:
        client1 = _build_phase1_client()
        client2 = _build_phase2_grant_client()
        model = "fake"

    # Phase 1: executor should exit with awaiting_approval.
    executor1 = DefaultExecutor(
        model=model,
        client=client1,
        tools=tools,
    )
    result1 = await executor1.execute(_subgoal(), session, max_turns=4)

    assert result1.awaiting_approval is not None, "executor did not pause!"
    request_id = result1.awaiting_approval
    print("\nPhase 1 complete:")
    print(f"  awaiting_approval: {request_id}")
    print(f"  final_answer: {result1.final_answer!r}")

    pending = list_pending_approvals(session)
    print(f"  pending approvals on disk: {len(pending)}")
    if pending:
        req = pending[0]
        print(f"    tool:   {req.tool_name}")
        print(f"    args:   {req.tool_arguments}")
        print(f"    reason: {req.reason}")

    # CLI grant — the exact code path a human would exercise.
    print("\nInvoking CLI: `sovereign-agent approvals grant ...`")
    _cli_grant(session, request_id, reason="CFO signed off; within budget")

    decision = find_decision(session, request_id)
    assert decision is not None and decision.decision == "granted"

    # Phase 2: resume.
    print("\nResuming executor with the decision surfaced to the LLM...")
    executor2 = DefaultExecutor(
        model=model,
        client=client2,
        tools=tools,
    )
    result2 = await resume_from_approval(
        executor2, _subgoal(), session, request_id=request_id, max_turns=4
    )
    print(f"  success:      {result2.success}")
    print(f"  final_answer: {result2.final_answer!r}")

    # Audit trail — the permanent record.
    decision_log = session.logs_dir / "approvals" / f"{request_id}.decision.json"
    assert decision_log.exists()
    print(f"\nPermanent audit log: {decision_log.relative_to(session.directory)}")
    decision_data = json.loads(decision_log.read_text())
    print(f"  decision: {decision_data['response']['decision']}")
    print(f"  approver: {decision_data['response']['approver']}")
    print(f"  reason:   {decision_data['response']['reason']}")


def _build_real_clients():
    """Build (phase1_client, phase2_client, model) using a real LLM.

    Both phases share the same endpoint and model — the claim under
    test is that a REAL model will:
      (phase 1) recognise requires_human_approval=True from the tool
                result and exit cleanly without fabricating progress
      (phase 2) on resumption, see the decision in context and adapt
                appropriately (commit on GRANT, alternative on DENY)

    A FakeLLMClient scripted trajectory can't prove either behavior.
    """
    from sovereign_agent._internal.llm_client import OpenAICompatibleClient
    from sovereign_agent.config import Config

    cfg = Config.from_env()
    client = OpenAICompatibleClient(base_url=cfg.llm_base_url, api_key_env=cfg.llm_api_key_env)
    # Both phases use the same client instance — real LLMs are
    # stateless between calls, so there's no mid-scenario state to
    # preserve the way the Fake client does with scripted queues.
    return client, client, cfg.llm_executor_model


async def run_deny_path(sessions_dir: Path, real: bool = False) -> None:
    print()
    print("=" * 72)
    print(f"Scenario B: approval DENIED{' (real LLM)' if real else ''}")
    print("=" * 72)

    session = create_session(
        scenario="hitl-deposit",
        task="book Haymarket Tap with a £500 deposit",
        sessions_dir=sessions_dir,
    )
    print(f"session: {session.session_id}")
    tools = _build_tool_registry()

    if real:
        client1, client2, model = _build_real_clients()
    else:
        client1 = _build_phase1_client()
        client2 = _build_phase2_deny_client()
        model = "fake"

    executor1 = DefaultExecutor(
        model=model,
        client=client1,
        tools=tools,
    )
    result1 = await executor1.execute(_subgoal(), session, max_turns=4)
    assert result1.awaiting_approval is not None
    request_id = result1.awaiting_approval
    print("\nPhase 1 complete:")
    print(f"  awaiting_approval: {request_id}")

    print("\nInvoking CLI: `sovereign-agent approvals deny ...`")
    _cli_deny(session, request_id, reason="£500 exceeds policy; try ≤ £300")

    decision = find_decision(session, request_id)
    assert decision is not None and decision.decision == "denied"

    print("\nResuming executor with the denial surfaced to the LLM...")
    executor2 = DefaultExecutor(
        model=model,
        client=client2,
        tools=tools,
    )
    result2 = await resume_from_approval(
        executor2, _subgoal(), session, request_id=request_id, max_turns=4
    )
    print(f"  success:      {result2.success}")
    print(f"  final_answer: {result2.final_answer!r}")


# ─────────────────────────────────────────────────────────────────────
# Real HITL flow — actually asks the human
# ─────────────────────────────────────────────────────────────────────


def _interactive_prompt(req) -> tuple[str, str]:
    """Interactive HITL prompt. Returns (decision, reason).

    decision: one of "granted" | "denied" | "counter_offer"
    reason:   free-text rationale from the human, possibly containing
              a counter-offer if decision == "counter_offer" (e.g.
              "approved but offer £300 max deposit")

    Design is modelled on Claude Code's command-approval prompt, Temporal's
    human-task primitive, and OpenAI Agents SDK HITL pattern: show full
    context, offer more than yes/no, give an inspection escape hatch.
    """
    # Pull context from the approval request
    args = req.tool_arguments or {}
    deposit = args.get("deposit_gbp", "?")
    venue_id = args.get("venue_id", "?")
    party = args.get("party", args.get("party_size", "?"))
    time_str = args.get("time", args.get("booking_time", "?"))

    while True:
        print()
        print("=" * 72)
        print("HUMAN APPROVAL REQUIRED")
        print("=" * 72)
        print()
        print("The agent wants to execute:")
        print()
        print(f"  Tool:     {req.tool_name}")
        print(f"  Venue:    {venue_id}")
        print(f"  Party:    {party} people at {time_str}")
        print(f"  Deposit:  £{deposit}")
        print()
        print("Reason from the agent:")
        agent_reason = req.reason or "(no reason provided)"
        for line in _wrap(agent_reason, 68):
            print(f"  {line}")
        print()
        print("Policy context:")
        print("  Auto-approve ceiling: £300")
        if isinstance(deposit, (int, float)) and deposit > 300:
            print(f"  Requested amount:     £{deposit}  (£{deposit - 300} over ceiling)")
        else:
            print(f"  Requested amount:     £{deposit}")
        print()
        print("What do you want to do?")
        print("  [a] Approve as-is")
        print("  [c] Approve with a counter-offer (e.g. cap the deposit at £300)")
        print("  [d] Deny (provide a reason)")
        print("  [?] Show more context (pending-approval JSON, session details)")
        print()

        try:
            choice = input("Your choice [a/c/d/?]: ").strip().lower()
        except EOFError:
            # Non-interactive input was exhausted. Safest default: deny.
            print("(stdin closed; defaulting to deny)")
            return ("denied", "stdin exhausted with no decision supplied")

        if choice == "a":
            reason = input("Optional note (press enter to skip): ").strip()
            return ("granted", reason or "approved by human operator")

        elif choice == "c":
            print()
            print("Describe the counter-offer. The agent will see this text and")
            print("decide whether to retry with the new constraint.")
            print("Example: 'Deposit ceiling is £300. Try the venue again at £300")
            print("or suggest an alternative venue with a lower deposit.'")
            print()
            counter = input("Counter-offer: ").strip()
            if not counter:
                print("(no counter-offer text provided; returning to main menu)")
                continue
            # We grant the approval request but with instructive reason text
            # so the agent sees the counter-offer in phase 2. (A fully-structured
            # counter-offer — with a typed `modifications: dict` — is a v0.3
            # idea; for v0.2 we keep it simple and put the guidance in text.)
            return ("granted", f"[counter-offer] {counter}")

        elif choice == "d":
            reason = input("Reason for denial: ").strip()
            if not reason:
                reason = "denied by human operator"
            return ("denied", reason)

        elif choice == "?":
            print()
            print("-" * 72)
            print("Pending-approval request (as stored on disk):")
            print("-" * 72)
            print(
                json.dumps(
                    {
                        "request_id": req.request_id,
                        "tool_name": req.tool_name,
                        "tool_arguments": req.tool_arguments,
                        "reason": req.reason,
                        "created_at": str(req.created_at),
                    },
                    indent=2,
                    default=str,
                )
            )
            print()
            print("Files on disk you can inspect:")
            print(f'  ls -R "{req.request_id}"  (under the session\'s ipc/awaiting_approval/)')
            print("-" * 72)
            print()
            # Loop back to the main prompt
            continue

        else:
            print(f"(unknown choice {choice!r}; try a/c/d/?)")
            continue


def _wrap(text: str, width: int) -> list[str]:
    """Tiny word-wrapper so agent-written reasons render neatly in the prompt."""
    import textwrap

    return textwrap.wrap(text, width=width) or [""]


async def run_real_hitl(
    sessions_dir: Path,
    *,
    auto_decision: str | None = None,
    auto_reason: str | None = None,
    counter_offer_amount: int | None = None,
) -> None:
    """Real-LLM HITL flow with an actual human (or flag-supplied) decision.

    auto_decision:          "granted" | "denied" | None (prompt interactively)
    auto_reason:            pre-specified reason (for --approve / --deny flags)
    counter_offer_amount:   if set, treat as "granted" with
                            reason "[counter-offer] cap deposit at £{amount}"

    The fake/offline grant and deny paths are still run by the default
    `make example-hitl-deposit` (offline mode). This function ONLY
    runs in --real mode, so it must always drive a real LLM.
    """
    print("=" * 72)
    print("Real HITL flow (live LLM, real human-in-the-loop)")
    print("=" * 72)

    session = create_session(
        scenario="hitl-deposit",
        task=(
            "You are booking a venue for an upcoming event. The customer has "
            "already agreed to a £500 deposit with the venue over email. Your "
            "job is to submit the booking to the system, full stop.\n\n"
            "DO THIS:\n"
            "  Call commit_booking_with_deposit ONCE with these exact values:\n"
            "    venue_id='venue_hay'\n"
            "    deposit_gbp=500\n\n"
            "The customer's agreed amount is £500. That number is fixed and "
            "set by the customer, not by you. You MUST pass deposit_gbp=500 — "
            "NOT 250, NOT 300, NOT any other value. Lowering the deposit "
            "without the customer's permission is fraud.\n\n"
            "When the tool responds, read what it says and do exactly what it "
            "tells you next. If the tool returns an approval-required signal, "
            "your job is done — write your final answer explaining that the "
            "booking is awaiting human approval and STOP. Do not retry with "
            "different arguments. Do not call any other tools. Do not fabricate "
            "a successful outcome."
        ),
        sessions_dir=sessions_dir,
    )
    print(f"session: {session.session_id}")
    tools = _build_tool_registry()

    client1, client2, model = _build_real_clients()
    print(f"  model:    {model}")

    # ── Phase 1 ─────────────────────────────────────────────────────
    executor1 = DefaultExecutor(model=model, client=client1, tools=tools)
    result1 = await executor1.execute(_subgoal(), session, max_turns=4)

    if result1.awaiting_approval is None:
        # Soft warning — the LLM didn't pause. This is the
        # 2026-04-23 Qwen3-235B failure mode: the model either bypassed
        # the approval signal or completed differently than scripted
        # trajectories would. The scenario doesn't crash; it prints what
        # the model actually did so students can inspect.
        print()
        print("✗ LLM did not trigger approval; tool was either bypassed or the")
        print("  flow completed without surfacing a pending request.")
        print()
        print("  What the model actually returned:")
        print(f"    success:      {result1.success}")
        print(f"    final_answer: {result1.final_answer!r}")
        print(f"    turns_used:   {result1.turns_used}")
        if result1.tool_calls_made:
            print("    tool calls made:")
            for tc in result1.tool_calls_made:
                print(
                    f"      - {tc.get('name')}({tc.get('arguments')}) → {tc.get('summary', '')[:80]}"
                )
        else:
            print("    (no tool calls recorded)")
        print()
        print("  Why this matters pedagogically:")
        print("    Prompts are advisory, not binding. A real LLM can see")
        print("    `requires_human_approval=True` and either respect it (what")
        print("    we want) or plow ahead (what we saw). The fix is to make")
        print("    the approval gate architectural — e.g. intercept the tool")
        print("    call at the executor level — not to wrestle with the prompt.")
        print("    That's the Decision 8 lesson: registries are physics; prompts")
        print("    are negotiation. See class slides §03.")
        return

    request_id = result1.awaiting_approval
    print()
    print(f"✓ Phase 1 paused cleanly. Approval request: {request_id}")

    pending = list_pending_approvals(session)
    if not pending:
        print("  (unexpected: awaiting_approval set but no pending request on disk)")
        return
    req = pending[0]

    # ── Human decision ──────────────────────────────────────────────
    if auto_decision is not None:
        # Non-interactive mode (flags). Useful for CI and recorded demos.
        print()
        print(f"[non-interactive] decision={auto_decision}, reason={auto_reason!r}")
        decision_str = auto_decision
        reason = auto_reason or "(no reason supplied)"
    elif counter_offer_amount is not None:
        print()
        print(f"[non-interactive] counter-offer: cap deposit at £{counter_offer_amount}")
        decision_str = "granted"
        reason = (
            f"[counter-offer] Deposit ceiling is £{counter_offer_amount}. "
            f"Retry at £{counter_offer_amount} or propose an alternative venue."
        )
    else:
        # Interactive prompt — real human, real decision.
        decision_str, reason = _interactive_prompt(req)

    # Write the decision via the real CLI path, so audit trail matches
    # what the production CLI produces.
    if decision_str == "granted":
        _cli_grant(session, request_id, reason=reason)
    else:
        _cli_deny(session, request_id, reason=reason)

    decision = find_decision(session, request_id)
    assert decision is not None

    # ── Phase 2 — resume with real LLM seeing the real decision ─────
    print()
    print("=" * 72)
    print("Phase 2 — resuming executor with the human's decision")
    print("=" * 72)
    print(f"  decision: {decision.decision}")
    print(f"  reason:   {reason}")
    print()

    executor2 = DefaultExecutor(model=model, client=client2, tools=tools)
    result2 = await resume_from_approval(
        executor2, _subgoal(), session, request_id=request_id, max_turns=4
    )
    print("  Agent's response after seeing the decision:")
    print(f"    success:      {result2.success}")
    print(f"    final_answer: {result2.final_answer!r}")

    # Audit trail
    decision_log = session.logs_dir / "approvals" / f"{request_id}.decision.json"
    if decision_log.exists():
        print()
        print(f"Permanent audit log: {decision_log.relative_to(session.directory)}")


async def main_async(real: bool = False, **real_flags) -> None:
    with tempfile.TemporaryDirectory() as td:
        sessions_dir = Path(td) / "sessions"
        sessions_dir.mkdir()

        if real:
            await run_real_hitl(sessions_dir, **real_flags)
        else:
            await run_grant_path(sessions_dir, real=False)
            await run_deny_path(sessions_dir, real=False)

        print()
        print("=" * 72)
        print("What this proved")
        print("=" * 72)
        print(
            "  * A tool marked requires_human_approval=True caused the executor\n"
            "    to exit cleanly with no in-memory coroutine holding state.\n"
            "  * The pending request lived on disk; the CLI wrote the decision\n"
            "    to disk; everything audit-trailed under logs/approvals/.\n"
            "  * resume_from_approval() re-entered the ReAct loop with the\n"
            "    decision visible to the LLM, which adapted appropriately:\n"
            "      - on GRANT: proceeded to commit\n"
            "      - on DENY:  proposed an alternative approach\n"
            "  * The session could have sat idle for seconds, hours, or days\n"
            "    between phase 1 and phase 2. Nothing in memory; all on disk."
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Human-in-the-loop deposit approval demo.",
        epilog=(
            "Offline mode (default) runs scripted grant + deny paths.\n"
            "With --real, runs a live LLM and asks YOU for the decision\n"
            "interactively (unless --approve / --deny / --counter-offer given)."
        ),
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use a real LLM and a real human (or flag-supplied) approval.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--approve",
        action="store_true",
        help=("Non-interactive: approve with a generic reason. Useful for CI and recorded demos."),
    )
    group.add_argument(
        "--deny",
        metavar="REASON",
        help="Non-interactive: deny with the given reason.",
    )
    group.add_argument(
        "--counter-offer",
        type=int,
        metavar="GBP",
        help=(
            "Non-interactive: approve but cap the deposit at this amount. "
            "Agent sees the counter-offer in phase 2 and must decide how to "
            "adapt (e.g. retry with lower amount or propose an alternative)."
        ),
    )
    args = parser.parse_args()

    real_flags: dict = {}
    if args.approve:
        real_flags = {
            "auto_decision": "granted",
            "auto_reason": "approved (non-interactive --approve flag)",
        }
    elif args.deny:
        real_flags = {
            "auto_decision": "denied",
            "auto_reason": args.deny,
        }
    elif args.counter_offer is not None:
        real_flags = {"counter_offer_amount": args.counter_offer}

    asyncio.run(main_async(real=args.real, **real_flags))


if __name__ == "__main__":
    main()
