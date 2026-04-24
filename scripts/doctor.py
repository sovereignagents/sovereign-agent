"""Comprehensive environment doctor for the sovereign-agent repo.

What this checks
================
Philosophy: a student running ``make doctor`` should see EVERYTHING
that might be wrong with their environment in one tabular view, with
each row marked ``✓`` (fine), ``⚠`` (works but worth knowing), or
``✗`` (broken, fix this first).

Categories covered:
  - Python version + platform
  - uv + uv.lock
  - Project layout (pyproject.toml at repo root, package imports)
  - .env presence + NEBIUS_KEY source + configured models
  - Dependencies (sovereign_agent, openai, typer, etc.)
  - Demos + examples importable
  - ruff + pytest available
  - Makefile + CI workflows present
  - Cached ci-real history (if any)

Pattern lifted from qv-llm's ``make doctor`` and adapted to our repo.
The structured output is what lets students paste the full block back
and get help without back-and-forth on "what version of Python?" etc.

Exit codes
==========
  0   all checks passed (✓ or ⚠ only)
  1   at least one ✗ — something is broken
  2   doctor itself crashed while checking
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class Check:
    name: str
    status: Status
    detail: str = ""
    hint: str = ""


@dataclass
class Section:
    title: str
    checks: list[Check] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# Output formatting
# ─────────────────────────────────────────────────────────────────────


class _C:
    """Minimal ANSI palette. Disabled if stdout isn't a terminal."""

    _on = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    @classmethod
    def _wrap(cls, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if cls._on else s

    @classmethod
    def green(cls, s: str) -> str:
        return cls._wrap("32", s)

    @classmethod
    def red(cls, s: str) -> str:
        return cls._wrap("31", s)

    @classmethod
    def yellow(cls, s: str) -> str:
        return cls._wrap("33", s)

    @classmethod
    def blue(cls, s: str) -> str:
        return cls._wrap("34", s)

    @classmethod
    def cyan(cls, s: str) -> str:
        return cls._wrap("36", s)

    @classmethod
    def dim(cls, s: str) -> str:
        return cls._wrap("2", s)

    @classmethod
    def bold(cls, s: str) -> str:
        return cls._wrap("1", s)


_MARKS = {
    Status.OK: lambda: _C.green("✓"),
    Status.WARN: lambda: _C.yellow("⚠"),
    Status.FAIL: lambda: _C.red("✗"),
}


def _print_check(c: Check, name_width: int = 22) -> None:
    mark = _MARKS[c.status]()
    name = c.name + " " * max(0, name_width - len(c.name))
    if c.status == Status.OK:
        print(f"  {_C.dim(name)}  {mark}  {c.detail}")
    elif c.status == Status.WARN:
        print(f"  {_C.dim(name)}  {mark}  {c.detail}")
        if c.hint:
            print(f"  {' ' * name_width}     {_C.dim('→ ' + c.hint)}")
    else:
        print(f"  {_C.dim(name)}  {mark}  {c.detail}")
        if c.hint:
            print(f"  {' ' * name_width}     {_C.dim('→ ' + c.hint)}")


def _print_section(section: Section) -> None:
    print()
    print(_C.bold(f"  {section.title}"))
    print(_C.dim("  " + "─" * 66))
    for c in section.checks:
        _print_check(c)


# ─────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────


def _check_python() -> Check:
    v = sys.version_info
    version_str = f"Python {v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < (3, 12):
        return Check(
            "python",
            Status.FAIL,
            f"{version_str} (need 3.12+)",
            hint="install a newer python (uv python install 3.12)",
        )
    return Check("python", Status.OK, f"{version_str} on {sys.platform}")


def _check_uv() -> Check:
    if shutil.which("uv") is None:
        return Check(
            "uv",
            Status.FAIL,
            "not installed",
            hint="curl -LsSf https://astral.sh/uv/install.sh | sh",
        )
    try:
        out = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=5)
        return Check("uv", Status.OK, out.stdout.strip() or "available")
    except Exception as e:  # noqa: BLE001
        return Check("uv", Status.WARN, f"found but unusable: {e}")


def _check_uv_lock(repo: Path) -> Check:
    lock = repo / "uv.lock"
    if not lock.exists():
        return Check(
            "uv.lock",
            Status.WARN,
            "missing (installs may not be reproducible)",
            hint="make lock",
        )
    return Check("uv.lock", Status.OK, "present")


def _check_pyproject(repo: Path) -> Check:
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return Check(
            "pyproject.toml",
            Status.FAIL,
            "missing",
            hint="this should be at the repo root",
        )
    return Check("pyproject.toml", Status.OK, "at repo root")


def _check_package_imports(repo: Path) -> Check:
    """Import the library and report version + __all__ count."""
    try:
        import sovereign_agent as sa  # noqa: PLC0415

        n = len(sa.__all__)
        return Check("sovereign_agent", Status.OK, f"v{sa.__version__}, {n} public exports")
    except ImportError as e:
        return Check(
            "sovereign_agent",
            Status.FAIL,
            f"cannot import: {e}",
            hint="make install (or rm -rf .venv && uv sync --all-groups --extra all)",
        )


def _check_tools_submodule() -> Check:
    """Explicitly check the submodule that's broken most often."""
    try:
        from sovereign_agent.tools.registry import ToolRegistry  # noqa: F401, PLC0415

        return Check("tools.registry", Status.OK, "importable")
    except ImportError as e:
        return Check(
            "tools.registry",
            Status.FAIL,
            f"cannot import: {e}",
            hint="sovereign_agent/tools/ missing (has happened before); reinstall",
        )


def _check_env_file(repo: Path) -> Check:
    env = repo / ".env"
    if not env.exists():
        return Check(
            ".env file",
            Status.WARN,
            "not found",
            hint="cp .env.example .env  (then edit and add NEBIUS_KEY)",
        )
    return Check(".env file", Status.OK, str(env.relative_to(repo)))


def _read_env_key(env_file: Path) -> str | None:
    """Extract NEBIUS_KEY=... from a .env file, stripping quotes."""
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        if key.strip() in ("NEBIUS_KEY", "export NEBIUS_KEY"):
            v = raw.strip().strip('"').strip("'")
            return v or None
    return None


def _check_api_key(repo: Path) -> Check:
    # Shell env has precedence when present (matches Python dotenv behavior
    # with override=False — .env is read only if the key isn't already set).
    shell_val = os.environ.get("NEBIUS_KEY")
    env_val = _read_env_key(repo / ".env")

    sources = []
    if shell_val and shell_val not in ("fake", "placeholder", "replace-me"):
        sources.append(("shell env", shell_val))
    if env_val and env_val not in ("fake", "placeholder", "replace-me", "your-nebius-api-key"):
        sources.append((".env", env_val))

    if not sources:
        return Check(
            "NEBIUS_KEY",
            Status.WARN,
            "not set or placeholder",
            hint="needed for any -real example. set in .env or export in shell.",
        )
    src, val = sources[0]
    # Show a short identifier prefix, not the full key
    masked = f"{val[:4]}…{val[-4:]}" if len(val) > 10 else "set"
    return Check("NEBIUS_KEY", Status.OK, f"{masked} (from {src})")


def _check_configured_models(repo: Path) -> Check:
    """Show which models .env has configured."""
    env = repo / ".env"
    if not env.exists():
        return Check("models", Status.WARN, "(.env missing)")

    planner = None
    executor = None
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        if key.strip() == "SOVEREIGN_AGENT_LLM_PLANNER_MODEL":
            planner = val
        elif key.strip() == "SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL":
            executor = val

    if not planner and not executor:
        return Check(
            "models",
            Status.OK,
            "defaults (sovereign_agent/config.py)",
        )
    detail_parts = []
    if planner:
        detail_parts.append(f"planner={planner}")
    if executor:
        detail_parts.append(f"executor={executor}")
    return Check("models", Status.OK, "  ".join(detail_parts))


def _check_demos_importable(repo: Path) -> Check:
    """Try importing each chapter demo module. Fail fast on any import error."""
    import importlib

    # Add repo to sys.path so relative imports work
    sys.path.insert(0, str(repo))
    try:
        failed: list[str] = []
        for name in [
            "chapters.chapter_01_session.demo",
            "chapters.chapter_02_queue.demo",
            "chapters.chapter_03_ipc.demo",
            "chapters.chapter_04_scheduler.demo",
            "chapters.chapter_05_planner_executor.demo",
        ]:
            try:
                importlib.import_module(name)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{name.split('.')[-2]}: {type(e).__name__}")
        if failed:
            return Check(
                "chapter demos",
                Status.FAIL,
                f"{len(failed)}/5 failed to import",
                hint=f"first: {failed[0]}",
            )
        return Check("chapter demos", Status.OK, "5/5 importable")
    finally:
        if str(repo) in sys.path:
            sys.path.remove(str(repo))


def _check_examples_importable(repo: Path) -> Check:
    """Try importing each example run module."""
    import importlib

    sys.path.insert(0, str(repo))
    try:
        failed: list[str] = []
        names = [
            "examples.research_assistant.run",
            "examples.code_reviewer.run",
            "examples.pub_booking.run",
            "examples.parallel_research.run",
            "examples.isolated_worker.run",
            "examples.session_resume_chain.run",
            "examples.classifier_rule.run",
            "examples.hitl_deposit.run",
        ]
        for name in names:
            try:
                importlib.import_module(name)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{name.split('.')[-2]}: {type(e).__name__}")
        if failed:
            return Check(
                "example scenarios",
                Status.FAIL,
                f"{len(failed)}/{len(names)} failed to import",
                hint=f"first: {failed[0]}",
            )
        return Check("example scenarios", Status.OK, f"{len(names)}/{len(names)} importable")
    finally:
        if str(repo) in sys.path:
            sys.path.remove(str(repo))


def _check_ruff() -> Check:
    try:
        out = subprocess.run(
            ["uv", "run", "ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            return Check("ruff", Status.OK, out.stdout.strip())
    except Exception:  # noqa: BLE001
        pass
    return Check(
        "ruff",
        Status.WARN,
        "not available via uv run",
        hint="make install (ruff is a dev dep)",
    )


def _check_pytest() -> Check:
    try:
        out = subprocess.run(
            ["uv", "run", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            return Check("pytest", Status.OK, out.stdout.strip().split("\n")[0])
    except Exception:  # noqa: BLE001
        pass
    return Check(
        "pytest",
        Status.WARN,
        "not available via uv run",
        hint="make install",
    )


def _check_github_workflows(repo: Path) -> Check:
    ci = repo / ".github" / "workflows" / "ci.yml"
    publish = repo / ".github" / "workflows" / "publish.yml"
    have = []
    if ci.exists():
        have.append("ci.yml")
    if publish.exists():
        have.append("publish.yml")
    if not have:
        return Check(
            "CI workflows",
            Status.WARN,
            "no workflows in .github/workflows/",
            hint="CI won't run on pushes; see docs/API.md",
        )
    return Check("CI workflows", Status.OK, " + ".join(have))


def _check_ci_real_history() -> Check:
    """Peek at the ci-real cache to show recent activity."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    cache = base / "sovereign-agent" / "ci-real"
    if not cache.exists():
        return Check("ci-real history", Status.OK, "no runs yet")
    runs = sorted(
        (p for p in cache.iterdir() if p.is_dir() and p.name != "latest"),
        reverse=True,
    )
    if not runs:
        return Check("ci-real history", Status.OK, "no runs yet")
    return Check("ci-real history", Status.OK, f"{len(runs)} run(s) cached; latest: {runs[0].name}")


# ─────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────


def find_repo_root() -> Path:
    """Walk up from this script to find the repo root."""
    here = Path(__file__).resolve().parent
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return here


def main() -> int:
    repo = find_repo_root()

    print()
    print(_C.cyan("━" * 72))
    print(_C.bold("  sovereign-agent") + _C.dim("  ·  ") + _C.bold("environment doctor"))
    print(_C.dim(f"  repo: {repo}"))
    print(_C.cyan("━" * 72))

    sections = [
        Section(
            "Runtime & tooling",
            [
                _check_python(),
                _check_uv(),
                _check_uv_lock(repo),
                _check_ruff(),
                _check_pytest(),
            ],
        ),
        Section(
            "Project layout",
            [
                _check_pyproject(repo),
                _check_package_imports(repo),
                _check_tools_submodule(),
                _check_github_workflows(repo),
            ],
        ),
        Section(
            "LLM configuration",
            [
                _check_env_file(repo),
                _check_api_key(repo),
                _check_configured_models(repo),
            ],
        ),
        Section(
            "Demos & examples",
            [
                _check_demos_importable(repo),
                _check_examples_importable(repo),
            ],
        ),
        Section(
            "ci-real cache",
            [
                _check_ci_real_history(),
            ],
        ),
    ]

    for section in sections:
        _print_section(section)

    # Summary footer
    all_checks = [c for section in sections for c in section.checks]
    n_ok = sum(1 for c in all_checks if c.status == Status.OK)
    n_warn = sum(1 for c in all_checks if c.status == Status.WARN)
    n_fail = sum(1 for c in all_checks if c.status == Status.FAIL)

    print()
    print(_C.cyan("━" * 72))
    if n_fail:
        print(
            f"  {_C.red('✗')} "
            + _C.bold(f"{n_fail} broken")
            + _C.dim(f"  ·  {n_warn} warning(s)  ·  {n_ok} OK")
        )
        print()
        print(
            _C.dim(
                "  Fix the ✗ rows first. Most are solved by: make install  "
                "(or rm -rf .venv && uv sync --all-groups --extra all)"
            )
        )
    elif n_warn:
        print(f"  {_C.yellow('⚠')} " + _C.bold(f"{n_warn} warning(s)") + _C.dim(f"  ·  {n_ok} OK"))
        print(_C.dim("  Warnings are non-blocking. See the → hints above."))
    else:
        print(f"  {_C.green('✓')} " + _C.bold(f"all {n_ok} checks passed"))
        print(
            _C.dim(
                "  Try: make ci-real-estimate (cost preview) or "
                "make ci-real-quick (cheapest real call)."
            )
        )
    print(_C.cyan("━" * 72))
    print()

    return 1 if n_fail else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        import traceback

        print(f"\n{_C.red('✗')} doctor itself crashed: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(2)
