#!/usr/bin/env python3
"""Build and execute the first source-owned exercise release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parent.parent
EXERCISES = ROOT / "book" / "always_on" / "exercises"


@dataclass(frozen=True)
class Unit:
    identity: str
    source: Path
    notebook: Path
    solution: Path
    holdout: Path


UNITS = (
    Unit(
        "ch01-a",
        EXERCISES / "ch01" / "unit-a-first-grounded-brief-v1.md",
        EXERCISES / "ch01" / "unit-a-first-grounded-brief-v1.ipynb",
        EXERCISES / "ch01" / "solutions" / "unit-a-solution-v1.py",
        EXERCISES / "ch01" / "holdouts" / "unit-a-holdout-v1.py",
    ),
    Unit(
        "ch01-b",
        EXERCISES / "ch01" / "unit-b-prompt-and-harness-v1.md",
        EXERCISES / "ch01" / "unit-b-prompt-and-harness-v1.ipynb",
        EXERCISES / "ch01" / "solutions" / "unit-b-solution-v1.py",
        EXERCISES / "ch01" / "holdouts" / "unit-b-holdout-v1.py",
    ),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def semantic_digest(notebook: dict) -> str:
    stable = [
        {
            "cell_type": cell["cell_type"],
            "source": cell.get("source", ""),
            "tags": cell.get("metadata", {}).get("tags", []),
        }
        for cell in notebook["cells"]
    ]
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def outputs_bytes(notebook: dict) -> int:
    total = 0
    for cell in notebook["cells"]:
        for output in cell.get("outputs", []):
            total += len(json.dumps(output, sort_keys=True, default=str).encode())
    return total


def marker(notebook: dict, prefix: str) -> dict:
    found = []
    for cell in notebook["cells"]:
        for output in cell.get("outputs", []):
            text = output.get("text", "")
            if isinstance(text, list):
                text = "".join(text)
            for line in str(text).splitlines():
                if line.startswith(prefix):
                    found.append(json.loads(line.removeprefix(prefix)))
    if len(found) != 1:
        raise RuntimeError(f"expected one {prefix!r} marker, found {len(found)}")
    return found[0]


def execute(notebook: dict, cwd: Path) -> dict:
    executed = NotebookClient(
        nbformat.from_dict(notebook),
        timeout=30,
        kernel_name="python3",
        allow_errors=False,
        record_timing=False,
    ).execute(cwd=str(cwd))
    size = outputs_bytes(executed)
    if size > 1_000_000:
        raise RuntimeError(f"captured notebook output exceeds post-run limit: {size} bytes")
    return executed


def convert(unit: Unit, jupytext: str) -> dict:
    subprocess.run(
        [jupytext, "--to", "ipynb", "--output", str(unit.notebook), str(unit.source)],
        cwd=ROOT,
        check=True,
    )
    notebook = nbformat.read(unit.notebook, as_version=4)
    for index, cell in enumerate(notebook.cells):
        identity = f"{unit.identity}:{index}:{cell.cell_type}:{cell.source}".encode()
        cell.id = hashlib.sha256(identity).hexdigest()[:16]
        if cell.cell_type == "code":
            cell.execution_count = None
            cell.outputs = []
    nbformat.write(notebook, unit.notebook)
    return notebook


def verify_solution(unit: Unit, notebook: dict, cwd: Path) -> dict:
    assessment = nbformat.from_dict(notebook)
    assessment.cells.append(nbformat.v4.new_code_cell(unit.solution.read_text(encoding="utf-8")))
    assessment.cells.append(nbformat.v4.new_code_cell(unit.holdout.read_text(encoding="utf-8")))
    executed = execute(assessment, cwd)
    return marker(executed, "HOLDOUT_RESULT=")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=EXERCISES / "release-v1.json")
    args = parser.parse_args()
    jupytext = shutil.which("jupytext")
    if not jupytext:
        raise RuntimeError("jupytext CLI unavailable; run with the locked authoring group")
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    lock_hash = sha256(ROOT / "uv.lock")
    rows = []
    with tempfile.TemporaryDirectory(prefix="sovereign-agent-exercises-") as temporary:
        run_root = Path(temporary)
        for unit in UNITS:
            notebook = convert(unit, jupytext)
            unit_root = run_root / unit.identity
            unit_root.mkdir()
            executed = execute(notebook, unit_root)
            report = marker(executed, "EXERCISE_REPORT=")
            solution = verify_solution(unit, notebook, unit_root)
            rows.append(
                {
                    "id": unit.identity,
                    "canonicalSource": relative(unit.source),
                    "canonicalSha256": sha256(unit.source),
                    "notebook": relative(unit.notebook),
                    "notebookSha256": sha256(unit.notebook),
                    "semanticDigestVersion": 1,
                    "semanticSha256": semantic_digest(notebook),
                    "freshKernel": True,
                    "execution": {
                        "attempted": sum(c["cell_type"] == "code" for c in executed["cells"]),
                        "completed": sum(c["cell_type"] == "code" for c in executed["cells"]),
                        "failed": 0,
                        "skipped": 0,
                        "capturedOutputBytes": outputs_bytes(executed),
                        "exerciseReport": report,
                    },
                    "instructorEvidence": {
                        "solution": relative(unit.solution),
                        "solutionSha256": sha256(unit.solution),
                        "holdout": relative(unit.holdout),
                        "holdoutSha256": sha256(unit.holdout),
                        "holdoutResult": solution,
                    },
                }
            )
    release = {
        "schemaVersion": 1,
        "status": "DRAFT",
        "sourceCommit": source_commit,
        "environmentLock": "uv.lock",
        "environmentLockSha256": lock_hash,
        "studentFiles": [
            {"path": path, "sha256": sha256(ROOT / path)}
            for path in (
                "book/always_on/exercises/README.md",
                "book/always_on/exercises/ch01/unit-a-first-grounded-brief-v1.md",
                "book/always_on/exercises/ch01/unit-a-first-grounded-brief-v1.ipynb",
                "book/always_on/exercises/ch01/unit-b-prompt-and-harness-v1.md",
                "book/always_on/exercises/ch01/unit-b-prompt-and-harness-v1.ipynb",
            )
        ],
        "units": rows,
        "executionLimitations": [
            "trusted local course code",
            "per-cell timeout is not a whole-run deadline",
            "captured output limit is checked after execution",
            "process, network, and descendant isolation unavailable",
        ],
    }
    args.output.write_text(json.dumps(release, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"built {len(rows)} units -> {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
