"""The Chapter 1 holdouts reject plausible visible-case shortcuts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHAPTER = ROOT / "book" / "always_on" / "exercises" / "ch01"


def notebook_scope(name: str, tmp_path: Path) -> dict[str, object]:
    notebook = json.loads((CHAPTER / name).read_text(encoding="utf-8"))
    scope: dict[str, object] = {"__name__": "__exercise__"}
    old = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] != "code":
                continue
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)
            exec(compile(source, f"{name}:cell-{index}", "exec"), scope)
    finally:
        os.chdir(old)
    return scope


def execute(path: Path, scope: dict[str, object]) -> None:
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), scope)


def test_unit_a_official_solution_passes_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-a-first-grounded-brief-v1.ipynb", tmp_path)
    execute(CHAPTER / "solutions" / "unit-a-solution-v1.py", scope)
    execute(CHAPTER / "holdouts" / "unit-a-holdout-v1.py", scope)


def test_unit_a_visible_fixture_lookup_fails_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-a-first-grounded-brief-v1.ipynb", tmp_path)
    exec(
        "def read_brief(document):\n"
        "    if document == GOOD_RESPONSE:\n"
        "        return document['choices'][0]['message']['content']\n"
        "    raise ValueError('not the visible fixture')\n",
        scope,
    )
    with pytest.raises(ValueError, match="visible fixture"):
        execute(CHAPTER / "holdouts" / "unit-a-holdout-v1.py", scope)


def test_unit_b_official_solution_passes_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-b-prompt-and-harness-v1.ipynb", tmp_path)
    execute(CHAPTER / "solutions" / "unit-b-solution-v1.py", scope)
    execute(CHAPTER / "holdouts" / "unit-b-holdout-v1.py", scope)


def test_unit_b_visible_product_lookup_fails_holdout(tmp_path: Path) -> None:
    scope = notebook_scope("unit-b-prompt-and-harness-v1.ipynb", tmp_path)
    exec(
        "def validate_draft(proposal, shop, prices, estimate_limit=3000):\n"
        "    if proposal != GOOD_PROPOSAL:\n"
        "        raise ValueError('not the visible products')\n"
        "    return {'drafts': proposal['drafts'], 'estimated_pence': 2600}\n",
        scope,
    )
    with pytest.raises(ValueError, match="visible products"):
        execute(CHAPTER / "holdouts" / "unit-b-holdout-v1.py", scope)
