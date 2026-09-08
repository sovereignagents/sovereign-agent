#!/usr/bin/env python3
"""Check constructed always-on chapters; --complete requires all sixteen.

This construction gate never describes planned chapters as verified. The old
curriculum remains independently gated while the new edition is being built.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from verify_book_snippets import check_chapter

ROOT = Path(__file__).resolve().parent.parent


def verify(book: Path, *, complete: bool = False) -> list[str]:
    manifest = json.loads((book / "BOOK.json").read_text())
    chapters = manifest["chapters"]
    if [c["number"] for c in chapters] != list(range(1, 17)):
        return ["manifest must retain the complete ordered sixteen-chapter contract"]
    if len({c["lessonId"] for c in chapters}) != 16:
        return ["stable lesson identities must be unique"]
    errors = []
    checked = planned = snippets = pairs = 0
    for chapter in chapters:
        if chapter["status"] == "PLANNED":
            planned += 1
            if complete:
                errors.append(f"{chapter['lessonId']}: chapter is still planned")
            continue
        if chapter["status"] not in {"DRAFT", "READY"}:
            errors.append(f"{chapter['lessonId']}: invalid status")
            continue
        if complete and chapter["status"] != "READY":
            errors.append(f"{chapter['lessonId']}: draft is not ready for publication")
        readme, checkpoint = book / chapter["path"], book / chapter["checkpoint"]
        if not readme.is_file() or not checkpoint.is_file():
            errors.append(f"{chapter['lessonId']}: manuscript or checkpoint missing")
            continue
        count, matched, failures = check_chapter(readme)
        errors.extend(failures)
        if count < 2 or matched < 2:
            errors.append(f"{chapter['lessonId']}: runnable examples and output proofs missing")
        snippets += count
        pairs += matched
        result = subprocess.run(
            [sys.executable, str(checkpoint)], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
        if result.returncode:
            errors.append(f"{chapter['lessonId']}: offline checkpoint failed: {result.stderr}")
        checked += 1
    print(
        f"ALWAYS-ON CONSTRUCTION: {checked}/16 chapters checked, {planned} planned; "
        f"{snippets} Python examples, {pairs} matching output pairs."
    )
    if not complete:
        print("This is draft verification, not whole-book publication acceptance.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--complete", action="store_true")
    args = parser.parse_args()
    errors = verify(ROOT / "book" / "always_on", complete=args.complete)
    for error in errors:
        print(error)
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
