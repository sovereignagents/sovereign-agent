"""Integration: run each v0.2 example end-to-end and check it exits clean.

Rationale: examples are part of the v0.2 contract. The CHANGELOG
claims each example demonstrates a specific feature, and the READMEs
reference specific output. If someone renames an internal symbol or
changes a signature and silently breaks an example, we want CI to
tell us before the students do.

These tests:

  * Invoke `python -m examples.<name>.run` as a subprocess.
  * Assert exit code is 0.
  * Grep the stdout for a short phrase the example MUST emit, so that
    "success" means "the example actually demonstrated the feature",
    not just "it didn't raise".

The grep phrases are deliberately short and unambiguous. If an
example's output is reworded, the grep is what flips red — forcing a
conscious decision: "yes, I changed the wording" vs "whoops, I broke
the demo".

We skip `--real` variants here (they need NEBIUS_KEY). Those are
verified by `make demo-ch5-real` and the homework grading harness.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_example(
    module_path: str, args: list[str] | None = None, timeout: float = 60.0
) -> subprocess.CompletedProcess:
    """Run `python -m <module_path>` from the repo root. Return the
    CompletedProcess, letting the caller inspect stdout/stderr."""
    cmd = [sys.executable, "-m", module_path] + (args or [])
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Module 1 — parallel_research
# ---------------------------------------------------------------------------


def test_example_parallel_research_runs_clean() -> None:
    """The default (parallel) run must complete cleanly and make five
    tool calls."""
    result = _run_example("examples.parallel_research.run")
    assert result.returncode == 0, (
        f"parallel_research exited {result.returncode}\n"
        f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    )
    # Five fetches in one turn.
    assert "tool calls made: 5" in result.stdout
    # Demonstrates the parallel path was actually taken.
    assert "parallelism_policy: respect_tool_flags" in result.stdout


def test_example_parallel_research_sequential_is_slower() -> None:
    """Timing proof: forcing sequential must take >= 1.0s for five
    0.3s calls. If this drops below, parallelism has silently become
    the default for policy='never'."""
    import re

    result = _run_example("examples.parallel_research.run", args=["--sequential"])
    assert result.returncode == 0
    # Extract the timing line: "Executor finished in X.XXs wall clock"
    match = re.search(r"Executor finished in ([\d.]+)s wall clock", result.stdout)
    assert match, f"no timing line found in stdout:\n{result.stdout}"
    elapsed = float(match.group(1))
    # Five 0.3s calls in sequence = 1.5s. Allow slack for slow CI.
    assert elapsed >= 1.0, (
        f"expected sequential run >=1.0s, got {elapsed:.2f}s "
        f"(parallel may have leaked into the sequential path)"
    )


# ---------------------------------------------------------------------------
# Module 2 — isolated_worker
# ---------------------------------------------------------------------------


def test_example_isolated_worker_runs_clean() -> None:
    """Must complete cleanly and report which policy it selected.

    We do NOT assert that forbidden reads were denied — the sandbox
    running these tests might not support Landlock / sandbox-exec and
    the NoOp path is the documented correct fallback. We DO assert
    the example reached the "What this proved" summary, which means
    the whole flow ran through.
    """
    result = _run_example("examples.isolated_worker.run")
    assert result.returncode == 0, (
        f"isolated_worker exited {result.returncode}\n"
        f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    )
    assert "selected policy:" in result.stdout
    assert "What this proved" in result.stdout


# ---------------------------------------------------------------------------
# Module 3 — session_resume_chain
# ---------------------------------------------------------------------------


def test_example_session_resume_chain_runs_clean() -> None:
    result = _run_example("examples.session_resume_chain.run")
    assert result.returncode == 0, (
        f"session_resume_chain exited {result.returncode}\n"
        f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    )
    # Three generations were created.
    assert "Generation 1: parent" in result.stdout
    assert "Generation 2: child" in result.stdout
    assert "Generation 3: grandchild" in result.stdout
    # Forward-only rule held.
    assert "parent state still 'completed':      OK" in result.stdout
    # Refusing a non-terminal parent fired.
    assert "refused as expected" in result.stdout


# ---------------------------------------------------------------------------
# Module 4 — classifier_rule
# ---------------------------------------------------------------------------


def test_example_classifier_rule_gets_all_six_correct() -> None:
    """The test fixtures are deterministic — 6/6 must pass every time."""
    result = _run_example("examples.classifier_rule.run")
    assert result.returncode == 0, (
        f"classifier_rule exited {result.returncode}\n"
        f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    )
    assert "Correct: 6/6" in result.stdout


# ---------------------------------------------------------------------------
# Module 5 — hitl_deposit
# ---------------------------------------------------------------------------


def test_example_hitl_deposit_runs_both_paths() -> None:
    """Both grant and deny scenarios must complete, and the permanent
    audit log must exist."""
    result = _run_example("examples.hitl_deposit.run")
    assert result.returncode == 0, (
        f"hitl_deposit exited {result.returncode}\n"
        f"stderr:\n{result.stderr}\nstdout:\n{result.stdout}"
    )
    assert "Scenario A: approval GRANTED" in result.stdout
    assert "Scenario B: approval DENIED" in result.stdout
    # LLM adapted on denial.
    assert "propose an alternative" in result.stdout.lower()
    # Audit log was written.
    assert "logs/approvals/" in result.stdout
    assert ".decision.json" in result.stdout


# ---------------------------------------------------------------------------
# Original v0.1.0 examples should still pass — protection against
# accidentally regressing the older examples while shipping v0.2.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "examples.research_assistant.run",
        "examples.code_reviewer.run",
        "examples.pub_booking.run",
    ],
)
def test_v01_examples_still_run_clean(module: str) -> None:
    result = _run_example(module)
    assert result.returncode == 0, (
        f"{module} regressed — exit {result.returncode}\n"
        f"stderr:\n{result.stderr}\nstdout:\n{result.stdout[-1000:]}"
    )
