"""Preflight: comprehensive sanity check before running the full suite.

Goes beyond `sovereign-agent doctor` (which is end-user-facing) and
covers the contributor surface:

  - uv present + lockfile in sync
  - package imports cleanly
  - ruff lint passes
  - pytest collects every test (no syntax errors, no import failures)
  - chapter-drift check passes
  - all chapter demos are importable
  - all example scenarios are importable

Exits 0 on all-green, 1 on any issue.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CHAPTER_MODULES = [
    "chapters.chapter_01_session",
    "chapters.chapter_02_queue",
    "chapters.chapter_03_ipc",
    "chapters.chapter_04_scheduler",
    "chapters.chapter_05_planner_executor",
]

EXAMPLE_MODULES = [
    "examples.research_assistant.run",
    "examples.code_reviewer.run",
    "examples.pub_booking.run",
]


def check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "✓" if ok else "✗"
    line = f"  {icon}  {label}"
    if detail:
        line += f"  — {detail}"
    print(line)
    return ok


def run(*cmd: str, timeout: int = 120) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"


def main() -> int:
    print()
    print("preflight checks")
    print("─" * 68)

    issues = 0

    # Ensure the repo root is on sys.path so `chapters.` and `examples.` resolve.
    sys.path.insert(0, str(REPO_ROOT))

    # 1. uv present
    rc, out = run("uv", "--version")
    if not check("uv available", rc == 0, out if rc == 0 else "install from https://astral.sh/uv"):
        issues += 1

    # 2. lockfile present
    lock_exists = (REPO_ROOT / "uv.lock").exists()
    if not check(
        "uv.lock present",
        lock_exists,
        "" if lock_exists else "run: uv sync --all-groups",
    ):
        issues += 1

    # 3. package imports cleanly
    try:
        import sovereign_agent

        version = sovereign_agent.__version__
        exports = len(sovereign_agent.__all__)
        if not check("package imports", True, f"v{version}, {exports} exports"):
            issues += 1
    except Exception as exc:  # noqa: BLE001
        check("package imports", False, f"{type(exc).__name__}: {exc}")
        issues += 1

    # 4. ruff clean
    rc, out = run(
        "uv",
        "run",
        "ruff",
        "check",
        "sovereign_agent/",
        "tests/",
        "chapters/",
        "examples/",
        "scripts/",
    )
    if not check("ruff lint", rc == 0, "" if rc == 0 else f"exit {rc}"):
        issues += 1

    # 5. pytest collection (no imports failed, no syntax errors)
    rc, out = run("uv", "run", "pytest", "--collect-only", "-q")
    if not check(
        "pytest collects cleanly",
        rc == 0,
        "" if rc == 0 else "something in tests/ or chapters/ won't import",
    ):
        issues += 1
        if out:
            # Show the first error line to speed up triage.
            for line in out.splitlines()[-10:]:
                print(f"       {line}")

    # 6. drift check
    rc, out = run("uv", "run", "python", "tools/verify_chapter_drift.py")
    if not check(
        "chapter drift check", rc == 0, "" if rc == 0 else "chapter solutions out of sync"
    ):
        issues += 1

    # 7. chapter demos importable
    for mod in CHAPTER_MODULES:
        try:
            importlib.import_module(mod + ".demo")
            check(f"{mod}.demo importable", True)
        except Exception as exc:  # noqa: BLE001
            check(f"{mod}.demo importable", False, f"{type(exc).__name__}: {exc}")
            issues += 1

    # 8. example scenarios importable
    for mod in EXAMPLE_MODULES:
        try:
            importlib.import_module(mod)
            check(f"{mod} importable", True)
        except Exception as exc:  # noqa: BLE001
            check(f"{mod} importable", False, f"{type(exc).__name__}: {exc}")
            issues += 1

    print("─" * 68)
    if issues:
        print(f"  ✗  {issues} issue(s) found")
        return 1
    print("  ✓  preflight green — safe to run the full suite")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
