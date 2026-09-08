"""Copy real teaching/runtime code, retain observations, and grade a repair separately.

This is classroom infrastructure, not a security sandbox for arbitrary Python.
Run only reviewed local exercises. A child interpreter is not OS containment.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = json.loads((HERE / "runtime-experiments-v1.json").read_text())["experiments"]


class RuntimeLab:
    def __init__(self, root, chapter):
        self.spec = next(row for row in CATALOG if row["chapter"] == chapter)
        self.source = Path(root) / self.spec["path"]
        self.original = self.source.read_text()
        if hashlib.sha256(self.original.encode()).hexdigest() != self.spec["sha256"]:
            raise ValueError("Runtime source differs from the pinned classroom experiment")
        self.temporary = tempfile.TemporaryDirectory(prefix=f"lucy-ch{chapter:02d}-copy-")
        self.root = Path(self.temporary.name)
        for relative in (
            "src",
            "book/always_on/checkpoints",
            "book/always_on/learner",
            "book/always_on/skills",
        ):
            shutil.copytree(
                Path(root) / relative,
                self.root / relative,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        self.target = self.root / self.spec["path"]
        self.probe = self.root / "classroom_probe.py"
        self.probe.write_text(self.spec["probe"])
        self.records = []

    def source_excerpt(self):
        lines = self.target.read_text().splitlines()
        start = max(0, self.spec["line"] - 3)
        return "\n".join(f"{i + 1}: {lines[i]}" for i in range(start, min(len(lines), start + 9)))

    def break_source(self):
        text = self.target.read_text()
        before, after = self.spec["before"], self.spec["after"]
        if text.count(before) != 1 or text != self.original:
            raise ValueError("Break step requires the original copied source; start a fresh lab")
        self.target.write_text(text.replace(before, after, 1))

    def repair(self, replacement):
        """Student supplies the complete replacement for the marked mutation fragment."""
        text = self.target.read_text()
        anchor = self.spec["after"]
        if not isinstance(replacement, str) or not replacement.strip() or text.count(anchor) != 1:
            raise ValueError("Provide one nonempty replacement for the unique broken fragment")
        self.target.write_text(text.replace(anchor, replacement, 1))

    def run(self, phase, *, expected=None):
        environment = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL"}
        }
        environment["PYTHONPATH"] = str(self.root / "src")
        # Never reuse bytecode between same-size source mutations within one second.
        for cached in self.root.rglob("__pycache__"):
            shutil.rmtree(cached)
        command = [sys.executable, "-B", str(self.probe)]
        process = subprocess.Popen(
            command,
            cwd=self.root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name == "posix",
        )
        try:
            stdout, stderr = process.communicate(timeout=60)
            code = process.returncode
        except subprocess.TimeoutExpired:
            # The reviewed supplier child inherits this group. Kill the group,
            # not only its parent, so a timed-out trial cannot leave a supplier.
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            stdout, stderr = process.communicate(timeout=5)
            code = None
        print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
        observation = None
        try:
            observation = json.loads(stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            pass
        passed = (
            code == 0
            and isinstance(observation, dict)
            and expected is not None
            and all(observation.get(key) == value for key, value in expected.items())
        )
        record = {
            "phase": phase,
            "command": command,
            "returncode": code,
            "stdout": stdout,
            "stderr": stderr,
            "observation": observation,
            "expected": expected,
            "status": "PASS" if passed else "FAILED",
            "source_path": self.spec["path"],
            "source_line": self.spec["line"],
            "source_sha256": hashlib.sha256(self.target.read_bytes()).hexdigest(),
            "probe_sha256": hashlib.sha256(self.probe.read_bytes()).hexdigest(),
        }
        self.records.append(record)
        if self.source.read_text() != self.original:
            raise RuntimeError("Original repository source changed during copied-code experiment")
        return record

    def trace(self, submission, record):
        if not submission:
            return {"status": "NOT_SUBMITTED"}
        observation = record.get("observation") or {}
        valid = (
            submission.get("source_path") == self.spec["path"]
            and submission.get("source_line") == self.spec["line"]
            and submission.get("observation_key") in observation
            and submission.get("observed_value")
            == observation.get(submission.get("observation_key"))
            and bool(submission.get("explanation", "").strip())
        )
        return {
            "status": "STRUCTURE_VALID_TEACHER_REVIEW_REQUIRED" if valid else "FAILED",
            "submission": submission,
            "scope": "Teacher must assess the causal explanation; matching fields is insufficient.",
        }

    def close(self):
        self.temporary.cleanup()
