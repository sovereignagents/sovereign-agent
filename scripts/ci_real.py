"""Run every ``-real`` scenario against a live LLM, collect pass/fail, and
print the tail of any failing log inline so you can copy-paste it.

Why this file
=============
The earlier ``ci-real`` target was a gnarly multi-line shell loop inside the
Makefile. Two real problems with that:

1. Logs lived in ``_transient/ci-real/`` inside the repo. That's fine for a
   throwaway directory, but it pollutes the repo and — more importantly —
   ``_transient`` is idiosyncratic (it's our convention). The XDG Base
   Directory spec has an answer for this: cache artifacts go under
   ``$XDG_CACHE_HOME`` (``~/Library/Caches`` on macOS, ``~/.cache`` on
   Linux, ``%LOCALAPPDATA%`` on Windows). That's where pytest's
   ``.pytest_cache`` would live if it followed XDG strictly; where pip,
   uv, npm, cargo, and huggingface_hub actually do store their caches.

2. When a scenario failed, the harness said "see /path/to/file.log" and
   you had to ``cat`` it separately. That's an extra step, and for remote
   pair-debugging (like our session here) the student has to copy the
   log file out and paste it back. Printing the last ~40 lines of the
   failing log INLINE solves both problems: the signal is on screen, it
   copy-pastes as one block, and the file is still there for deeper dives.

3. Nebius (and real LLM providers in general) have flake modes — things
   like the "Already borrowed" 400 error you just hit, which is a
   provider-side Rust borrow-check race, not our bug. A single run
   shouldn't fail if the second attempt would succeed. We retry ONCE on
   transient errors (400 with specific patterns, 429, 500, 502, 503, 504,
   network errors); a second failure is reported as a real failure.

Called from the Makefile as ``python scripts/ci_real.py``. Exit code is
the count of genuine failures (capped at 125 so shells don't interpret
it as a signal number), which means ``make ci-real`` fails with a
non-zero exit when anything genuinely broke.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ─────────────────────────────────────────────────────────────────────
# Scenario catalog
# ─────────────────────────────────────────────────────────────────────

# The Makefile targets we cycle through. Ordered roughly cheapest-first
# so a consistent failure fails the cheap ones early.
SCENARIOS: list[str] = [
    "example-isolated-worker-real",
    "example-session-resume-chain-real",
    "example-parallel-research-real",
    "example-reviewer-real",
    "example-research-real",
    "example-pub-booking-real",
    "example-pub-booking-oversize-real",
    "example-classifier-rule-real",
    "example-hitl-deposit-real-approve",
]


# Rough cost + duration estimates per scenario, collected from actual runs
# against the default (MiniMax-M2.5 planner + Qwen3-235B-Instruct executor)
# on Nebius. These are ballpark values — real spend varies 2-3x based on
# the model's verbosity and retry count. They exist so `ci-real-estimate`
# can give students a "what's this going to cost me?" preview without
# surprising them. Keep conservative (slightly high) — worse to under-warn
# than over-warn about spend.
#
# If the Nebius pricing or defaults change materially, this dict is the
# single source of truth to update.
SCENARIO_ESTIMATES: dict[str, dict] = {
    "example-isolated-worker-real": {"cost_usd": 0.005, "seconds": 10},
    "example-session-resume-chain-real": {"cost_usd": 0.005, "seconds": 10},
    "example-parallel-research-real": {"cost_usd": 0.010, "seconds": 15},
    "example-reviewer-real": {"cost_usd": 0.015, "seconds": 20},
    "example-research-real": {"cost_usd": 0.020, "seconds": 25},
    "example-pub-booking-real": {"cost_usd": 0.020, "seconds": 25},
    "example-pub-booking-oversize-real": {"cost_usd": 0.020, "seconds": 25},
    "example-classifier-rule-real": {"cost_usd": 0.015, "seconds": 20},
    "example-hitl-deposit-real-approve": {"cost_usd": 0.025, "seconds": 30},
}


# ─────────────────────────────────────────────────────────────────────
# Where logs live — follow XDG Base Directory spec
# ─────────────────────────────────────────────────────────────────────


def _cache_root() -> Path:
    """Return the ROOT cache directory where all ci-real runs live.

    Individual runs live in timestamped subdirs under this. The ``latest``
    symlink (or ``latest-run.txt`` pointer on platforms without symlink
    support) always points at the most recent.

    Linux / generic Unix:
        $XDG_CACHE_HOME/sovereign-agent/ci-real/
        (default $XDG_CACHE_HOME = ~/.cache)

    macOS:
        ~/Library/Caches/sovereign-agent/ci-real/

    Windows:
        %LOCALAPPDATA%\\sovereign-agent\\Cache\\ci-real\\
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")

    path = base / "sovereign-agent" / "ci-real"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _new_run_dir() -> Path:
    """Create a new timestamped subdir for the current run.

    Format: YYYYMMDD-HHMMSS (sorts chronologically, no collisions at 1s).
    If two runs collide (rare), append a short random suffix.
    """
    import datetime
    import secrets

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = _cache_root() / stamp
    if run_dir.exists():
        run_dir = _cache_root() / f"{stamp}-{secrets.token_hex(2)}"
    run_dir.mkdir(parents=True, exist_ok=False)

    # Update the `latest` pointer. Try symlink first; fall back to a text
    # file on Windows / filesystems that don't support symlinks.
    latest = _cache_root() / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(run_dir.name, target_is_directory=True)
    except (OSError, NotImplementedError):
        (_cache_root() / "latest-run.txt").write_text(run_dir.name + "\n")

    return run_dir


def _latest_run_dir() -> Path | None:
    """Resolve the most recent run directory, if any."""
    root = _cache_root()
    # Try the symlink first
    latest_symlink = root / "latest"
    if latest_symlink.is_symlink():
        target = root / latest_symlink.readlink()
        if target.is_dir():
            return target
    # Fall back to the text pointer
    pointer = root / "latest-run.txt"
    if pointer.exists():
        name = pointer.read_text().strip()
        target = root / name
        if target.is_dir():
            return target
    # Last resort: scan for timestamped dirs and pick the newest
    candidates = sorted(
        (p for p in root.iterdir() if p.is_dir() and p.name != "latest"),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _all_run_dirs() -> list[Path]:
    """Every run directory under the cache root, newest first."""
    root = _cache_root()
    if not root.exists():
        return []
    return sorted(
        (p for p in root.iterdir() if p.is_dir() and p.name != "latest"),
        reverse=True,
    )


# Back-compat alias: earlier code + the Makefile imports _cache_dir. Keep
# it pointing at the root so `make ci-real-logs`-style inline Python calls
# still resolve the right place.
def _cache_dir() -> Path:
    return _cache_root()


# ─────────────────────────────────────────────────────────────────────
# Flake detection — these errors get a single retry
# ─────────────────────────────────────────────────────────────────────

# Substrings that indicate the error is transient (provider-side, network,
# rate limit). If any of these appear in the failure output, we retry once
# with a short backoff. Real logic errors shouldn't match these — they'd
# say "ModuleNotFoundError", "AssertionError", "KeyError", etc.
TRANSIENT_MARKERS: tuple[str, ...] = (
    "Already borrowed",  # Nebius Rust borrow-check flake (2026-04-23 trace)
    "rate limit",
    "429",
    "500 Internal",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway",
    "Connection reset",
    "Connection refused",
    "ConnectionError",
    "ReadTimeout",
    "ReadTimeoutError",
    "TimeoutError",
    "temporary failure",
    "Temporary failure",
)


def _looks_transient(output: str) -> bool:
    return any(marker in output for marker in TRANSIENT_MARKERS)


# ─────────────────────────────────────────────────────────────────────
# ANSI colors (auto-disable for non-TTY)
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
    def dim(cls, s: str) -> str:
        return cls._wrap("2", s)

    @classmethod
    def bold(cls, s: str) -> str:
        return cls._wrap("1", s)


# ─────────────────────────────────────────────────────────────────────
# Run one scenario
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Result:
    target: str
    status: Literal["ok", "fail", "flake-then-ok", "flake-then-fail"]
    log_path: Path
    attempts: int = 1
    output: str = ""
    tail: list[str] = field(default_factory=list)


def _tail(text: str, n: int = 40) -> list[str]:
    lines = text.splitlines()
    return lines[-n:] if len(lines) > n else lines


def _run_once(target: str) -> tuple[int, str]:
    """Run `make -s <target>` and capture combined output. Returns (rc, output)."""
    proc = subprocess.run(
        ["make", "-s", target],
        capture_output=True,
        text=True,
        timeout=300,  # 5 minutes per scenario, generous
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def run_scenario(target: str, log_dir: Path) -> Result:
    """Run one scenario. Retries once on transient errors."""
    log_path = log_dir / f"{target}.log"

    # First attempt
    rc, output = _run_once(target)
    log_path.write_text(output)

    if rc == 0:
        return Result(target=target, status="ok", log_path=log_path, output=output)

    # Failure — check if it's a flake worth retrying
    if _looks_transient(output):
        # Back off briefly so we don't hammer the provider
        import time

        time.sleep(3)
        rc2, output2 = _run_once(target)
        # Append retry output to the same log file
        combined = (
            output
            + "\n\n"
            + "=" * 72
            + "\nRETRY #2 (first attempt looked like a provider-side flake)\n"
            + "=" * 72
            + "\n"
            + output2
        )
        log_path.write_text(combined)
        if rc2 == 0:
            return Result(
                target=target,
                status="flake-then-ok",
                log_path=log_path,
                attempts=2,
                output=combined,
                tail=_tail(output2, 10),  # short tail of successful retry
            )
        else:
            return Result(
                target=target,
                status="flake-then-fail",
                log_path=log_path,
                attempts=2,
                output=combined,
                tail=_tail(output2, 40),  # longer tail for diagnosis
            )

    # Hard failure (not a flake)
    return Result(
        target=target,
        status="fail",
        log_path=log_path,
        attempts=1,
        output=output,
        tail=_tail(output, 40),
    )


# ─────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────


def _print_result(result: Result) -> None:
    target = result.target
    if result.status == "ok":
        print(f"  {_C.green('✓')} {target:<42} {_C.green('ok')}")
    elif result.status == "flake-then-ok":
        print(f"  {_C.yellow('~')} {target:<42} {_C.yellow('ok')} {_C.dim('(flake, retried)')}")
    elif result.status == "flake-then-fail":
        print(
            f"  {_C.red('✗')} {target:<42} "
            f"{_C.red('FAIL')} {_C.dim('(retried once, still failing)')}"
        )
    else:  # fail
        print(f"  {_C.red('✗')} {target:<42} {_C.red('FAIL')}")


def _print_failure_inline(result: Result) -> None:
    """Print the tail of a failing log so the student can copy-paste it."""
    print()
    print("─" * 72)
    print(_C.red("✗") + " " + _C.bold(result.target) + f"  (attempts: {result.attempts})")
    print(_C.dim(f"full log: {result.log_path}"))
    print("─" * 72)
    print(_C.dim(f"tail of output (last {len(result.tail)} lines):"))
    print()
    for line in result.tail:
        print(f"  {line}")
    print()


def _write_summary(results: list[Result], run_dir: Path) -> Path:
    """Write both a human-readable summary.txt and a machine-readable
    summary.json. The JSON is used by history/retry/summary subcommands."""
    import json

    summary_path = run_dir / "summary.txt"
    with summary_path.open("w") as f:
        for r in results:
            label = r.status.upper().replace("-", " ")
            f.write(f"{label:<18} {r.target}\n")

    # Machine-readable form for the history/retry-failed subcommands
    json_path = run_dir / "summary.json"
    data = {
        "run_at": run_dir.name,  # timestamp-based dir name
        "total": len(results),
        "passed": sum(1 for r in results if r.status in ("ok", "flake-then-ok")),
        "failed": sum(1 for r in results if r.status in ("fail", "flake-then-fail")),
        "flakes_recovered": sum(1 for r in results if r.status == "flake-then-ok"),
        "scenarios": [
            {
                "target": r.target,
                "status": r.status,
                "attempts": r.attempts,
                "log": r.log_path.name,
            }
            for r in results
        ],
    }
    with json_path.open("w") as f:
        json.dump(data, f, indent=2)

    return summary_path


# ─────────────────────────────────────────────────────────────────────
# Main — dispatches to a subcommand, defaults to `run`
# ─────────────────────────────────────────────────────────────────────


def cmd_run(only: list[str] | None = None) -> int:
    """Run every (or selected) -real scenarios. This is the default."""
    run_dir = _new_run_dir()
    scenarios = only or SCENARIOS
    root = _cache_root()

    print()
    print(_C.yellow("▶") + " " + _C.bold("Running -real scenarios against live LLM"))
    print(_C.dim("─" * 68))
    est_cost, est_secs = _estimate(scenarios)
    print(_C.dim(f"estimated: ~${est_cost:.2f} over ~{est_secs}s · logs: {run_dir}"))
    print()

    results: list[Result] = []
    for target in scenarios:
        print(f"  {_C.dim('▸')} {target:<42} {_C.dim('running...')}", end="", flush=True)
        result = run_scenario(target, run_dir)
        print("\r", end="")
        _print_result(result)
        results.append(result)

    summary_path = _write_summary(results, run_dir)

    failures = [r for r in results if r.status in ("fail", "flake-then-fail")]
    for result in failures:
        _print_failure_inline(result)

    print()
    print(_C.dim("─" * 68))
    total = len(results)
    failed = len(failures)
    flakes_recovered = sum(1 for r in results if r.status == "flake-then-ok")

    if failed == 0:
        msg = _C.green("✓") + " " + _C.bold("ci-real green")
        if flakes_recovered:
            msg += _C.dim(f"  ({flakes_recovered} transient flake(s) recovered on retry)")
        print(msg)
    else:
        print(_C.red("✗") + " " + _C.bold(f"ci-real: {failed}/{total} scenario(s) failed"))
        print(_C.dim(f"  logs:    {run_dir}/*.log"))
        print(_C.dim(f"  summary: {summary_path}"))
        print()
        print(_C.bold("Copy-paste the block(s) above into your next message."))

    print(_C.dim(f"  history: {root} (see: make ci-real-history)"))

    return min(failed, 125)


def _estimate(scenarios: list[str]) -> tuple[float, int]:
    """Return (total_cost_usd, total_seconds) for a list of scenarios."""
    cost = sum(SCENARIO_ESTIMATES.get(s, {}).get("cost_usd", 0.02) for s in scenarios)
    secs = sum(SCENARIO_ESTIMATES.get(s, {}).get("seconds", 20) for s in scenarios)
    return cost, secs


def cmd_estimate() -> int:
    """Preview cost and time for a full ci-real run."""
    print()
    print(_C.yellow("▶") + " " + _C.bold("Cost estimate for ci-real"))
    print(_C.dim("─" * 68))
    rows = []
    for s in SCENARIOS:
        est = SCENARIO_ESTIMATES.get(s, {"cost_usd": 0.02, "seconds": 20})
        rows.append((s, est["cost_usd"], est["seconds"]))
    for name, c, sec in rows:
        print(f"  {_C.dim('▸')} {name:<42} ${c:>6.3f}  ~{sec:>3d}s")
    total_cost, total_secs = _estimate(SCENARIOS)
    print(_C.dim("─" * 68))
    print(
        f"  {_C.bold('total:')}                                         "
        f"{_C.bold(f'${total_cost:.2f}')}  ~{total_secs}s "
        f"{_C.dim('(' + str(len(SCENARIOS)) + ' scenarios)')}"
    )
    print()
    print(
        _C.dim(
            "  These are ballpark estimates from the current default models "
            "(MiniMax-M2.5 + Qwen3-235B-Instruct)."
        )
    )
    print(_C.dim("  Actual spend varies 2-3x depending on model verbosity and retries."))
    return 0


def cmd_summary() -> int:
    """One-line verdict from the most recent run."""
    import json

    latest = _latest_run_dir()
    if latest is None:
        print(_C.yellow("⚠") + " no ci-real runs yet (try: make ci-real)")
        return 0

    json_path = latest / "summary.json"
    if not json_path.exists():
        # Old-format run from before json was added
        print(_C.yellow("⚠") + f" {latest.name}: no summary.json (older format)")
        return 0

    data = json.loads(json_path.read_text())
    mark_passed = _C.green(f"✓ {data['passed']} passed")
    mark_failed_color = _C.green if data["failed"] == 0 else _C.red
    mark_failed = mark_failed_color(f"✗ {data['failed']} failed")
    flakes = (
        f"  ({data['flakes_recovered']} flake(s) recovered)" if data["flakes_recovered"] else ""
    )
    print(f"{mark_passed}  {mark_failed}{_C.dim(flakes)}  {_C.dim('at ' + data['run_at'])}")
    if data["failed"]:
        print(_C.dim(f"  details: {latest}"))
    return 0


def cmd_history(limit: int = 10) -> int:
    """List recent ci-real runs with their verdicts."""
    import json

    runs = _all_run_dirs()
    if not runs:
        print(_C.yellow("⚠") + " no ci-real runs yet")
        return 0

    print()
    print(
        _C.yellow("▶")
        + " "
        + _C.bold("ci-real history")
        + _C.dim(f"  (last {min(limit, len(runs))} of {len(runs)})")
    )
    print(_C.dim("─" * 68))
    for run in runs[:limit]:
        json_path = run / "summary.json"
        if not json_path.exists():
            print(f"  {_C.dim('▸')} {run.name}  {_C.dim('(no summary.json)')}")
            continue
        data = json.loads(json_path.read_text())
        passed = data["passed"]
        failed = data["failed"]
        total = data["total"]
        mark = _C.green("✓") if failed == 0 else _C.red("✗")
        status = (
            _C.green(f"{passed}/{total} passed")
            if failed == 0
            else _C.red(f"{failed}/{total} failed")
        )
        print(f"  {mark} {run.name}  {status}")
    root = _cache_root()
    print(_C.dim("─" * 68))
    print(_C.dim(f"  inspect a run: ls {root}/<run>/"))
    return 0


def cmd_retry_failed() -> int:
    """Rerun only the scenarios that failed in the most recent run."""
    import json

    latest = _latest_run_dir()
    if latest is None:
        print(_C.red("✗") + " no prior ci-real run to retry")
        return 1

    json_path = latest / "summary.json"
    if not json_path.exists():
        print(_C.red("✗") + f" {latest.name} has no summary.json; can't determine what failed")
        return 1

    data = json.loads(json_path.read_text())
    failed_targets = [
        s["target"] for s in data["scenarios"] if s["status"] in ("fail", "flake-then-fail")
    ]
    if not failed_targets:
        print(_C.green("✓") + f" nothing to retry: {latest.name} was fully green")
        return 0

    print()
    print(
        _C.yellow("▶")
        + " "
        + _C.bold(f"Retrying {len(failed_targets)} failed scenario(s) from {latest.name}")
    )
    print(_C.dim("─" * 68))
    for t in failed_targets:
        print(f"  {_C.dim('▸')} {t}")
    print()
    return cmd_run(only=failed_targets)


def cmd_clean(keep: int = 5) -> int:
    """Retention: keep the N most recent runs, delete older ones."""
    runs = _all_run_dirs()
    if len(runs) <= keep:
        print(_C.green("✓") + f" {len(runs)} run(s); nothing to clean (keeping {keep} most recent)")
        return 0

    to_delete = runs[keep:]
    print()
    print(
        _C.yellow("▶")
        + " "
        + _C.bold(f"Cleaning {len(to_delete)} old run(s); keeping {keep} most recent")
    )
    print(_C.dim("─" * 68))
    import shutil

    for run in to_delete:
        shutil.rmtree(run)
        print(f"  {_C.dim('rm')} {run.name}")
    print(_C.green("✓") + f" kept {keep}, removed {len(to_delete)}")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="ci-real runner + log/history management",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="run",
        choices=["run", "estimate", "summary", "history", "retry-failed", "clean"],
        help="which action to perform (default: run)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=5,
        help="for `clean`: how many recent runs to keep (default 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="for `history`: how many runs to list (default 10)",
    )
    args = parser.parse_args()

    if args.subcommand == "run":
        return cmd_run()
    elif args.subcommand == "estimate":
        return cmd_estimate()
    elif args.subcommand == "summary":
        return cmd_summary()
    elif args.subcommand == "history":
        return cmd_history(limit=args.limit)
    elif args.subcommand == "retry-failed":
        return cmd_retry_failed()
    elif args.subcommand == "clean":
        return cmd_clean(keep=args.keep)
    else:
        parser.error(f"unknown subcommand: {args.subcommand}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
