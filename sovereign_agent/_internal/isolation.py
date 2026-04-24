"""Process isolation policies (v0.2, Module 2).

## Goal

When a session runs via SubprocessWorker, we want the child process to
have a bounded view of the filesystem: it can read/write its session
directory, read the sovereign-agent install and the Python runtime,
and nothing else. No browsing /home, no reading ~/.ssh, no clobbering
files outside the session.

We achieve this with OS-native isolation primitives, not containers:

  * **Linux ≥ 5.13**: Landlock LSM. A process irrevocably restricts
    its own filesystem view via three syscalls (landlock_create_ruleset,
    landlock_add_rule, landlock_restrict_self). Once restricted, it
    cannot un-restrict — not even as root. Kernel-enforced.

  * **macOS**: sandbox-exec(1). Apple's own per-process sandbox, same
    underlying framework that confines every App Store app. The policy
    is a .sb file in a Scheme-like DSL; we generate it from the allowed
    paths.

  * **Elsewhere (Windows, old kernels)**: NoOpPolicy. We log a warning
    and let the child run unrestricted. Better than silently failing.

## Why not Docker, bwrap, firejail?

  * Docker needs a daemon; students should not have to install Docker
    Desktop.
  * bubblewrap / firejail are fine but they're setuid binaries not
    present everywhere and require extra install steps.
  * Landlock + sandbox-exec are already in every modern Linux/macOS
    install. Zero install friction, real kernel-enforced isolation.

## The contract

    class IsolationPolicy(Protocol):
        name: str
        def wrap_command(
            self,
            command: list[str],
            *,
            allowed_paths: list[Path],
            allow_network: bool,
        ) -> tuple[list[str], dict[str, str]]: ...

Given a command and an allow-list, return the wrapped command (suitable
for asyncio.create_subprocess_exec) and extra env vars. The subprocess
worker runs whatever comes back. This keeps the policy pure and
testable.

## What's enforced vs. what isn't

  Filesystem: strongly enforced on Linux (Landlock) and macOS (sandbox-exec).
  Network: partial. sandbox-exec can deny network; Landlock 6.7+ can
    restrict TCP connect/bind, but many kernels don't have that yet.
    Network isolation is an advisory flag for now.
  CPU/RAM: not our problem. Use cgroups or `ulimit` at the orchestrator
    level if you need resource limits.
  Syscalls: out of scope. For syscall filtering you want seccomp, which
    is a separate concern (and a separate v0.3 module if ever).
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


@runtime_checkable
class IsolationPolicy(Protocol):
    """How to wrap a subprocess command so it runs confined.

    Implementations are pure: same inputs produce the same wrapped
    command. No side effects until the command is actually spawned.
    """

    name: str

    def wrap_command(
        self,
        command: list[str],
        *,
        allowed_paths: list[Path],
        allow_network: bool,
    ) -> tuple[list[str], dict[str, str]]: ...


# ---------------------------------------------------------------------------
# NoOpPolicy — last-resort fallback
# ---------------------------------------------------------------------------


class NoOpPolicy:
    """No isolation. Used on platforms where no primitive is available,
    and as an explicit opt-out for debugging.

    Emits a warning the first time it's used so students don't silently
    run unconfined agents thinking they're sandboxed.
    """

    name = "noop"

    _warned = False

    def wrap_command(
        self,
        command: list[str],
        *,
        allowed_paths: list[Path],
        allow_network: bool,
    ) -> tuple[list[str], dict[str, str]]:
        if not NoOpPolicy._warned:
            log.warning(
                "NoOpPolicy: subprocess will run WITHOUT filesystem isolation. "
                "Install on Linux >=5.13 or macOS for kernel-enforced isolation."
            )
            NoOpPolicy._warned = True
        return list(command), {}


# ---------------------------------------------------------------------------
# Landlock (Linux ≥ 5.13)
# ---------------------------------------------------------------------------

# Landlock ABI version we target. ABI 2 (Linux 5.19+) added refer
# semantics. ABI 1 is enough for our needs and works on Linux 5.13+.
# We'll negotiate down at runtime if the kernel is older.
_LANDLOCK_ABI_TARGET = 2

# Syscall numbers (x86_64). If we ever care about other architectures,
# we expand this table.
_LANDLOCK_CREATE_RULESET_SYSNUM = 444
_LANDLOCK_ADD_RULE_SYSNUM = 445
_LANDLOCK_RESTRICT_SELF_SYSNUM = 446

# Landlock access-filesystem rights (from uapi/linux/landlock.h).
# We keep them here as constants rather than importing a library so
# the module has no extra runtime deps — the pattern is the same a
# Chromium-style sandbox helper uses.
_LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0
_LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
_LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
_LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3
_LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4
_LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
_LANDLOCK_ACCESS_FS_MAKE_CHAR = 1 << 6
_LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
_LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
_LANDLOCK_ACCESS_FS_MAKE_SOCK = 1 << 9
_LANDLOCK_ACCESS_FS_MAKE_FIFO = 1 << 10
_LANDLOCK_ACCESS_FS_MAKE_BLOCK = 1 << 11
_LANDLOCK_ACCESS_FS_MAKE_SYM = 1 << 12
_LANDLOCK_ACCESS_FS_REFER = 1 << 13  # ABI 2+

_FS_READ = (
    _LANDLOCK_ACCESS_FS_READ_FILE | _LANDLOCK_ACCESS_FS_READ_DIR | _LANDLOCK_ACCESS_FS_EXECUTE
)
_FS_WRITE = (
    _LANDLOCK_ACCESS_FS_WRITE_FILE
    | _LANDLOCK_ACCESS_FS_MAKE_REG
    | _LANDLOCK_ACCESS_FS_MAKE_DIR
    | _LANDLOCK_ACCESS_FS_MAKE_SYM
    | _LANDLOCK_ACCESS_FS_MAKE_FIFO
    | _LANDLOCK_ACCESS_FS_MAKE_SOCK
    | _LANDLOCK_ACCESS_FS_REMOVE_FILE
    | _LANDLOCK_ACCESS_FS_REMOVE_DIR
)


def landlock_available() -> bool:
    """Check whether Landlock is usable on this host.

    We try to call landlock_create_ruleset with a zero-sized probe; if
    the syscall returns a non-negative ABI version, Landlock is
    available. Any other outcome (ENOSYS, EOPNOTSUPP, not-Linux) means
    not available.

    We never leave a real ruleset behind — the probe call uses size=0
    which returns just the ABI number.
    """
    if sys.platform != "linux":
        return False
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
    except OSError:
        return False
    # syscall(SYS_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION=1)
    try:
        abi = libc.syscall(
            _LANDLOCK_CREATE_RULESET_SYSNUM,
            None,
            0,
            1,  # _VERSION flag = 1
        )
    except Exception:  # noqa: BLE001
        return False
    return abi > 0


@dataclass
class LandlockPolicy:
    """Landlock-based isolation.

    On Linux ≥ 5.13, we wrap the command so that it restricts itself
    BEFORE executing the real payload:

      python -m sovereign_agent._internal.landlock_shim \\
          --allow-read /read/path --allow-rw /rw/path -- \\
          <original command ...>

    The shim calls landlock_create_ruleset / add_rule / restrict_self
    using ctypes — no native deps — then exec's into the original
    command. From that point on the child's filesystem view is
    kernel-confined. It can't escape even if it runs as root.

    Network: Landlock network restrictions (TCP) require ABI 4 (Linux
    6.7+). We flag allow_network=False but don't enforce it unless
    available. Document the gap; don't pretend.
    """

    name: str = "landlock"
    abi_target: int = field(default=_LANDLOCK_ABI_TARGET)

    def wrap_command(
        self,
        command: list[str],
        *,
        allowed_paths: list[Path],
        allow_network: bool,
    ) -> tuple[list[str], dict[str, str]]:
        # Split allowed_paths into read-only (everything the child needs
        # for the Python runtime) and read-write (the session dir).
        # We don't invent this split; the caller tells us via a
        # convention: the FIRST path in `allowed_paths` is the
        # read-write one (typically the session dir). Everything after
        # is read-only.
        #
        # This is a deliberate contract — it keeps the policy pure and
        # the caller-side explicit about which path is writable.
        if not allowed_paths:
            raise ValueError(
                "LandlockPolicy requires at least one allowed path (the session dir, read-write)"
            )
        rw_path = allowed_paths[0]
        ro_paths = allowed_paths[1:]

        shim_args: list[str] = [
            sys.executable,
            "-m",
            "sovereign_agent._internal.landlock_shim",
            "--allow-rw",
            str(rw_path),
        ]
        for ro in ro_paths:
            shim_args.extend(["--allow-read", str(ro)])
        if not allow_network:
            # Advisory for now. The shim may log a warning if the
            # kernel ABI doesn't support network restrictions.
            shim_args.append("--deny-network")
        shim_args.append("--")
        shim_args.extend(command)

        return shim_args, {}


# ---------------------------------------------------------------------------
# macOS sandbox-exec
# ---------------------------------------------------------------------------


def sandbox_exec_available() -> bool:
    """sandbox-exec has been present on macOS since 10.5 (2007). The
    binary is deprecated (Apple marked it as such in 10.14) but still
    ships and still works through at least macOS 15. We prefer it over
    nothing while noting that Apple may eventually remove it."""
    if sys.platform != "darwin":
        return False
    return shutil.which("sandbox-exec") is not None


@dataclass
class SandboxExecPolicy:
    """macOS isolation using sandbox-exec.

    We generate a .sb profile at wrap time with:

      (version 1)
      (deny default)
      (allow process-fork)
      (allow process-exec)
      (allow signal (target self))
      (allow file-read-metadata)
      (allow file-read* (subpath "/allowed/read/path"))
      (allow file-read* file-write* (subpath "/allowed/rw/path"))
      ; network
      (deny network*)   ; if allow_network=False
      (allow network*)  ; if allow_network=True

    Written to a temp file, passed to sandbox-exec via -f. The temp
    file is cleaned up by the OS; we keep them under /tmp.

    Caveat: sandbox-exec is officially deprecated ("SBPL is SPI"). It
    continues to work, but Apple has not committed to keeping it
    forever. We isolate the logic here so a future switch (to
    Endpoint Security, or to sandbox_init libraries) is localised.
    """

    name: str = "sandbox-exec"

    def wrap_command(
        self,
        command: list[str],
        *,
        allowed_paths: list[Path],
        allow_network: bool,
    ) -> tuple[list[str], dict[str, str]]:
        if not allowed_paths:
            raise ValueError(
                "SandboxExecPolicy requires at least one allowed path (the session dir, read-write)"
            )
        rw_path = allowed_paths[0]
        ro_paths = allowed_paths[1:]

        profile_lines = [
            "(version 1)",
            "(deny default)",
            # Basic execution primitives the child needs.
            "(allow process-fork)",
            "(allow process-exec)",
            "(allow signal (target self))",
            "(allow sysctl-read)",
            "(allow mach-lookup)",
            "(allow ipc-posix-shm)",
            "(allow iokit-open)",  # Python runtime needs this on modern macOS
            # Metadata is read freely (stat, access). The actual bytes
            # are still gated by file-read*.
            "(allow file-read-metadata)",
            # Read-write allow on the session dir.
            f'(allow file-read* file-write* (subpath "{_sb_escape(rw_path)}"))',
        ]
        for ro in ro_paths:
            profile_lines.append(f'(allow file-read* (subpath "{_sb_escape(ro)}"))')
        # Network
        if allow_network:
            profile_lines.append("(allow network*)")
        else:
            profile_lines.append("(deny network*)")
        profile = "\n".join(profile_lines) + "\n"

        # Write to a tmp file. sandbox-exec reads this before spawn.
        # We can't clean it up inside wrap_command (child hasn't run
        # yet), so we rely on /tmp cleanup or on the OS reaping at
        # reboot. This is the same pattern `mktemp + exec` scripts use.
        fd, path = tempfile.mkstemp(prefix="sa_sandbox_", suffix=".sb")
        os.write(fd, profile.encode("utf-8"))
        os.close(fd)

        wrapped = ["sandbox-exec", "-f", path, *command]
        return wrapped, {}


def _sb_escape(p: Path) -> str:
    """Escape a path for embedding in an SBPL string literal. SBPL uses
    backslash escaping similar to C. Path characters we worry about:
    backslash, double-quote. Paths with these are rare but we handle
    them rather than break mysteriously."""
    s = str(p.resolve())
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def detect_best_policy() -> IsolationPolicy:
    """Return the strongest isolation policy available on this host.

    Order: LandlockPolicy > SandboxExecPolicy > NoOpPolicy.

    We log which one we picked at INFO level. If we fall back to NoOp,
    we log a warning — students should know their agents are running
    unconfined.
    """
    if landlock_available():
        log.info("isolation: using LandlockPolicy (Linux kernel supports Landlock)")
        return LandlockPolicy()
    if sandbox_exec_available():
        log.info("isolation: using SandboxExecPolicy (macOS sandbox-exec)")
        return SandboxExecPolicy()
    log.warning(
        "isolation: no supported primitive available on this host (%s). "
        "Subprocess workers will run unconfined. Install on Linux >=5.13 "
        "or macOS for kernel-enforced isolation.",
        platform.platform(),
    )
    return NoOpPolicy()


__all__ = [
    "IsolationPolicy",
    "LandlockPolicy",
    "NoOpPolicy",
    "SandboxExecPolicy",
    "detect_best_policy",
    "landlock_available",
    "sandbox_exec_available",
]
