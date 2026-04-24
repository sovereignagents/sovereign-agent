"""The `sovereign-agent` command-line tool.

See docs/architecture.md §2.19. Implemented with typer so `--help` is nice
out of the box.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import shutil
import sys
from pathlib import Path

import typer

from sovereign_agent.config import Config
from sovereign_agent.observability.report import generate_session_report
from sovereign_agent.orchestrator import Orchestrator, run_task
from sovereign_agent.session.directory import (
    DEFAULT_SESSIONS_DIR,
    archive_session,
    list_sessions,
    load_session,
)

app = typer.Typer(
    name="sovereign-agent",
    help="A framework for building always-on AI agents that you actually own.",
    no_args_is_help=True,
    add_completion=False,
)
sessions_app = typer.Typer(name="sessions", help="Session management subcommands.")
app.add_typer(sessions_app, name="sessions")


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------
@app.command()
def version() -> None:
    """Print the installed sovereign-agent version."""
    try:
        v = importlib.metadata.version("sovereign-agent")
    except importlib.metadata.PackageNotFoundError:
        v = "0.1.0 (source checkout)"
    typer.echo(f"sovereign-agent {v}")


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
@app.command()
def doctor(
    skip_llm: bool = typer.Option(
        False, "--skip-llm", help="Skip the real LLM call check (faster, offline)."
    ),
) -> None:
    """Preflight checks. Exits 0 if everything is OK, non-zero otherwise."""
    issues: list[str] = []

    # Python version
    py = sys.version_info
    if (py.major, py.minor) < (3, 12):
        issues.append(
            f"Python {py.major}.{py.minor} is too old. sovereign-agent requires Python 3.12+."
        )
    else:
        _ok(f"Python {py.major}.{py.minor}.{py.micro}")

    # Config loads
    try:
        cfg = Config.from_env()
        _ok(f"Config loaded (sessions_dir={cfg.sessions_dir})")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"Config failed to load: {exc}")
        cfg = Config()

    # API key
    if os.environ.get(cfg.llm_api_key_env):
        _ok(f"LLM API key present ({cfg.llm_api_key_env})")
    else:
        issues.append(f"LLM API key not set. Export {cfg.llm_api_key_env} and retry.")

    # Disk space in sessions_dir parent.
    try:
        target = cfg.sessions_dir.parent if cfg.sessions_dir.parent.exists() else Path.cwd()
        usage = shutil.disk_usage(target)
        free_gb = usage.free / (1024**3)
        if free_gb < 1.0:
            issues.append(
                f"Disk space low: {free_gb:.2f} GB free in {target}. Recommended >= 1 GB."
            )
        else:
            _ok(f"Disk space OK ({free_gb:.1f} GB free in {target})")
    except OSError as exc:
        issues.append(f"Could not check disk space: {exc}")

    # Mount allowlist existence (auto-generated on first load).
    try:
        from sovereign_agent.orchestrator.mounts import load_allowlist

        al = load_allowlist(cfg.mount_allowlist_path)
        _ok(
            f"Mount allowlist present ({cfg.mount_allowlist_path}, "
            f"{len(al.allowed_roots)} allowed root(s))"
        )
    except Exception as exc:  # noqa: BLE001
        issues.append(f"Mount allowlist problem: {exc}")

    # Config.validate() self-check
    for msg in cfg.validate():
        issues.append(msg)

    # Optional: make a real LLM call.
    if not skip_llm and os.environ.get(cfg.llm_api_key_env):
        try:
            from sovereign_agent._internal.llm_client import (
                ChatMessage,
                OpenAICompatibleClient,
            )

            client = OpenAICompatibleClient(
                base_url=cfg.llm_base_url,
                api_key_env=cfg.llm_api_key_env,
            )

            async def _probe() -> str:
                resp = await client.chat(
                    model=cfg.llm_executor_model,
                    messages=[ChatMessage(role="user", content="Reply with just the word OK.")],
                    temperature=0.0,
                    max_tokens=10,
                )
                return (resp.content or "").strip()

            reply = asyncio.run(_probe())
            if reply:
                _ok(f"LLM call succeeded (model={cfg.llm_executor_model}, reply={reply!r})")
            else:
                issues.append(f"LLM call returned empty content (model={cfg.llm_executor_model})")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"LLM call failed: {exc}")

    # Summary
    typer.echo("")
    if issues:
        typer.secho(f"Found {len(issues)} issue(s):", fg=typer.colors.RED, bold=True)
        for msg in issues:
            typer.echo(f"  ✗ {msg}")
        raise typer.Exit(code=1)
    typer.secho("All checks passed.", fg=typer.colors.GREEN, bold=True)


def _ok(message: str) -> None:
    typer.secho(f"  ✓ {message}", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
@app.command()
def run(
    task: str = typer.Argument(..., help="The task description for the agent."),
    scenario: str = typer.Option("default", help="Scenario label for the session."),
    user_id: str | None = typer.Option(None, help="User id to attach to the session."),
) -> None:
    """Run one task end-to-end and print the result."""
    cfg = Config.from_env()
    result = run_task(task, config=cfg, scenario=scenario, user_id=user_id)
    typer.echo(f"Session: {result.session_id}")
    typer.echo(f"Directory: {result.session_dir}")
    typer.echo(f"Success: {result.success}")
    typer.echo("")
    typer.echo(result.summary)
    if not result.success:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------
@app.command()
def serve() -> None:
    """Start a long-running orchestrator."""
    cfg = Config.from_env()
    orch = Orchestrator(cfg)
    typer.echo(f"starting orchestrator (sessions_dir={cfg.sessions_dir}). Ctrl+C to stop.")
    try:
        asyncio.run(orch.run())
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
@app.command()
def report(
    session_id: str = typer.Argument(...),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write to file instead of stdout."
    ),
) -> None:
    """Generate a markdown report for one session."""
    cfg = Config.from_env()
    try:
        session = load_session(session_id, sessions_dir=cfg.sessions_dir)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    text = generate_session_report(session)
    if output is None:
        typer.echo(text)
    else:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {output}")


# ---------------------------------------------------------------------------
# sessions list / show / archive
# ---------------------------------------------------------------------------
@sessions_app.command("list")
def sessions_list(
    state: str | None = typer.Option(None, help="Filter by state."),
) -> None:
    """List sessions, newest first."""
    cfg = Config.from_env()
    all_sessions = list_sessions(state_filter=state, sessions_dir=cfg.sessions_dir)  # type: ignore[arg-type]
    if not all_sessions:
        typer.echo("no sessions found")
        return
    for s in all_sessions:
        typer.echo(f"{s.session_id}  {s.state.state:30s}  updated {s.state.updated_at.isoformat()}")


@sessions_app.command("show")
def sessions_show(session_id: str) -> None:
    """Pretty-print a single session's state."""
    cfg = Config.from_env()
    try:
        session = load_session(session_id, sessions_dir=cfg.sessions_dir)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    import json

    typer.echo(json.dumps(session.state.to_dict(), indent=2, default=str))


@sessions_app.command("archive")
def sessions_archive(session_id: str) -> None:
    """Move a terminal session into sessions/archive/."""
    cfg = Config.from_env()
    try:
        session = load_session(session_id, sessions_dir=cfg.sessions_dir)
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    try:
        dest = archive_session(session, archive_dir=cfg.sessions_dir / "archive")
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"archive failed: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(f"archived to {dest}")


@sessions_app.command("resume")
def sessions_resume(
    parent_id: str = typer.Argument(..., help="Session ID to resume from (the parent)."),
    task: str = typer.Option(
        "",
        "--task",
        "-t",
        help="Task description for the new session. Defaults to empty.",
    ),
    scenario: str | None = typer.Option(
        None,
        "--scenario",
        help="Override the scenario name. Defaults to the parent's scenario.",
    ),
    user_id: str | None = typer.Option(
        None, "--user", help="User ID for the new session (defaults to parent's)."
    ),
    allow_unfinished_parent: bool = typer.Option(
        False,
        "--allow-unfinished-parent",
        help="Permit resuming from a parent that is not in a terminal state.",
    ),
    sessions_dir: Path | None = typer.Option(
        None,
        "--sessions-dir",
        help="Root sessions directory (defaults to config / ./sessions).",
    ),
) -> None:
    """Create a new session that resumes from an existing one.

    The new session gets a fresh ID and records `resumed_from=<parent_id>`
    in its session.json. Parent session is not modified. Parent trace,
    tickets, and result are summarised and prepended to the new session's
    SESSION.md so the planner reads the context on its first turn.
    """
    from sovereign_agent.session.resume import resume_session as _resume

    cfg = Config.from_env()
    resolved_sessions_dir = sessions_dir or cfg.sessions_dir

    try:
        child = _resume(
            parent_id=parent_id,
            task=task,
            scenario=scenario,
            sessions_dir=resolved_sessions_dir,
            user_id=user_id,
            allow_unfinished_parent=allow_unfinished_parent,
        )
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.echo(f"new session: {child.session_id}")
    typer.echo(f"  resumed_from: {parent_id}")
    typer.echo(f"  directory:    {child.directory}")
    typer.echo(f"  SESSION.md:   {child.session_md_path}")
    typer.echo(
        "\nThe new session is in state 'planning'. Run the orchestrator "
        "against this session_id to continue."
    )


def main() -> None:
    """Console-script entry point."""
    app()


# ---------------------------------------------------------------------------
# approvals — v0.2 Module 5 (HITL)
# ---------------------------------------------------------------------------
approvals_app = typer.Typer(
    name="approvals", help="Inspect and respond to human-in-the-loop approval requests."
)
app.add_typer(approvals_app, name="approvals")


@approvals_app.command("list")
def approvals_list(
    session_id: str = typer.Argument(..., help="Session ID (e.g. sess_abcd1234...)."),
    sessions_dir: Path | None = typer.Option(
        None, "--sessions-dir", help="Root sessions directory (defaults to ./sessions)."
    ),
) -> None:
    """List pending approval requests for a session."""
    from sovereign_agent.ipc.approval import list_pending_approvals

    try:
        session = load_session(session_id, sessions_dir=sessions_dir)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    pending = list_pending_approvals(session)
    if not pending:
        typer.echo(f"no pending approvals for session {session_id}")
        return

    for req in pending:
        typer.echo(
            f"{req.request_id}  subgoal={req.subgoal_id}  "
            f"tool={req.tool_name}  reason={req.reason!r}"
        )
        typer.echo(f"    args: {req.tool_arguments}")
        typer.echo(f"    proposed_output: {req.proposed_output}")


@approvals_app.command("grant")
def approvals_grant(
    session_id: str = typer.Argument(..., help="Session ID."),
    request_id: str = typer.Argument(..., help="Request ID (e.g. appr_abc12345_c1)."),
    reason: str = typer.Option("", "--reason", "-r", help="Approver's reason/notes."),
    approver: str = typer.Option(
        os.environ.get("USER", "unknown"), "--approver", help="Approver identifier."
    ),
    sessions_dir: Path | None = typer.Option(None, "--sessions-dir"),
) -> None:
    """Grant a pending approval."""
    _record_decision(
        session_id=session_id,
        request_id=request_id,
        decision="granted",
        approver=approver,
        reason=reason,
        sessions_dir=sessions_dir,
    )


@approvals_app.command("deny")
def approvals_deny(
    session_id: str = typer.Argument(..., help="Session ID."),
    request_id: str = typer.Argument(..., help="Request ID."),
    reason: str = typer.Option(
        "", "--reason", "-r", help="Reason (shown to the LLM to adapt its plan)."
    ),
    approver: str = typer.Option(
        os.environ.get("USER", "unknown"), "--approver", help="Approver identifier."
    ),
    sessions_dir: Path | None = typer.Option(None, "--sessions-dir"),
) -> None:
    """Deny a pending approval."""
    _record_decision(
        session_id=session_id,
        request_id=request_id,
        decision="denied",
        approver=approver,
        reason=reason,
        sessions_dir=sessions_dir,
    )


def _record_decision(
    *,
    session_id: str,
    request_id: str,
    decision: str,
    approver: str,
    reason: str,
    sessions_dir: Path | None,
) -> None:
    """Shared helper for grant/deny subcommands."""
    from sovereign_agent.ipc.approval import ApprovalResponse, record_decision
    from sovereign_agent.session.state import now_utc

    try:
        session = load_session(session_id, sessions_dir=sessions_dir)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    response = ApprovalResponse(
        request_id=request_id,
        decision=decision,  # type: ignore[arg-type]
        approver=approver,
        decided_at=now_utc().isoformat(),
        reason=reason,
    )
    try:
        target = record_decision(session, response)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"{decision}: {request_id}")
    typer.echo(f"  written to: {target}")
    typer.echo(
        f"  the session can now be resumed via resume_from_approval(..., request_id={request_id!r})"
    )


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = ["app", "main"]

# Make DEFAULT_SESSIONS_DIR importable for symmetry; not otherwise used here.
_ = DEFAULT_SESSIONS_DIR
