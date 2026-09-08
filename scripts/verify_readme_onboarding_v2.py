#!/usr/bin/env python3
"""Behaviorally prove the README's documented onboarding sequence.

RULING-418 (org issue #184, Unit 12 track) found that the "## Unit 1 gates"
section of README.md listed bare `python ...` / `sovereign-agent ...`
commands after `uv sync`. A bare command is not guaranteed to run inside the
project's managed virtualenv -- a stale global `python` or `sovereign-agent`
shadowing the project's own can silently intercept it, so the gate either
fails confusingly or "passes" against the wrong environment.

Grepping the README for the string `uv run` would only prove the TEXT
changed, not that the documented sequence actually works. This script proves
behavior instead: it extracts the exact commands from the README's fenced
code blocks, materializes a genuinely clean copy of the repository (a fresh
`git archive` extraction, not a reused working tree), points `uv` at a fresh
cache and a fresh project environment so no prior `uv sync` in this checkout
can be reused, and then runs the real documented sequence -- `uv sync`
followed by each Unit 1 gate command -- as real subprocesses against that
clean state, asserting each one's actual exit code is 0.

If any documented command is not qualified with `uv run` (or is `uv sync`
itself), and a decoy `python`/`sovereign-agent` shim earlier on PATH would
intercept it, this script fails and names exactly which documented line
broke -- the same failure mode the live README defect produced.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
GATES_HEADING = "## Unit 1 gates"

# Every one of these must appear, verbatim, as its own documented gate
# command. This is the behavioral contract this script proves -- not a
# regex over the README's prose, but the literal command line this script
# is about to execute for real.
REQUIRED_GATE_COMMANDS = (
    "uv run python -m pytest -q",
    "uv run python scripts/verify_runtime_dependencies.py",
    "uv run python scripts/verify_source_budget_v2.py",
    "uv run sovereign-agent --help",
    "uv run sovereign-agent doctor",
)

DECOY_SHIM = textwrap.dedent(
    """\
    #!/bin/sh
    echo "DECOY: a stale global '$(basename "$0")' ran instead of the project's own" >&2
    exit 99
    """
)


def _extract_gates_block(readme_text: str) -> list[str]:
    """Return the shell lines inside the fenced block under GATES_HEADING."""
    if GATES_HEADING not in readme_text:
        raise AssertionError(f"README.md has no {GATES_HEADING!r} section")
    after_heading = readme_text.split(GATES_HEADING, 1)[1]
    fence_match = re.search(r"```bash\n(.*?)\n```", after_heading, re.DOTALL)
    if not fence_match:
        raise AssertionError(f"no ```bash fenced block found under {GATES_HEADING!r}")
    lines = [line.strip() for line in fence_match.group(1).splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"{GATES_HEADING!r} fenced block is empty")
    return lines


def _make_decoy_path(tmp_root: Path) -> Path:
    """A PATH entry with fake `python`/`sovereign-agent` that fail loudly.

    This is the behavioral trap: if a documented command is a bare `python`
    or `sovereign-agent` invocation (not routed through `uv run`), *this*
    decoy is what a stale global tool looks like on a learner's machine, and
    it will be found first. A command correctly qualified with `uv run`
    never consults this PATH entry at all, because `uv run` resolves the
    interpreter/entry point from the project's own synced environment.
    """
    decoy_dir = tmp_root / "decoy-path"
    decoy_dir.mkdir(parents=True, exist_ok=True)
    for name in ("python", "python3", "sovereign-agent"):
        shim = decoy_dir / name
        shim.write_text(DECOY_SHIM, encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return decoy_dir


def _clean_worktree_copy(dest: Path) -> None:
    """Materialize a clone-equivalent copy of the repo's tracked files only.

    Uses `git archive` on HEAD so build artifacts, .venv, __pycache__, and any
    other untracked local cruft in this checkout cannot leak into the
    "fresh clone" this script is supposed to be proving the sequence against.
    """
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    subprocess.run(["tar", "-x"], input=archive.stdout, cwd=dest, check=True)


def _run_step(
    description: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    print(f"--- {description}: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise AssertionError(
            f"documented step failed (exit {result.returncode}): {description}\n"
            f"  command: {' '.join(command)}"
        )
    print("    OK (exit 0)")


def main() -> int:
    readme_text = README.read_text(encoding="utf-8")
    gate_lines = _extract_gates_block(readme_text)

    missing = [cmd for cmd in REQUIRED_GATE_COMMANDS if cmd not in gate_lines]
    if missing:
        print("FAIL: README's Unit 1 gates block is missing required commands:")
        for cmd in missing:
            print(f"  - {cmd!r}")
        print(f"actual fenced block contents: {gate_lines}")
        return 1

    unqualified = [
        line
        for line in gate_lines
        if (line.startswith("python ") or line.startswith("sovereign-agent "))
        and not line.startswith("uv run")
    ]
    if unqualified:
        print("FAIL: README's Unit 1 gates block has bare commands not run through uv run:")
        for line in unqualified:
            print(f"  - {line!r}")
        return 1

    with tempfile.TemporaryDirectory(prefix="sovereign-agent-onboarding-smoke-") as tmp:
        tmp_root = Path(tmp)
        fresh_repo = tmp_root / "repo"
        fresh_cache = tmp_root / "uv-cache"
        fresh_venv = tmp_root / ".venv"
        decoy_path = _make_decoy_path(tmp_root)

        print(f"Materializing a clean clone-equivalent tree at {fresh_repo}")
        _clean_worktree_copy(fresh_repo)
        if (fresh_repo / ".venv").exists():
            raise AssertionError("fresh checkout must not already contain a .venv")

        # A hostile PATH: the decoy shims come FIRST, exactly like a stale
        # global python/sovereign-agent shadowing the project's own would.
        # `uv` and `git` themselves still need to resolve, so keep the real
        # PATH after the decoy.
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join([str(decoy_path), env.get("PATH", "")])
        env["UV_CACHE_DIR"] = str(fresh_cache)
        env["UV_PROJECT_ENVIRONMENT"] = str(fresh_venv)
        env.pop("VIRTUAL_ENV", None)

        _run_step("uv sync", ["uv", "sync"], cwd=fresh_repo, env=env)

        for line in gate_lines:
            _run_step(f"documented gate: {line}", line.split(), cwd=fresh_repo, env=env)

    print("\nAll documented onboarding steps executed for real, from a clean")
    print("state, hostile PATH included, and every one exited 0.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        sys.exit(1)
