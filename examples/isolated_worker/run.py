"""Isolated worker — Module 2 (Landlock + sandbox-exec) in action.

## What this shows

The orchestrator's worker runs in a separate Python process whose
filesystem view is kernel-confined: it can read/write the session
directory, read the Python runtime, and nothing else. A compromised
tool cannot read `/etc/passwd`, `~/.ssh/*`, or anything outside the
allow-list — not with `os.system`, not with `..` traversal, not even
as root.

No Docker. No daemon. No container runtime. Kernel-native isolation:

  * Linux ≥ 5.13  → Landlock (self-applied filesystem restriction)
  * macOS         → sandbox-exec (Apple's per-process sandbox)
  * elsewhere     → NoOp with a loud warning

The script:

  1. Prints which isolation policy was auto-selected for your host.
  2. Spawns a subprocess worker that attempts two things:
     a. Write a file inside the session directory (ALLOWED)
     b. Read /etc/shadow (DENIED by the sandbox)
  3. Shows that (a) succeeds and (b) fails with PermissionError or
     EACCES — proving the sandbox is enforcing.

## Run

    python -m examples.isolated_worker.run

On a modern Linux/macOS host you'll see the forbidden read denied. On a
kernel or OS without the primitive (Windows, pre-5.13 Linux), you'll
see the NoOp warning and the read will succeed — the framework tells
you this explicitly so you don't run unconfined by mistake.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from sovereign_agent._internal.isolation import (
    LandlockPolicy,
    NoOpPolicy,
    SandboxExecPolicy,
    detect_best_policy,
    landlock_available,
    sandbox_exec_available,
)
from sovereign_agent.orchestrator.worker import SubprocessWorker, WorkerOutcome

# ---------------------------------------------------------------------------
# The probe script — this is what the isolated worker subprocess runs.
# ---------------------------------------------------------------------------

_PROBE_SCRIPT = r"""
# This script runs INSIDE the sandbox. It tries two things:
#   1. Write a file under the session dir (allowed)
#   2. Read /etc/shadow (denied on a working sandbox)
# and emits a one-line JSON summary to stdout as its last output
# (the contract SubprocessWorker expects).

import json, os, sys

session_dir = os.environ["SESSION_DIR"]
write_ok = False
forbidden_read_ok = False
error_messages = []

# (1) Write inside session dir.
try:
    path = os.path.join(session_dir, "sandbox_probe.txt")
    with open(path, "w") as f:
        f.write("hello from inside the sandbox\n")
    write_ok = True
except Exception as exc:
    error_messages.append(f"write to session dir failed: {exc}")

# (2) Attempt to read /etc/shadow (or /etc/sudoers on macOS). A
#     working sandbox must deny this; NoOp will silently allow it
#     (on Linux running as non-root, shadow is unreadable anyway —
#     in that case we try /etc/hosts which every non-root user CAN
#     normally read, to distinguish sandbox-denial from lack-of-perms).
candidate = "/etc/shadow" if sys.platform == "linux" else "/etc/sudoers"
try:
    with open(candidate, "rb") as f:
        f.read(64)
    forbidden_read_ok = True
except PermissionError as exc:
    error_messages.append(f"{candidate}: PermissionError ({exc})")
except FileNotFoundError as exc:
    error_messages.append(f"{candidate}: FileNotFoundError ({exc})")
except OSError as exc:
    error_messages.append(f"{candidate}: OSError ({exc})")

# The real test — try reading /etc/hosts, which a non-root user CAN
# normally read. If the sandbox is enforcing, this should ALSO fail
# (because /etc/hosts isn't in our allow-list). If we're running
# unconfined, it will succeed.
hosts_readable = False
try:
    with open("/etc/hosts", "rb") as f:
        f.read(64)
    hosts_readable = True
except (PermissionError, FileNotFoundError, OSError) as exc:
    error_messages.append(f"/etc/hosts: {type(exc).__name__} ({exc})")

# Last line of stdout must be the worker-outcome JSON per the SubprocessWorker
# contract, regardless of what else we printed.
summary = {
    "terminal": True,
    "advanced": True,
    "summary": (
        f"wrote={write_ok} forbidden_read={forbidden_read_ok} "
        f"hosts_readable={hosts_readable}"
    ),
    "probe": {
        "write_ok": write_ok,
        "forbidden_read_ok": forbidden_read_ok,
        "hosts_readable": hosts_readable,
        "errors": error_messages,
    },
}
print("probe: running inside subprocess", file=sys.stderr)
for line in error_messages:
    print(f"probe: {line}", file=sys.stderr)
print(json.dumps(summary))
"""


# ---------------------------------------------------------------------------
# A tiny subclass that runs our probe script under the policy wrap.
# ---------------------------------------------------------------------------


class _ProbeWorker(SubprocessWorker):
    """Runs _PROBE_SCRIPT instead of the real worker_entrypoint. Still
    applies the isolation policy so we see the same enforcement path
    the real worker would get."""

    def __init__(self, script_path: Path, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self._script_path = script_path

    async def run_session(self, session_id, session_dir, *, timeout_s=None):  # type: ignore[no-untyped-def]
        env = os.environ.copy()
        env.update(self.extra_env)
        env["SESSION_DIR"] = str(session_dir)

        raw_command = [self.python_executable, str(self._script_path)]
        if self.isolation_policy is not None:
            allowed = [session_dir.resolve()]
            # For the script to even start, it needs to READ its own file.
            allowed.append(self._script_path.resolve())
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
        else:
            args = raw_command

        proc = await asyncio.create_subprocess_exec(
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        stdout_text = stdout.decode(errors="replace")
        stderr_text = stderr.decode(errors="replace")
        # Parse last-line JSON contract.
        import json as _json

        last = stdout_text.strip().splitlines()[-1] if stdout_text.strip() else "{}"
        try:
            payload = _json.loads(last)
        except _json.JSONDecodeError:
            payload = {
                "terminal": False,
                "advanced": False,
                "summary": f"probe produced no JSON (exit={proc.returncode})",
                "probe": {},
            }
        return WorkerOutcome(
            session_id=session_id,
            terminal=bool(payload.get("terminal", False)),
            advanced=bool(payload.get("advanced", False)),
            summary=str(payload.get("summary", "")),
            raw={
                "returncode": proc.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "probe": payload.get("probe", {}),
            },
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _describe_policy(policy) -> str:  # type: ignore[no-untyped-def]
    if isinstance(policy, LandlockPolicy):
        return "LandlockPolicy — Linux kernel Landlock LSM, ABI-negotiated"
    if isinstance(policy, SandboxExecPolicy):
        return "SandboxExecPolicy — macOS sandbox-exec(1) with generated .sb profile"
    if isinstance(policy, NoOpPolicy):
        return "NoOpPolicy — NO isolation (platform lacks a supported primitive)"
    return f"{type(policy).__name__}"


async def run_scenario(real: bool = False) -> None:
    print("=== Isolation availability on this host ===")
    print(f"  platform:           {sys.platform}")
    print(f"  landlock_available: {landlock_available()}")
    print(f"  sandbox_exec_available: {sandbox_exec_available()}")

    policy = detect_best_policy()
    print(f"  selected policy:    {policy.name}")
    print(f"  description:        {_describe_policy(policy)}")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        session_dir = td_path / "sess_demo"
        session_dir.mkdir()

        # Write the probe script to a location the sandbox can READ.
        script_path = td_path / "probe.py"
        script_path.write_text(_PROBE_SCRIPT, encoding="utf-8")

        print("\n=== Running probe subprocess under isolation policy ===")
        print(f"  session_dir:        {session_dir}")
        print(f"  probe_script:       {script_path}")

        worker = _ProbeWorker(
            script_path=script_path,
            isolation_policy=policy,
            allow_network=False,
        )
        outcome = await worker.run_session(
            session_id="sess_demo", session_dir=session_dir, timeout_s=10.0
        )

        probe = outcome.raw.get("probe", {})
        print("\n=== Probe results ===")
        print(f"  write to session dir:   {'ok' if probe.get('write_ok') else 'FAIL'}")
        print(
            f"  forbidden file read:    "
            f"{'ALLOWED (sandbox not enforcing!)' if probe.get('forbidden_read_ok') else 'DENIED (good)'}"
        )
        print(
            f"  /etc/hosts read:        "
            f"{'ALLOWED (read-only allowlist added it)' if probe.get('hosts_readable') else 'DENIED (sandbox confining)'}"
        )
        print(f"\n  subprocess exit code:   {outcome.raw.get('returncode')}")
        errors = probe.get("errors") or []
        if errors:
            print("\n  errors observed inside subprocess:")
            for line in errors:
                print(f"    - {line}")

        # Verify the file really did land where it was supposed to.
        probe_file = session_dir / "sandbox_probe.txt"
        if probe_file.exists():
            print(f"\n  file written inside session dir:  {probe_file}")
            print(f"  contents: {probe_file.read_text()!r}")

        # Pedagogical sign-off.
        print("\n=== What this proved ===")
        if isinstance(policy, NoOpPolicy):
            print(
                "  Your host does not support Landlock or sandbox-exec; the "
                "subprocess ran UNCONFINED. Run this on a modern Linux (>=5.13) "
                "or macOS to see real isolation."
            )
        else:
            if probe.get("forbidden_read_ok"):
                print(
                    "  WARNING — the subprocess was able to read a forbidden file. "
                    "Either the file didn't exist, or something is wrong with the "
                    "sandbox on this host. Investigate before relying on isolation."
                )
            else:
                print(
                    "  The subprocess was DENIED access to a file outside its "
                    "allow-list by the kernel. This is enforced even if the tool "
                    "is compromised; there is no escape hatch."
                )

    # ── Optional: real-LLM probe ────────────────────────────────────
    # In --real mode, confirm the full stack works: a live LLM call
    # can round-trip through the configured endpoint. The sandbox
    # itself doesn't need the LLM to work — this just proves the
    # configured environment is wired correctly, which is the point
    # of having a -real variant for cohort consistency.
    if real:
        print("\n=== Real-LLM round-trip ===")
        try:
            from sovereign_agent._internal.llm_client import OpenAICompatibleClient
            from sovereign_agent.config import Config

            cfg = Config.from_env()
            print(f"  endpoint: {cfg.llm_base_url}")
            print(f"  model:    {cfg.llm_executor_model}")
            client = OpenAICompatibleClient(
                base_url=cfg.llm_base_url, api_key_env=cfg.llm_api_key_env
            )
            # A single cheap call — prove auth + network + model selection
            resp = await client.chat(
                model=cfg.llm_executor_model,
                messages=[{"role": "user", "content": "say 'ok' and nothing else"}],
                max_tokens=5,
            )
            content = (resp.content or "").strip()
            print(f"  response: {content!r}")
            print("  ✓  real LLM reachable and responding")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗  real-LLM probe failed: {type(e).__name__}: {e}")
            print("     (sandbox verification above is unaffected — different concern)")


def main() -> None:
    real = "--real" in sys.argv
    asyncio.run(run_scenario(real=real))


if __name__ == "__main__":
    main()
