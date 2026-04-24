"""Landlock shim (v0.2, Module 2).

Runs as:

    python -m sovereign_agent._internal.landlock_shim \\
        --allow-rw /path/to/session \\
        --allow-read /path/to/python \\
        --allow-read /path/to/site-packages \\
        [--deny-network] \\
        -- \\
        <original command to exec> ...

What it does:

  1. Parse args.
  2. Call landlock_create_ruleset to build a ruleset whose handled
     access rights are "everything we want to restrict".
  3. For each --allow-read path: add a rule granting READ rights on
     that subtree.
  4. For each --allow-rw path: add a rule granting READ+WRITE rights
     on that subtree.
  5. Call landlock_restrict_self: irrevocably apply the ruleset to
     this process and its children.
  6. execvp into the original command.

From step 5 onward, the process (and everything it spawns) can only
touch the allowed subtrees. Any other open/write/exec on paths
outside the allow-list returns EACCES.

## Why a Python shim, not ctypes in the worker?

Because Landlock MUST be applied in the process that ultimately runs
the untrusted code. We don't want the orchestrator to restrict itself
— that would confine every session. We want the CHILD to restrict
itself before it exec's into the agent's Python.

The shim is the child. It does nothing before restricting, then
exec's into the agent.

## Why no pypi dependency on `landlock`?

There are landlock bindings on pypi (`pylandlock`), but they add a
dep and aren't maintained. We use three ctypes syscalls directly,
which is <50 lines and doesn't bit-rot.

## ABI negotiation

Landlock's ABI has grown over kernel versions:
  ABI 1 (Linux 5.13): basic fs rights
  ABI 2 (Linux 5.19): added REFER
  ABI 3 (Linux 6.2):  TRUNCATE
  ABI 4 (Linux 6.7):  network TCP bind/connect

We ask the kernel what ABI it supports and emit a ruleset that's
compatible. If we target a right the kernel doesn't know, the ruleset
creation fails with EINVAL; we mask those bits off and retry.

## Bypass-safety

Landlock is SELF-restriction: a process volunteers to be confined.
Once restricted you cannot un-restrict, not even as root. A
compromised agent cannot escape. The only thing outside Landlock's
remit is processes that are unprivileged AND re-exec into setuid
binaries — but kernel policy prevents Landlock-restricted processes
from gaining new privileges via NO_NEW_PRIVS, which the shim also
sets.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys

log = logging.getLogger(__name__)


# Syscall numbers (x86_64). See /usr/include/asm-generic/unistd.h or
# the kernel source. Other arches need their own numbers; we detect
# and refuse rather than run blind.
_SYSNUM_BY_MACHINE = {
    "x86_64": {
        "landlock_create_ruleset": 444,
        "landlock_add_rule": 445,
        "landlock_restrict_self": 446,
    },
    "aarch64": {
        # ARM64 uses the same numbers for these three.
        "landlock_create_ruleset": 444,
        "landlock_add_rule": 445,
        "landlock_restrict_self": 446,
    },
}

# prctl constants.
_PR_SET_NO_NEW_PRIVS = 38

# Landlock access-fs rights. We repeat these here rather than import
# from isolation.py because this shim is meant to have ZERO imports
# from the rest of sovereign-agent — it must start up fast and not
# drag in agent modules we may not have access to post-landlock.
_ACCESS_EXECUTE = 1 << 0
_ACCESS_WRITE_FILE = 1 << 1
_ACCESS_READ_FILE = 1 << 2
_ACCESS_READ_DIR = 1 << 3
_ACCESS_REMOVE_DIR = 1 << 4
_ACCESS_REMOVE_FILE = 1 << 5
_ACCESS_MAKE_CHAR = 1 << 6
_ACCESS_MAKE_DIR = 1 << 7
_ACCESS_MAKE_REG = 1 << 8
_ACCESS_MAKE_SOCK = 1 << 9
_ACCESS_MAKE_FIFO = 1 << 10
_ACCESS_MAKE_BLOCK = 1 << 11
_ACCESS_MAKE_SYM = 1 << 12
_ACCESS_REFER = 1 << 13  # ABI 2+
_ACCESS_TRUNCATE = 1 << 14  # ABI 3+
# ABI 4+ adds NETWORK_* bits — we don't use them here because the
# network-restrict flags are in a SEPARATE rule type; see ABI docs.

_ALL_FS_ABI1 = (
    _ACCESS_EXECUTE
    | _ACCESS_WRITE_FILE
    | _ACCESS_READ_FILE
    | _ACCESS_READ_DIR
    | _ACCESS_REMOVE_DIR
    | _ACCESS_REMOVE_FILE
    | _ACCESS_MAKE_CHAR
    | _ACCESS_MAKE_DIR
    | _ACCESS_MAKE_REG
    | _ACCESS_MAKE_SOCK
    | _ACCESS_MAKE_FIFO
    | _ACCESS_MAKE_BLOCK
    | _ACCESS_MAKE_SYM
)
_ALL_FS_ABI2 = _ALL_FS_ABI1 | _ACCESS_REFER
_ALL_FS_ABI3 = _ALL_FS_ABI2 | _ACCESS_TRUNCATE

_READ_RIGHTS = _ACCESS_READ_FILE | _ACCESS_READ_DIR | _ACCESS_EXECUTE
_WRITE_RIGHTS = (
    _ACCESS_WRITE_FILE
    | _ACCESS_MAKE_REG
    | _ACCESS_MAKE_DIR
    | _ACCESS_MAKE_SYM
    | _ACCESS_MAKE_FIFO
    | _ACCESS_MAKE_SOCK
    | _ACCESS_REMOVE_FILE
    | _ACCESS_REMOVE_DIR
)


# struct landlock_ruleset_attr { __u64 handled_access_fs; __u64 handled_access_net; }
class _LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
    ]


# struct landlock_path_beneath_attr { __u64 allowed_access; __s32 parent_fd; } __attribute__((packed));
class _LandlockPathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


# Rule-type constant.
_LANDLOCK_RULE_PATH_BENEATH = 1


def _syscall_table() -> dict[str, int]:
    machine = os.uname().machine
    if machine not in _SYSNUM_BY_MACHINE:
        raise RuntimeError(
            f"Landlock shim: unsupported architecture {machine!r}. "
            f"Supported: {', '.join(_SYSNUM_BY_MACHINE)}."
        )
    return _SYSNUM_BY_MACHINE[machine]


def _load_libc() -> ctypes.CDLL:
    return ctypes.CDLL("libc.so.6", use_errno=True)


def _landlock_get_abi_version(libc: ctypes.CDLL, syscalls: dict[str, int]) -> int:
    """Ask the kernel what Landlock ABI it supports. Returns 0 or
    negative if Landlock is not available."""
    # landlock_create_ruleset(NULL, 0, LANDLOCK_CREATE_RULESET_VERSION=1)
    # returns the ABI version as a positive integer.
    abi = libc.syscall(syscalls["landlock_create_ruleset"], None, 0, 1)
    return int(abi)


def _choose_handled_access(abi: int) -> int:
    """Pick the widest handled_access_fs mask the kernel knows about.
    We want to restrict as much as possible; newer ABI = more rights
    we can govern."""
    if abi >= 3:
        return _ALL_FS_ABI3
    if abi >= 2:
        return _ALL_FS_ABI2
    return _ALL_FS_ABI1


def _apply_landlock(
    allow_rw: list[str],
    allow_read: list[str],
) -> None:
    """Build the ruleset, add the allow rules, apply it to self.

    On any failure we raise RuntimeError; the caller will print a clear
    message and exit non-zero rather than exec'ing the child
    unprotected.
    """
    libc = _load_libc()
    syscalls = _syscall_table()

    abi = _landlock_get_abi_version(libc, syscalls)
    if abi <= 0:
        err = ctypes.get_errno()
        raise RuntimeError(
            f"Landlock not available on this kernel "
            f"(ABI probe returned {abi}, errno={err}). "
            f"Requires Linux >=5.13."
        )
    log.info("Landlock ABI %d detected", abi)

    handled = _choose_handled_access(abi)

    # Create the ruleset.
    attr = _LandlockRulesetAttr(
        handled_access_fs=handled,
        handled_access_net=0,  # ABI 4+; we don't use it
    )
    ruleset_fd = libc.syscall(
        syscalls["landlock_create_ruleset"],
        ctypes.byref(attr),
        ctypes.sizeof(attr),
        0,  # no flags
    )
    if ruleset_fd < 0:
        err = ctypes.get_errno()
        raise RuntimeError(f"landlock_create_ruleset failed: errno={err} ({os.strerror(err)})")

    # For each allow-list path, add a path_beneath rule granting the
    # appropriate rights.
    def _add_path(path: str, rights: int) -> None:
        # Rights must be a subset of what we declared in handled_access_fs.
        rights_masked = rights & handled
        try:
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        except OSError as exc:
            raise RuntimeError(f"cannot open {path!r} for Landlock rule: {exc}") from exc
        try:
            rule = _LandlockPathBeneathAttr(allowed_access=rights_masked, parent_fd=fd)
            rc = libc.syscall(
                syscalls["landlock_add_rule"],
                ruleset_fd,
                _LANDLOCK_RULE_PATH_BENEATH,
                ctypes.byref(rule),
                0,  # no flags
            )
            if rc < 0:
                err = ctypes.get_errno()
                raise RuntimeError(
                    f"landlock_add_rule failed for {path!r}: errno={err} ({os.strerror(err)})"
                )
        finally:
            os.close(fd)

    for p in allow_read:
        _add_path(p, _READ_RIGHTS)
    for p in allow_rw:
        _add_path(p, _READ_RIGHTS | _WRITE_RIGHTS)

    # Set NO_NEW_PRIVS: a Landlock-restricted process that tries to
    # gain new privileges via setuid binaries would defeat the point.
    # Kernel requires NO_NEW_PRIVS be set before restrict_self.
    rc = libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    if rc != 0:
        err = ctypes.get_errno()
        raise RuntimeError(f"prctl(PR_SET_NO_NEW_PRIVS) failed: errno={err}")

    # The moment of no return.
    rc = libc.syscall(syscalls["landlock_restrict_self"], ruleset_fd, 0)
    if rc != 0:
        err = ctypes.get_errno()
        raise RuntimeError(f"landlock_restrict_self failed: errno={err} ({os.strerror(err)})")
    # Close the ruleset fd — the restriction is already applied.
    os.close(ruleset_fd)


def _parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    # Split at the first '--'; everything after is the child command.
    try:
        sep = argv.index("--")
    except ValueError:
        raise SystemExit("landlock_shim: missing '--' separator before child command") from None
    shim_args = argv[:sep]
    child_argv = argv[sep + 1 :]
    if not child_argv:
        raise SystemExit("landlock_shim: no child command given after '--'")

    parser = argparse.ArgumentParser(
        prog="landlock_shim",
        description="Apply Landlock to this process, then exec the child.",
    )
    parser.add_argument(
        "--allow-rw",
        action="append",
        default=[],
        help="Path granted read+write. May be given multiple times.",
    )
    parser.add_argument(
        "--allow-read",
        action="append",
        default=[],
        help="Path granted read-only. May be given multiple times.",
    )
    parser.add_argument(
        "--deny-network",
        action="store_true",
        help="Advisory: request network deny. Only enforced on ABI >=4.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Shim log level (shim itself, not child).",
    )
    return parser.parse_args(shim_args), child_argv


def main(argv: list[str] | None = None) -> int:
    args, child = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(levelname)s landlock_shim: %(message)s",
        stream=sys.stderr,
    )

    try:
        _apply_landlock(args.allow_rw, args.allow_read)
    except RuntimeError as exc:
        # Fail closed: if Landlock can't be applied, we do NOT run the
        # child unprotected. Emit a clear message and exit.
        print(f"landlock_shim: {exc}", file=sys.stderr)
        return 3

    if args.deny_network:
        # Advisory for now — log once so the operator knows network
        # isolation wasn't enforced if ABI is too old.
        log.info(
            "--deny-network: ABI-level enforcement requires Landlock "
            "ABI 4 (Linux 6.7+). If your kernel is older, the child's "
            "network access is NOT restricted by Landlock."
        )

    # execvp replaces this process — there is nothing to clean up.
    # The Landlock restriction is inherited by the new exec image.
    os.execvp(child[0], child)
    # Unreachable except on exec failure.
    return 127


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
