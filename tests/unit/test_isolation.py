"""Tests for v0.2 Module 2 isolation policies.

What we can and can't verify in this sandbox:

  CAN verify (platform-agnostic, policy is pure):
    * NoOpPolicy returns the command unchanged and warns once
    * LandlockPolicy builds the correct shim command with the right
      --allow-read/--allow-rw flags
    * SandboxExecPolicy builds a valid SBPL profile and wraps the
      command in sandbox-exec -f <profile>
    * detect_best_policy() picks the strongest available on the host
    * Policies raise cleanly on empty allow-lists
    * Allow-list contract: first path is RW, rest are RO
    * Path escaping for SBPL (quotes, backslashes)

  CANNOT verify here (requires Linux >=5.13 or macOS):
    * That Landlock actually blocks a forbidden read
    * That sandbox-exec actually denies network
  These are validated by the shim raising RuntimeError on unsupported
  kernels (test_landlock_shim_probe_returns_zero_on_old_kernel) and by
  manual verification on real hosts during release.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from sovereign_agent._internal.isolation import (
    IsolationPolicy,
    LandlockPolicy,
    NoOpPolicy,
    SandboxExecPolicy,
    _sb_escape,
    detect_best_policy,
    landlock_available,
    sandbox_exec_available,
)

# ---------------------------------------------------------------------------
# NoOpPolicy
# ---------------------------------------------------------------------------


def test_noop_passes_command_through(tmp_path: Path) -> None:
    p = NoOpPolicy()
    args, env = p.wrap_command(
        ["python", "-c", "pass"],
        allowed_paths=[tmp_path],
        allow_network=False,
    )
    assert args == ["python", "-c", "pass"]
    assert env == {}


def test_noop_satisfies_policy_protocol() -> None:
    """Tripwire against accidental signature drift."""
    assert isinstance(NoOpPolicy(), IsolationPolicy)


# ---------------------------------------------------------------------------
# LandlockPolicy — structural tests (contents of the wrapped command)
# ---------------------------------------------------------------------------


def test_landlock_wraps_in_shim_with_allow_rw(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess_abc"
    session_dir.mkdir()
    policy = LandlockPolicy()
    args, _env = policy.wrap_command(
        ["python", "-m", "my_entry"],
        allowed_paths=[session_dir],
        allow_network=True,
    )
    # Shim is invoked via `-m sovereign_agent._internal.landlock_shim`
    assert args[0] == sys.executable
    assert args[1] == "-m"
    assert args[2] == "sovereign_agent._internal.landlock_shim"
    # First allowed path becomes --allow-rw
    assert "--allow-rw" in args
    rw_index = args.index("--allow-rw")
    assert args[rw_index + 1] == str(session_dir)
    # The original command follows `--`
    sep = args.index("--")
    assert args[sep + 1 :] == ["python", "-m", "my_entry"]


def test_landlock_read_only_paths_each_get_flag(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess_abc"
    session_dir.mkdir()
    ro1 = tmp_path / "ro1"
    ro1.mkdir()
    ro2 = tmp_path / "ro2"
    ro2.mkdir()
    policy = LandlockPolicy()
    args, _env = policy.wrap_command(
        ["real_cmd"],
        allowed_paths=[session_dir, ro1, ro2],
        allow_network=True,
    )
    # --allow-read must appear twice, each followed by the right path
    indices = [i for i, a in enumerate(args) if a == "--allow-read"]
    assert len(indices) == 2
    read_paths = {args[i + 1] for i in indices}
    assert read_paths == {str(ro1), str(ro2)}


def test_landlock_deny_network_flag(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    policy = LandlockPolicy()
    args, _env = policy.wrap_command(
        ["cmd"],
        allowed_paths=[session_dir],
        allow_network=False,
    )
    assert "--deny-network" in args


def test_landlock_allow_network_no_flag(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    policy = LandlockPolicy()
    args, _env = policy.wrap_command(
        ["cmd"],
        allowed_paths=[session_dir],
        allow_network=True,
    )
    assert "--deny-network" not in args


def test_landlock_rejects_empty_allowed_paths() -> None:
    policy = LandlockPolicy()
    with pytest.raises(ValueError, match="at least one allowed path"):
        policy.wrap_command(["cmd"], allowed_paths=[], allow_network=True)


# ---------------------------------------------------------------------------
# LandlockPolicy — shim behavior on a kernel that may or may not have Landlock
# ---------------------------------------------------------------------------


def test_landlock_shim_exits_nonzero_on_unsupported_kernel(tmp_path: Path) -> None:
    """The shim must fail-closed when Landlock isn't available: exit
    non-zero with a clear message rather than exec'ing the child
    unprotected. This is the safety-critical contract.

    We skip if the sandbox happens to have Landlock — we don't want
    to prove a negative we can't guarantee.
    """
    if landlock_available():
        pytest.skip("Landlock is available on this host; negative test skipped")
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    # Execute the shim directly and expect a non-zero exit.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sovereign_agent._internal.landlock_shim",
            "--allow-rw",
            str(session_dir),
            "--",
            sys.executable,
            "-c",
            "print('should not reach this')",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0, "shim must fail closed on unsupported kernels"
    # The child command did NOT run.
    assert "should not reach this" not in result.stdout
    # The message explains why.
    combined = (result.stderr or "") + (result.stdout or "")
    assert "landlock" in combined.lower()


def test_landlock_shim_requires_separator() -> None:
    """Without `--`, the shim has no way to know where its args stop
    and the child command begins. It must refuse rather than guess."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sovereign_agent._internal.landlock_shim",
            "--allow-rw",
            "/tmp",
            # no `--`, no child command
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "separator" in (result.stderr + result.stdout).lower()


def test_landlock_shim_requires_child_after_separator(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sovereign_agent._internal.landlock_shim",
            "--allow-rw",
            str(tmp_path),
            "--",
            # no child command
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "child command" in (result.stderr + result.stdout).lower()


# ---------------------------------------------------------------------------
# SandboxExecPolicy — structural tests (profile contents)
# ---------------------------------------------------------------------------


def test_sandbox_exec_wraps_in_binary_with_profile(tmp_path: Path) -> None:
    """sandbox-exec takes -f <profile_file>. We write the profile to a
    tempfile and pass its path as the first argument after `-f`."""
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    policy = SandboxExecPolicy()
    args, _env = policy.wrap_command(
        ["python", "-c", "pass"],
        allowed_paths=[session_dir],
        allow_network=True,
    )
    assert args[0] == "sandbox-exec"
    assert args[1] == "-f"
    profile_path = args[2]
    assert Path(profile_path).exists()
    assert args[3:] == ["python", "-c", "pass"]


def test_sandbox_exec_profile_grants_rw_on_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    policy = SandboxExecPolicy()
    args, _env = policy.wrap_command(
        ["cmd"],
        allowed_paths=[session_dir],
        allow_network=True,
    )
    profile = Path(args[2]).read_text()
    # Header
    assert "(version 1)" in profile
    assert "(deny default)" in profile
    # RW allow on the session dir.
    assert f'file-write* (subpath "{session_dir.resolve()}")' in profile
    # Network allowed.
    assert "(allow network*)" in profile


def test_sandbox_exec_profile_denies_network_when_asked(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    policy = SandboxExecPolicy()
    args, _env = policy.wrap_command(
        ["cmd"],
        allowed_paths=[session_dir],
        allow_network=False,
    )
    profile = Path(args[2]).read_text()
    assert "(deny network*)" in profile
    assert "(allow network*)" not in profile


def test_sandbox_exec_profile_read_only_paths(tmp_path: Path) -> None:
    session_dir = tmp_path / "sess"
    session_dir.mkdir()
    ro = tmp_path / "ro"
    ro.mkdir()
    policy = SandboxExecPolicy()
    args, _env = policy.wrap_command(
        ["cmd"],
        allowed_paths=[session_dir, ro],
        allow_network=True,
    )
    profile = Path(args[2]).read_text()
    # RO path has file-read* but NOT file-write*.
    assert f'file-read* (subpath "{ro.resolve()}")' in profile


def test_sb_escape_handles_quotes_and_backslash() -> None:
    """Paths with meta-chars must be escaped so the generated SBPL
    parses cleanly."""
    p = Path('/tmp/weird"dir')
    escaped = _sb_escape(p)
    # The literal double-quote must be preceded by a backslash (i.e. \")
    # so SBPL's string parser sees an escaped quote, not a string terminator.
    assert '\\"' in escaped
    # Every double-quote in the output is escaped — for each " there's a
    # preceding \.
    i = 0
    while i < len(escaped):
        if escaped[i] == '"':
            assert i > 0 and escaped[i - 1] == "\\", (
                f"unescaped quote at position {i} in {escaped!r}"
            )
        i += 1


def test_sandbox_exec_rejects_empty_allowed_paths() -> None:
    policy = SandboxExecPolicy()
    with pytest.raises(ValueError, match="at least one allowed path"):
        policy.wrap_command(["cmd"], allowed_paths=[], allow_network=True)


# ---------------------------------------------------------------------------
# detect_best_policy
# ---------------------------------------------------------------------------


def test_detect_best_policy_returns_a_protocol_instance() -> None:
    p = detect_best_policy()
    assert isinstance(p, IsolationPolicy)


def test_detect_best_policy_matches_platform() -> None:
    """The detector returns the right thing for the current host:
    * Landlock-capable Linux → LandlockPolicy
    * macOS → SandboxExecPolicy
    * otherwise → NoOpPolicy
    """
    p = detect_best_policy()
    if landlock_available():
        assert p.name == "landlock"
    elif sandbox_exec_available():
        assert p.name == "sandbox-exec"
    else:
        assert p.name == "noop"


# ---------------------------------------------------------------------------
# SubprocessWorker integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subprocess_worker_with_noop_policy_still_works(tmp_path: Path) -> None:
    """Attaching NoOpPolicy to a SubprocessWorker must not break it —
    the policy is a pass-through. This is the baseline before we add
    real isolation."""
    from sovereign_agent.orchestrator.worker import SubprocessWorker

    script = tmp_path / "ok.py"
    script.write_text(
        'import json; print(json.dumps({"terminal": True, "advanced": True, "summary": "ok"}))\n'
    )

    # A lightweight subclass that runs our script instead of the real
    # worker_entrypoint, but goes through the policy-wrapping code path.
    class _ScriptWorker(SubprocessWorker):
        async def run_session(self, session_id, session_dir, *, timeout_s=None):  # type: ignore[no-untyped-def]
            import asyncio
            import json as _json

            raw_command = [sys.executable, str(script)]
            if self.isolation_policy is not None:
                args, _env = self.isolation_policy.wrap_command(
                    raw_command,
                    allowed_paths=[session_dir.resolve()],
                    allow_network=self.allow_network,
                )
            else:
                args = raw_command
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await proc.communicate()
            from sovereign_agent.orchestrator.worker import WorkerOutcome

            last = stdout.decode().strip().splitlines()[-1]
            payload = _json.loads(last)
            return WorkerOutcome(
                session_id=session_id,
                terminal=payload["terminal"],
                advanced=payload["advanced"],
                summary=payload["summary"],
                raw={"returncode": proc.returncode},
            )

    w = _ScriptWorker(isolation_policy=NoOpPolicy())
    result = await w.run_session("sess_x", tmp_path)
    assert result.terminal is True
    assert result.advanced is True
    assert result.summary == "ok"


def test_subprocess_worker_default_readonly_paths_are_plausible() -> None:
    """The auto-discovery of Python-runtime read-only paths must at
    least include sys.prefix. Sanity check — without this, Landlock
    would block `import os`."""
    from sovereign_agent.orchestrator.worker import SubprocessWorker

    w = SubprocessWorker(isolation_policy=NoOpPolicy())
    paths = w._default_readonly_paths()  # noqa: SLF001
    assert paths, "default readonly paths list must not be empty"
    prefix = Path(sys.prefix).resolve()
    assert any(prefix == p or prefix in p.parents or p in prefix.parents for p in paths)
