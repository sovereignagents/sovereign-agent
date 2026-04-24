"""Worker backends (v0.2, Module 2 foundation).

## Why this exists

In v0.1.0, when the orchestrator wanted to drive a session through its
ReAct loop, it called `executor.execute()` directly — in the same
process, same Python interpreter, same filesystem view. This is simple
for teaching, but it has the problems the class transcript keeps
surfacing:

  * Tenant isolation is only as strong as Python's import system.
    A misbehaving tool can read any file the process can read.
  * A runaway loop that hogs CPU or RAM takes the orchestrator with it.
  * Scaling out across hosts means distributing Python runtimes, not
    just shipping a container.

The orchestrator should not care HOW a session gets worked on. It
should tell SOMEONE to advance the session, then wait for artifacts
to appear on disk (tickets, handoff files, session_complete). That
"someone" is a worker backend.

## The protocol

    class WorkerBackend(Protocol):
        async def run_session(self, session_id: str, session_dir: Path) -> WorkerOutcome: ...

That's it. The worker is handed a session id and its on-disk directory;
it drives one "step" (planner → executor → maybe handoff) and returns.
Correctness guarantees come from the session directory contract, not
from the worker implementation.

## Built-in backends

  BareWorker         — runs in-process via existing DefaultExecutor.
                       Same behaviour as v0.1.0. Default.
  SubprocessWorker   — spawns `python -m sovereign_agent.orchestrator.worker_entrypoint`
                       in a separate process. OS-level isolation,
                       no Docker daemon required. Portable across
                       Linux/macOS/Windows.
  DockerWorker       — (see docker_worker.py) spawns a container with
                       the session directory bind-mounted read-write.
                       Stronger isolation; requires Docker daemon.

Users pick via `Config.worker_backend`. Scenarios can override
per-invocation. Tests use `BareWorker` by default.

## What a backend MUST do

  1. Advance the session through exactly one "step" — typically one
     planner call followed by one executor call.
  2. Write all state changes through the Session directory APIs. No
     smuggling state via return values, env vars, or stdout.
  3. Return a WorkerOutcome that summarises what happened, so the
     orchestrator can log and re-enqueue as needed.
  4. Honour the `_close` sentinel and timeouts. A backend that doesn't
     exit when asked is a bug.

## What a backend MUST NOT do

  * Hold state across calls. Every call re-reads the session's current
    state from disk.
  * Reach into the orchestrator's memory. The only shared state is the
    session directory.
  * Depend on its own network ingress. The worker reaches out; nothing
    reaches in.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


@dataclass
class WorkerOutcome:
    """Result of one worker step.

    Fields:
      session_id: the session that was advanced.
      terminal: True if the session reached a terminal state during
        this step (completed/failed/escalated) — the orchestrator
        will not re-enqueue.
      advanced: True if the worker changed the session's state or
        produced new artifacts. False means "I looked at the session
        and there was nothing to do" (idle tick).
      summary: one-line human-readable description of the step.
      raw: backend-specific extra payload (timings, container id,
        exit code). Do NOT rely on its shape.
    """

    session_id: str
    terminal: bool
    advanced: bool
    summary: str
    raw: dict = field(default_factory=dict)


@runtime_checkable
class WorkerBackend(Protocol):
    """The interface the orchestrator uses to advance sessions.

    All methods are async. Implementations are free to block internally —
    the orchestrator runs them on its event loop, so a worker that spawns
    a subprocess should await its completion with asyncio-native waits,
    not time.sleep.
    """

    name: str

    async def run_session(
        self,
        session_id: str,
        session_dir: Path,
        *,
        timeout_s: float | None = None,
    ) -> WorkerOutcome: ...

    async def close(self) -> None:
        """Release any resources the backend holds (thread pools,
        subprocess handles, Docker containers). The orchestrator calls
        this during shutdown."""
        ...


# ---------------------------------------------------------------------------
# BareWorker — v0.1.0 behaviour, preserved as the default
# ---------------------------------------------------------------------------


class BareWorker:
    """Runs the session step in-process.

    This is what v0.1.0 did implicitly. We give it a name now so that
    "no isolation" is a choice, not an assumption. Useful for teaching,
    debugging, and tests where a fresh process per step would be too
    slow.

    Use Config.worker_backend='bare' (the default) to get this.
    """

    name = "bare"

    def __init__(self, advance_fn):  # type: ignore[no-untyped-def]
        """advance_fn is an async callable ``(session_id, session_dir) -> WorkerOutcome``.

        The orchestrator builds the callable from its own state-dispatch
        code and hands it to the worker. This lets us decouple "what a
        step does" from "where the step runs".
        """
        self._advance_fn = advance_fn

    async def run_session(
        self,
        session_id: str,
        session_dir: Path,
        *,
        timeout_s: float | None = None,
    ) -> WorkerOutcome:
        coro = self._advance_fn(session_id, session_dir)
        if timeout_s is None:
            return await coro
        try:
            return await asyncio.wait_for(coro, timeout=timeout_s)
        except TimeoutError:
            return WorkerOutcome(
                session_id=session_id,
                terminal=False,
                advanced=False,
                summary=f"bare worker timed out after {timeout_s}s",
                raw={"timeout": True},
            )

    async def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# SubprocessWorker — OS process isolation, no Docker required
# ---------------------------------------------------------------------------


class SubprocessWorker:
    """Runs the session step in a separate Python process via
    `python -m sovereign_agent.orchestrator.worker_entrypoint`.

    The subprocess inherits just enough environment to find the same
    sovereign-agent install and the session's LLM credentials. Session
    state is exchanged via the session directory — the subprocess reads
    and writes files there, and its exit code tells us whether the step
    succeeded.

    v0.2 Module 2 addition: optional `isolation_policy`. When set, the
    subprocess is launched through an IsolationPolicy that wraps it in
    Landlock (Linux) or sandbox-exec (macOS) with a filesystem
    allow-list consisting of:

      * The session directory (read-write)
      * The Python runtime and site-packages (read-only)
      * /etc/resolv.conf and other read-only system paths the runtime needs

    See sovereign_agent._internal.isolation for available policies and
    detect_best_policy() to pick the right one automatically.

    Trade-offs compared to BareWorker:

      + OS-level isolation: a segfault or runaway import doesn't take
        the orchestrator down.
      + With isolation_policy, filesystem isolation is kernel-enforced.
      + Same isolation guarantees as Docker without the daemon.
      - Adds ~100-300ms fork overhead per step.
      - Without an isolation_policy, shares the host filesystem outside
        the session directory.

    Use Config.worker_backend='subprocess' to opt in.
    """

    name = "subprocess"

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        extra_env: dict[str, str] | None = None,
        isolation_policy=None,  # type: ignore[no-untyped-def]
        extra_allowed_paths: list[Path] | None = None,
        allow_network: bool = True,
    ) -> None:
        self.python_executable = python_executable or sys.executable
        self.extra_env = extra_env or {}
        # IsolationPolicy is optional. If None, runs unconfined (same as
        # v0.1.0 behaviour). Scenarios that need confinement should pass
        # sovereign_agent._internal.isolation.detect_best_policy().
        self.isolation_policy = isolation_policy
        # Extra read-only paths the child needs access to. Typically
        # includes sys.prefix (Python runtime) and site-packages. If
        # not provided and isolation is active, we auto-discover them.
        self._extra_allowed_paths = extra_allowed_paths
        self.allow_network = allow_network

    def _default_readonly_paths(self) -> list[Path]:
        """Paths every Python child needs read access to. Covers the
        interpreter, stdlib, and common site-packages locations.

        This is the allow-list that makes the sandbox usable at all —
        without these, `import os` would fail under Landlock.
        """
        import site
        import sysconfig

        paths: set[Path] = set()
        # Python runtime
        paths.add(Path(sys.prefix))
        if hasattr(sys, "base_prefix"):
            paths.add(Path(sys.base_prefix))
        # Stdlib + ext modules + site-packages
        for key in ("stdlib", "purelib", "platlib", "include"):
            try:
                p = sysconfig.get_path(key)
                if p:
                    paths.add(Path(p))
            except KeyError:
                pass
        for sp in site.getsitepackages():
            paths.add(Path(sp))
        if hasattr(site, "getusersitepackages"):
            paths.add(Path(site.getusersitepackages()))
        # Common system paths the runtime reads
        for p in ("/etc/resolv.conf", "/etc/hosts", "/etc/ssl/certs", "/usr/share/ca-certificates"):
            pp = Path(p)
            if pp.exists():
                paths.add(pp)
        # Resolve and deduplicate.
        return sorted({p.resolve() for p in paths if p.exists()})

    async def run_session(
        self,
        session_id: str,
        session_dir: Path,
        *,
        timeout_s: float | None = None,
    ) -> WorkerOutcome:
        env = os.environ.copy()
        env.update(self.extra_env)

        raw_command = [
            self.python_executable,
            "-m",
            "sovereign_agent.orchestrator.worker_entrypoint",
            "--session-id",
            session_id,
            "--session-dir",
            str(session_dir),
        ]

        # Apply isolation if configured. The policy is pure: it returns
        # a wrapped command and any extra env. We honour both.
        if self.isolation_policy is not None:
            allowed = [session_dir.resolve()]
            if self._extra_allowed_paths is not None:
                allowed.extend(p.resolve() for p in self._extra_allowed_paths)
            else:
                allowed.extend(self._default_readonly_paths())
            args, extra_env = self.isolation_policy.wrap_command(
                raw_command,
                allowed_paths=allowed,
                allow_network=self.allow_network,
            )
            env.update(extra_env)
            log.debug(
                "isolation policy %r wrapping command (%d allow paths)",
                self.isolation_policy.name,
                len(allowed),
            )
        else:
            args = raw_command

        log.debug("spawning subprocess worker: %s", args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            return WorkerOutcome(
                session_id=session_id,
                terminal=False,
                advanced=False,
                summary=f"subprocess spawn failed: {exc}",
                raw={"error": str(exc)},
            )

        try:
            if timeout_s is not None:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            else:
                stdout, stderr = await proc.communicate()
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return WorkerOutcome(
                session_id=session_id,
                terminal=False,
                advanced=False,
                summary=f"subprocess worker timed out after {timeout_s}s",
                raw={"timeout": True},
            )

        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        # Convention: the worker entrypoint writes a WorkerOutcome-shaped
        # JSON line as its LAST line of stdout. If it didn't, we fall
        # back to an exit-code-based outcome.
        summary_line = ""
        terminal = False
        advanced = False
        if stdout_text.strip():
            last = stdout_text.strip().splitlines()[-1]
            # We parse defensively — if it isn't JSON, treat as free text.
            import json as _json

            try:
                payload = _json.loads(last)
                if isinstance(payload, dict):
                    terminal = bool(payload.get("terminal", False))
                    advanced = bool(payload.get("advanced", False))
                    summary_line = str(payload.get("summary", ""))
            except _json.JSONDecodeError:
                summary_line = last

        if proc.returncode == 0:
            return WorkerOutcome(
                session_id=session_id,
                terminal=terminal,
                advanced=advanced,
                summary=summary_line or "subprocess exited 0",
                raw={
                    "returncode": proc.returncode,
                    "stdout_tail": stdout_text[-2000:],
                    "stderr_tail": stderr_text[-2000:],
                },
            )
        return WorkerOutcome(
            session_id=session_id,
            terminal=False,
            advanced=False,
            summary=(
                f"subprocess exited {proc.returncode}: "
                f"{(stderr_text or summary_line or '').splitlines()[-1] if stderr_text or summary_line else 'no stderr'}"
            ),
            raw={
                "returncode": proc.returncode,
                "stdout_tail": stdout_text[-2000:],
                "stderr_tail": stderr_text[-2000:],
            },
        )

    async def close(self) -> None:
        return None


__all__ = [
    "BareWorker",
    "SubprocessWorker",
    "WorkerBackend",
    "WorkerOutcome",
]
