#!/usr/bin/env python3
"""Verify distributed exercise bytes without executing student solutions."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "book" / "always_on" / "exercises" / "release-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def committed_bytes(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, check=False
    )
    require(result.returncode == 0, f"source commit does not contain {path}")
    return result.stdout


def verify(release_path: Path = RELEASE) -> None:
    release = json.loads(release_path.read_text(encoding="utf-8"))
    require(release["schemaVersion"] == 1, "unknown release schema")
    require(re.fullmatch(r"[0-9a-f]{40}", release["sourceCommit"]) is not None, "bad commit")
    lock = ROOT / release["environmentLock"]
    require(lock.is_file() and sha256(lock) == release["environmentLockSha256"], "lock drift")
    student_files = release["studentFiles"]
    paths = [item["path"] for item in student_files]
    require(len(paths) == len(set(paths)), "duplicate student file")
    require(not any("solution" in path or "holdout" in path for path in paths), "answer leak")
    for item in student_files:
        path = item["path"]
        target = ROOT / path
        require(target.is_file() and target.resolve().is_relative_to(ROOT), f"missing file: {path}")
        require(sha256(target) == item["sha256"], f"student file drift: {path}")
        committed = hashlib.sha256(committed_bytes(release["sourceCommit"], path)).hexdigest()
        require(committed == item["sha256"], f"source commit drift: {path}")
    require({row["id"] for row in release["units"]} == {"ch01-a", "ch01-b"}, "unit set drift")
    for row in release["units"]:
        source = ROOT / row["canonicalSource"]
        notebook_path = ROOT / row["notebook"]
        require(sha256(source) == row["canonicalSha256"], f"source drift: {row['id']}")
        require(sha256(notebook_path) == row["notebookSha256"], f"notebook drift: {row['id']}")
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        stable = [
            {
                "cell_type": cell["cell_type"],
                "source": (
                    "".join(cell.get("source", []))
                    if isinstance(cell.get("source", ""), list)
                    else cell.get("source", "")
                ),
                "tags": cell.get("metadata", {}).get("tags", []),
            }
            for cell in notebook["cells"]
        ]
        semantic = hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        require(row["semanticDigestVersion"] == 1, "unknown semantic digest")
        require(semantic == row["semanticSha256"], f"semantic drift: {row['id']}")
        execution = row["execution"]
        require(execution["failed"] == 0 and execution["skipped"] == 0, "execution incomplete")
        require(execution["attempted"] == execution["completed"], "cell accounting mismatch")
        require(row["freshKernel"] is True, "fresh-kernel evidence missing")
        evidence = row["instructorEvidence"]
        for kind in ("solution", "holdout"):
            evidence_path = ROOT / evidence[kind]
            require(sha256(evidence_path) == evidence[f"{kind}Sha256"], f"{kind} drift")
        require(evidence["holdoutResult"]["status"] == "PASSED", "holdout failed")


if __name__ == "__main__":
    verify()
    print("EXERCISE RELEASE: exact bytes, semantic cells, execution and holdouts verified.")
    print("Student starters running is not evidence of learner mastery.")
