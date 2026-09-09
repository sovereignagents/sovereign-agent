"""The Chapter 3 holdouts reject unbounded calls and free failed attempts."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHAPTER = ROOT / "book" / "always_on" / "exercises" / "ch03"


def notebook_scope(name: str, tmp_path: Path) -> dict[str, object]:
    notebook = json.loads((CHAPTER / name).read_text(encoding="utf-8"))
    scope: dict[str, object] = {"__name__": "__exercise__", "__exercise_cwd__": str(tmp_path)}
    old_cwd = Path.cwd()
    old_root = os.environ.get("SOVEREIGN_AGENT_REPO")
    try:
        os.chdir(tmp_path)
        os.environ["SOVEREIGN_AGENT_REPO"] = str(ROOT)
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] != "code":
                continue
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)
            exec(compile(source, f"{name}:cell-{index}", "exec", dont_inherit=True), scope)
    finally:
        os.chdir(old_cwd)
        if old_root is None:
            os.environ.pop("SOVEREIGN_AGENT_REPO", None)
        else:
            os.environ["SOVEREIGN_AGENT_REPO"] = old_root
    return scope


def execute(path: Path, scope: dict[str, object]) -> None:
    previous = Path.cwd()
    try:
        os.chdir(str(scope["__exercise_cwd__"]))
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec", dont_inherit=True), scope)
    finally:
        os.chdir(previous)


def test_unit_a_official_solution_passes_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-a-bounded-loop-v1.ipynb", tmp_path)
    execute(CHAPTER / "solutions" / "unit-a-solution-v1.py", scope)
    execute(CHAPTER / "holdouts" / "unit-a-holdout-v1.py", scope)


def test_unit_a_always_call_shortcut_fails_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-a-bounded-loop-v1.ipynb", tmp_path)
    with pytest.raises(AssertionError):
        execute(CHAPTER / "holdouts" / "unit-a-holdout-v1.py", scope)


def test_unit_b_official_solution_passes_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-b-failure-accounting-v1.ipynb", tmp_path)
    execute(CHAPTER / "solutions" / "unit-b-solution-v1.py", scope)
    execute(CHAPTER / "holdouts" / "unit-b-holdout-v1.py", scope)


def test_unit_b_free_failure_shortcut_fails_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-b-failure-accounting-v1.ipynb", tmp_path)
    with pytest.raises(AssertionError):
        execute(CHAPTER / "holdouts" / "unit-b-holdout-v1.py", scope)
