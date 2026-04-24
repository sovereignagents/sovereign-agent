#!/usr/bin/env python3
"""verify_setup.py — pre-flight diagnostics for sovereign-agent.

Checks everything required to do real work with a real LLM:

  - Python version (>= 3.12)
  - .env file present and readable
  - NEBIUS_KEY (or configured LLM key) set to a non-placeholder value
  - Package imports cleanly
  - uv.lock present (reproducible installs)
  - Filesystem writable where sessions will land
  - Mount allowlist present
  - LLM endpoint reachable with a real (tiny) completion round-trip
  - Chapter drift clean
  - Ruff clean

Run:

    make verify
    # or
    uv run python scripts/verify_setup.py

Exit code: 0 if all checks pass, 1 otherwise.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Colors (auto-disabled when not a TTY) ───────────────────────────────
_TTY = sys.stdout.isatty()
GREEN = "\033[92m" if _TTY else ""
YELLOW = "\033[93m" if _TTY else ""
RED = "\033[91m" if _TTY else ""
BLUE = "\033[94m" if _TTY else ""
MAGENTA = "\033[95m" if _TTY else ""
BOLD = "\033[1m" if _TTY else ""
DIM = "\033[2m" if _TTY else ""
RESET = "\033[0m" if _TTY else ""


def ok(msg: str) -> None:
    print(f"{GREEN}  ✓  {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}  ⚠  {msg}{RESET}")


def fail(msg: str) -> None:
    print(f"{RED}  ✗  {msg}{RESET}")


def hint(msg: str) -> None:
    print(f"{DIM}       → {msg}{RESET}")


def info(msg: str) -> None:
    print(f"{BLUE}  ℹ  {msg}{RESET}")


def section(title: str) -> None:
    print(f"\n{BLUE}{BOLD}{'─' * 58}{RESET}")
    print(f"{BLUE}{BOLD}  {title}{RESET}")
    print(f"{BLUE}{BOLD}{'─' * 58}{RESET}")


# ────────────────────────────────────────────────────────────────────────
# .env loading — tiny implementation so we don't need python-dotenv
# ────────────────────────────────────────────────────────────────────────


def load_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Ignores comments, empty lines, exports."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if v and v[0] in "\"'" and v[0] == v[-1]:
            v = v[1:-1]
        result[k] = v
    return result


def merge_env(dotenv: dict[str, str]) -> dict[str, str]:
    """Shell env takes precedence over .env (standard dotenv semantics)."""
    merged = dict(dotenv)
    merged.update(os.environ)
    return merged


# ────────────────────────────────────────────────────────────────────────
# Individual checks
# ────────────────────────────────────────────────────────────────────────


def check_python_version() -> int:
    v = sys.version_info
    if (v.major, v.minor) >= (3, 12):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return 0
    fail(f"Python {v.major}.{v.minor} — sovereign-agent requires 3.12+")
    hint("pyenv install 3.12 && pyenv local 3.12")
    return 1


def check_uv_installed() -> int:
    if shutil.which("uv") is None:
        fail("uv is not on PATH")
        hint("curl -LsSf https://astral.sh/uv/install.sh | sh")
        return 1
    try:
        out = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=5)
        ok(f"uv available — {out.stdout.strip()}")
        return 0
    except Exception as e:  # noqa: BLE001
        fail(f"uv present but broken: {e}")
        return 1


def check_uv_lock() -> int:
    if (REPO_ROOT / "uv.lock").exists():
        ok("uv.lock present (reproducible installs)")
        return 0
    fail("uv.lock missing")
    hint("Run: uv sync --all-groups")
    return 1


def check_dotenv() -> tuple[int, dict[str, str]]:
    """Ensures .env exists (copied from .env.example if needed) and returns its contents."""
    env_path = REPO_ROOT / ".env"
    example_path = REPO_ROOT / ".env.example"
    if not env_path.exists():
        if example_path.exists():
            fail(".env does not exist at the repo root")
            hint(f"Copy the template: cp {example_path.name} .env")
            hint("Then edit .env and set NEBIUS_KEY to your real key")
        else:
            fail(".env and .env.example both missing")
            hint(
                "The .env.example template should ship with the repo; this looks like a broken checkout"
            )
        return 1, {}
    contents = load_dotenv(env_path)
    ok(f".env present ({len(contents)} key(s) defined)")
    return 0, contents


def _is_placeholder(value: str) -> bool:
    """Rough heuristic for 'the user didn't replace the template value'."""
    if not value:
        return True
    v = value.strip().lower()
    bad = [
        "your-nebius-key",
        "your-nebius-key-here",
        "replace-me",
        "sk-replace-me",
        "xxx",
        "todo",
        "changeme",
        "your-",
    ]
    return any(tok in v for tok in bad)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


def check_llm_api_key(env: dict[str, str]) -> tuple[int, str | None, str | None]:
    """Returns (error_count, api_key, api_key_env_name)."""
    # Which env var holds the key? Config default is NEBIUS_KEY; user can override.
    key_var = env.get("SOVEREIGN_AGENT_LLM_API_KEY_ENV", "NEBIUS_KEY")
    value = env.get(key_var, "").strip()
    if not value:
        fail(f"{key_var} not set in .env or shell environment")
        hint(f"Edit .env and set {key_var}=<your real key>")
        hint("Get a free Nebius key at https://nebius.com/services/ai-studio")
        return 1, None, key_var
    if _is_placeholder(value):
        fail(f"{key_var} is still a placeholder ({_mask(value)})")
        hint("Edit .env and replace the template value with your real key")
        return 1, None, key_var
    ok(f"{key_var} set ({_mask(value)})")
    return 0, value, key_var


def check_package_imports() -> int:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import sovereign_agent  # noqa: F401

        ok(
            f"sovereign_agent imports (v{sovereign_agent.__version__}, "
            f"{len(sovereign_agent.__all__)} exports)"
        )
        return 0
    except Exception as e:  # noqa: BLE001
        fail(f"sovereign_agent fails to import: {type(e).__name__}: {e}")
        hint("Run: uv sync --all-groups")
        return 1


def check_dependencies() -> int:
    errors = 0
    deps = [
        ("openai", "openai>=1.40"),
        ("typer", "typer>=0.12"),
        ("croniter", "croniter>=2.0"),
        ("dateutil", "python-dateutil>=2.8.2"),
    ]
    for module, label in deps:
        if importlib.util.find_spec(module) is None:
            fail(f"{label} not installed")
            errors += 1
    if errors == 0:
        ok("core dependencies installed (openai, typer, croniter, dateutil)")
    else:
        hint("Run: uv sync --all-groups")
    return errors


def check_filesystem_writable(env: dict[str, str]) -> int:
    sessions_dir_str = env.get("SOVEREIGN_AGENT_SESSIONS_DIR", "sessions")
    sessions_dir = (REPO_ROOT / sessions_dir_str).resolve()
    try:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        probe = sessions_dir / ".verify_setup_probe"
        probe.write_text("ok")
        probe.unlink()
        ok(f"filesystem writable at {sessions_dir}")
        return 0
    except Exception as e:  # noqa: BLE001
        fail(f"cannot write to {sessions_dir}: {e}")
        return 1


def check_mount_allowlist() -> int:
    path = Path.home() / ".config" / "sovereign-agent" / "mount-allowlist.json"
    if path.exists():
        ok(f"mount allowlist present ({path})")
        return 0
    warn(f"mount allowlist not yet created at {path}")
    hint("Will be auto-created on first run; not an error")
    return 0  # soft


def check_chapter_drift() -> int:
    """Verify chapter solutions match the production package."""
    script = REPO_ROOT / "tools" / "verify_chapter_drift.py"
    if not script.exists():
        warn("tools/verify_chapter_drift.py missing — skipping drift check")
        return 0
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            ok("chapter solutions match production modules (no drift)")
            return 0
        fail("chapter drift detected")
        for line in result.stdout.splitlines()[-5:]:
            hint(line)
        return 1
    except Exception as e:  # noqa: BLE001
        warn(f"drift check could not run: {e}")
        return 0


def check_ruff() -> int:
    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "ruff",
                "check",
                "sovereign_agent/",
                "tests/",
                "chapters/",
                "examples/",
                "tools/",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            ok("ruff clean across package, tests, chapters, examples")
            return 0
        fail("ruff check failed")
        hint("Run: make lint   (to see details)")
        hint("Fix: make fix    (auto-fix where possible)")
        return 1
    except Exception as e:  # noqa: BLE001
        warn(f"ruff check could not run: {e}")
        return 0


async def check_llm_endpoint(api_key: str, env: dict[str, str]) -> int:
    """Real, tiny round-trip to the configured LLM endpoint."""
    base_url = env.get(
        "SOVEREIGN_AGENT_LLM_BASE_URL",
        "https://api.tokenfactory.nebius.com/v1/",
    )
    # Pick the probe model in this order:
    #   1. SOVEREIGN_AGENT_LLM_VERIFY_MODEL (explicit override for this check)
    #   2. A small cheap default per-provider (Nebius: gemma-2-2b-it)
    #   3. SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL (user's configured executor)
    #   4. Hardcoded fallback
    verify_override = env.get("SOVEREIGN_AGENT_LLM_VERIFY_MODEL")
    if verify_override:
        model = verify_override
    elif "nebius.com" in base_url:
        # Nebius Token Factory: gemma-2-2b-it is the cheapest available model.
        # Override with SOVEREIGN_AGENT_LLM_VERIFY_MODEL if it's unavailable.
        model = "google/gemma-2-2b-it"
    else:
        model = env.get("SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL", "gpt-4o-mini")

    try:
        from openai import AsyncOpenAI
    except ImportError:
        fail("openai package not installed — cannot probe LLM endpoint")
        hint("Run: uv sync --all-groups")
        return 1

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0,
            ),
            timeout=20.0,
        )
        if response.choices and response.choices[0].message is not None:
            ok(f"LLM endpoint reachable — {base_url} (model: {model})")
            return 0
        fail(f"LLM endpoint returned empty response — {base_url}")
        return 1
    except TimeoutError:
        fail(f"LLM endpoint timed out after 20s — {base_url}")
        hint("Check network connectivity; if behind a proxy, set HTTPS_PROXY")
        return 1
    except Exception as e:  # noqa: BLE001
        fail(f"LLM endpoint unreachable — {type(e).__name__}: {e}")
        if "401" in str(e) or "Unauthorized" in str(e) or "authentication" in str(e).lower():
            hint("Your API key is invalid or expired. Edit .env and update it.")
        elif "404" in str(e):
            hint(f"Probe model {model!r} not available at this endpoint.")
            hint(
                "Set SOVEREIGN_AGENT_LLM_VERIFY_MODEL=<model> in .env to override "
                "(any tiny model will do — this check just probes reachability)."
            )
        else:
            hint(f"Endpoint: {base_url}")
            hint("If using a non-default provider, verify SOVEREIGN_AGENT_LLM_BASE_URL in .env")
        return 1


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────


async def run_checks() -> int:
    print(f"\n{BOLD}{BLUE}{'=' * 58}{RESET}")
    print(f"{BOLD}{BLUE}  sovereign-agent — pre-flight verification{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 58}{RESET}")
    info("Checks everything needed to run with a real LLM.")

    errors = 0

    # ── Python ──────────────────────────────────────────────────────────
    section("Python environment")
    errors += check_python_version()

    # ── uv ──────────────────────────────────────────────────────────────
    section("uv and project state")
    errors += check_uv_installed()
    errors += check_uv_lock()

    # ── .env file ───────────────────────────────────────────────────────
    section(".env configuration")
    err, dotenv_contents = check_dotenv()
    errors += err
    merged_env = merge_env(dotenv_contents)

    # Export dotenv values into the process environment so subsequent
    # checks (LLM round-trip) see them.
    for k, v in dotenv_contents.items():
        os.environ.setdefault(k, v)

    # ── API key ─────────────────────────────────────────────────────────
    section("LLM API key")
    key_err, api_key, key_var = check_llm_api_key(merged_env)
    errors += key_err

    # ── Package + deps ──────────────────────────────────────────────────
    section("Package and dependencies")
    errors += check_package_imports()
    errors += check_dependencies()

    # ── Filesystem ──────────────────────────────────────────────────────
    section("Filesystem")
    errors += check_filesystem_writable(merged_env)
    errors += check_mount_allowlist()

    # ── Code quality ────────────────────────────────────────────────────
    section("Code quality")
    errors += check_chapter_drift()
    errors += check_ruff()

    # ── Real LLM round-trip ─────────────────────────────────────────────
    section("LLM endpoint (real round-trip)")
    if api_key:
        errors += await check_llm_endpoint(api_key, merged_env)
    else:
        fail("skipping LLM round-trip (no valid API key)")
        hint("Fix the .env issues above, then re-run: make verify")
        errors += 1

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'=' * 58}{RESET}")
    if errors == 0:
        print(f"{GREEN}{BOLD}✓  All checks passed — ready to do real work!{RESET}")
        print()
        print(f"  {MAGENTA}Try a live agent run:{RESET}")
        print(f"    {GREEN}make demo-ch5-real{RESET}           end-to-end with a real LLM")
        print(f"    {GREEN}python -m examples.research_assistant.run --real{RESET}")
        print(f"    {GREEN}python -m examples.pub_booking.run --real{RESET}")
        print()
        print(f"  {BLUE}Or spin up the daemon:{RESET}")
        print(f"    {GREEN}uv run sovereign-agent serve{RESET}")
        print()
    else:
        noun = "error" if errors == 1 else "errors"
        print(f"{RED}{BOLD}✗  {errors} {noun} — see details above{RESET}")
        print()
        print(f"  {BLUE}Common fixes:{RESET}")
        print(f"    {GREEN}cp .env.example .env{RESET}       create .env from template")
        print(
            f"    {GREEN}make install{RESET}               install the project + dev tools via uv"
        )
        print(f"    {GREEN}make fix && make format{RESET}    clean up lint issues")
        print()

    return 0 if errors == 0 else 1


def main() -> None:
    sys.exit(asyncio.run(run_checks()))


if __name__ == "__main__":
    main()
