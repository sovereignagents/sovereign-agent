"""Session resume (v0.2, Module 3).

## What this is

`resume_session(parent_id, task, ...)` creates a NEW session that holds a
pointer to an earlier ("parent") session. The child can read the parent's
memory, trace, tickets, and workspace — but cannot modify them. This lets
agents pick up where a prior session left off (after a crash, a handoff
delay, or a human deciding to extend the task) without violating the
forward-only state rule.

Students asked for this directly in class — "how do I continue a session
from yesterday?" — and we gave a hand-wavy verbal answer. This module is
the concrete form.

## What this is NOT

This is not the same as `resume_from_approval` in the executor (Module 5).
That function re-enters a SPECIFIC paused session after a human decision.
`resume_session` here makes a FRESH session linked to an older one.

## Contract

  * Creates a new session directory with a new session id.
  * Records `resumed_from=<parent_id>` in session.json.
  * The parent is not touched. Parent state, files, trace — all unchanged.
  * The new session's SESSION.md gets an auto-generated "Parent context"
    header summarising the parent's trace, memory, and terminal state, so
    the planner sees the context as soon as it reads SESSION.md.

## Policy

  * If the parent is still running (state='planning' | 'executing' |
    'handed_off_*'), we refuse to resume. Waiting for a session to finish
    before resuming from it avoids reading an inconsistent mid-write state.
    Override with `allow_unfinished_parent=True` if you're sure.
  * If the parent doesn't exist, raise SessionNotFoundError (the loader
    already does this).
  * We read a capped-length summary of the parent trace, not the whole
    thing. Long-running sessions can have megabytes of trace.
"""

from __future__ import annotations

import json
from pathlib import Path

from sovereign_agent.errors import ValidationError
from sovereign_agent.session.directory import (
    DEFAULT_SESSIONS_DIR,
    Session,
    create_session,
    load_session,
)

# Cap the parent-trace summary we inline into SESSION.md. Very long traces
# can blow out planner context windows. If users want the full trace they
# can read it directly from the parent's directory.
DEFAULT_TRACE_SUMMARY_LINES = 80


def resume_session(
    parent_id: str,
    task: str = "",
    *,
    scenario: str | None = None,
    sessions_dir: Path | None = None,
    user_id: str | None = None,
    config_overrides: dict | None = None,
    session_id: str | None = None,
    allow_unfinished_parent: bool = False,
    trace_summary_lines: int = DEFAULT_TRACE_SUMMARY_LINES,
) -> Session:
    """Create a new session that resumes from `parent_id`.

    Args:
      parent_id: session id of the parent. Must exist under `sessions_dir`.
      task: the new task description. Typically narrower than the parent's
        ("continue the booking: now handle the deposit negotiation").
      scenario: scenario name. Defaults to the parent's scenario.
      sessions_dir: root directory. Defaults to ./sessions.
      user_id, config_overrides, session_id: see create_session.
      allow_unfinished_parent: if True, permit resuming from a session
        that hasn't reached a terminal state. Default False.
      trace_summary_lines: number of trace lines to inline into the
        child's SESSION.md as parent context.

    Returns:
      the new Session handle.

    Raises:
      SessionNotFoundError: parent doesn't exist.
      ValidationError: parent is unfinished and allow_unfinished_parent=False.
    """
    sessions_root = sessions_dir or DEFAULT_SESSIONS_DIR

    # Fetch parent (raises if missing).
    parent = load_session(parent_id, sessions_dir=sessions_root)

    if not parent.state.is_terminal() and not allow_unfinished_parent:
        raise ValidationError(
            code="SA_VAL_PARENT_UNFINISHED",
            message=(
                f"cannot resume from session {parent_id!r}: state="
                f"{parent.state.state!r} is not terminal. Pass "
                f"allow_unfinished_parent=True to override."
            ),
            context={
                "parent_id": parent_id,
                "parent_state": parent.state.state,
            },
        )

    resolved_scenario = scenario or parent.state.scenario

    child = create_session(
        scenario=resolved_scenario,
        task=task,
        user_id=user_id or parent.state.user_id,
        config_overrides=config_overrides,
        sessions_dir=sessions_root,
        session_id=session_id,
        resumed_from=parent_id,
    )

    # Inline a context summary into SESSION.md. The planner reads SESSION.md
    # at the start of every run, so this is the natural place to surface
    # "here's what happened last time".
    summary = build_parent_context_summary(
        parent,
        trace_summary_lines=trace_summary_lines,
    )
    _prepend_to_session_md(child, summary)

    return child


def build_parent_context_summary(
    parent: Session,
    *,
    trace_summary_lines: int = DEFAULT_TRACE_SUMMARY_LINES,
) -> str:
    """Construct a markdown block summarising the parent session.

    Intended to be prepended to a child's SESSION.md. Includes:
      * parent id, scenario, terminal state
      * a capped tail of the parent's trace (most recent events)
      * a list of tickets from the parent
      * the parent's final result, if any

    Separated from `resume_session` so tests and custom flows can assemble
    their own context blocks without going through full resume.
    """
    state = parent.state
    lines = [
        "## Parent session context (auto-generated)",
        "",
        f"This session resumes from `{state.session_id}`.",
        f"- Scenario: `{state.scenario}`",
        f"- Parent state: `{state.state}`",
        f"- Parent created: {state.created_at.isoformat()}",
        f"- Parent last updated: {state.updated_at.isoformat()}",
    ]
    if state.result:
        # Pretty-print the result dict so the planner can read it
        # naturally.
        lines.append("")
        lines.append("### Parent result")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(state.result, indent=2, default=str))
        lines.append("```")

    # Trace tail.
    trace_path = parent.trace_path
    if trace_path.exists():
        try:
            with open(trace_path, encoding="utf-8") as f:
                trace_lines = f.readlines()
        except OSError:
            trace_lines = []
        if trace_lines:
            tail = trace_lines[-trace_summary_lines:]
            lines.append("")
            lines.append(f"### Parent trace tail (last {len(tail)} of {len(trace_lines)} events)")
            lines.append("")
            lines.append("```jsonl")
            # Strip trailing newlines for cleaner markdown rendering;
            # each line is one trace event.
            lines.extend(line.rstrip("\n") for line in tail)
            lines.append("```")

    # Ticket list.
    tickets_dir = parent.tickets_dir
    if tickets_dir.exists():
        try:
            ticket_dirs = sorted(p.name for p in tickets_dir.iterdir() if p.is_dir())
        except OSError:
            ticket_dirs = []
        if ticket_dirs:
            lines.append("")
            lines.append(f"### Parent tickets ({len(ticket_dirs)})")
            lines.append("")
            for name in ticket_dirs:
                lines.append(f"- `{name}`")

    lines.append("")
    lines.append(
        "> The above is read-only context from the parent. This session "
        "is a fresh execution with its own trace, tickets, and memory. "
        "The planner MAY use parent context to guide its plan but MUST "
        "NOT assume the parent's side effects are still valid."
    )
    lines.append("")
    return "\n".join(lines)


def _prepend_to_session_md(session: Session, block: str) -> None:
    """Prepend `block` to the session's SESSION.md. Preserves the template
    that create_session wrote.
    """
    md_path = session.session_md_path
    try:
        existing = md_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""
    combined = block + "\n---\n\n" + existing
    # Straight write — SESSION.md is only read, never concurrently written.
    md_path.write_text(combined, encoding="utf-8")


def find_ancestor_chain(session: Session) -> list[str]:
    """Walk the resumed_from pointers up the chain.

    Returns session_ids oldest-first (deepest ancestor, ..., this session's
    immediate parent). Does NOT include `session.session_id` itself.

    Used for:
      * Cycle detection (if this returns something unexpectedly long, you
        have a malformed parent pointer).
      * Reasoning over the full history of a thread of sessions.

    Stops silently if a parent in the chain doesn't exist on disk — the
    chain is whatever we can still reach.
    """
    chain: list[str] = []
    seen: set[str] = {session.session_id}
    current: Session | None = session.parent_session()
    while current is not None:
        if current.session_id in seen:
            # Cycle — shouldn't happen with sane construction, but be
            # defensive. Stop here.
            break
        chain.append(current.session_id)
        seen.add(current.session_id)
        current = current.parent_session()
    # Reverse so oldest ancestor is first.
    chain.reverse()
    return chain


__all__ = [
    "DEFAULT_TRACE_SUMMARY_LINES",
    "build_parent_context_summary",
    "find_ancestor_chain",
    "resume_session",
]
