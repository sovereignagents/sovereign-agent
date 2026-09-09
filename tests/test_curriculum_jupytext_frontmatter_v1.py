"""Jupytext exercise metadata is distinct from forbidden site frontmatter."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_curriculum.py"
SPEC = importlib.util.spec_from_file_location("verify_curriculum_frontmatter", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def check(tmp_path: Path, relative: str, header: str) -> list[str]:
    book = tmp_path / "book"
    target = book / relative
    target.parent.mkdir(parents=True)
    target.write_text(header + "\n# Lesson\n", encoding="utf-8")
    module.BOOK = book
    module.REPO_ROOT = tmp_path
    return module.check_no_frontmatter()


def test_jupytext_metadata_is_allowed_only_for_exercises(tmp_path: Path) -> None:
    header = """---
jupyter:
  jupytext:
    text_representation:
      extension: .md
  kernelspec:
    name: python3
---
"""
    assert check(tmp_path, "always_on/exercises/ch01/unit.md", header) == []
    assert check(tmp_path, "always_on/ch01/README.md", header)


def test_site_frontmatter_remains_forbidden_inside_exercises(tmp_path: Path) -> None:
    header = """---
title: A page
slug: a-page
---
"""
    assert check(tmp_path, "always_on/exercises/ch01/unit.md", header)
