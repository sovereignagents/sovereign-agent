"""Executed chapter companions distinguish supplied evidence from student work."""

import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path

import pytest

BOOK = Path(__file__).resolve().parents[1] / "book/always_on"
EDUCATOR = BOOK / "educator"
MANIFEST = json.loads((EDUCATOR / "curriculum-v1.json").read_text())


def test_every_remaining_chapter_has_a_companion_and_valid_runtime_anchor():
    assert [row["number"] for row in MANIFEST["chapters"]] == list(range(2, 17))
    chapters = json.loads((BOOK / "BOOK.json").read_text())["chapters"]
    for row in MANIFEST["chapters"]:
        document = json.loads((EDUCATOR / row["notebook"]).read_text())
        anchor = document["metadata"]["sovereign_agent"]
        assert row["checkpoint"] == chapters[row["number"] - 1]["checkpoint"]
        assert (
            anchor["checkpoint_sha256"]
            == hashlib.sha256((BOOK / row["checkpoint"]).read_bytes()).hexdigest()
        )
        assert (EDUCATOR / row["guide"]).is_file()
        ids = [cell["id"] for cell in document["cells"]]
        assert len(ids) == len(set(ids))
        assert document["nbformat"] == 4 and document["nbformat_minor"] == 5
        assert all(cell.get("outputs", []) == [] for cell in document["cells"])


@pytest.fixture(params=MANIFEST["chapters"], ids=lambda row: f"ch{row['number']:02d}")
def lesson(request, monkeypatch):
    monkeypatch.setenv("SOVEREIGN_AGENT_REPO", str(BOOK.parents[1]))
    monkeypatch.setenv("CLASS_API_KEY", "synthetic-notebook-secret")
    path = EDUCATOR / request.param["notebook"]
    notebook = json.loads(path.read_text())
    scope = {}
    for _ in range(2):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            for index, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] != "code":
                    continue
                source = "".join(cell["source"])
                ast.parse(source)
                exec(compile(source, f"{path}:cell{index}", "exec"), scope)
        assert "synthetic-notebook-secret" not in output.getvalue()
        assert "REFERENCE_CHECKPOINT_PASSED" in output.getvalue()
        assert all(row["status"] == "NOT_SUBMITTED" for row in scope["submission_results"])
        assert scope["transfer_results"] == []
        assert all(row["status"] == "PASS" for row in scope["worked_results"])
        assert any(row["status"] == "FAILED" for row in scope["shortcut_results"])
        assert scope["reference_run"].returncode == 0
        assert "CLASS_API_KEY" not in scope["reference_environment"]
    return scope


def test_replay_and_student_grader_refuse_shortcuts_and_mutation(lesson):
    grade = lesson["grade"]
    # Deliberately different output types and a mutation with otherwise correct output.
    assert grade(lambda case: True, [({}, 1)])[0]["status"] == "FAILED"
    assert grade(lambda case: {1}, [({}, 1)])[0]["status"] == "FAILED"

    def mutates(case):
        case["changed"] = True
        return 1

    assert grade(mutates, [({}, 1)])[0]["status"] == "FAILED"
    assert grade(lambda case: 1, [({}, 1)])[0]["status"] == "PASS"
    with pytest.raises(NotImplementedError):
        lesson["decide"]({})  # Worked solution did not overwrite the student's function.


def test_plain_python_runner_records_unsubmitted_work_and_preserves_evidence(tmp_path):
    import subprocess
    import sys

    output = tmp_path / "class.json"
    command = [
        sys.executable,
        str(EDUCATOR / "run_lesson_v1.py"),
        "--chapter",
        "2",
        "--output",
        str(output),
    ]
    subprocess.run(command, cwd=BOOK.parents[1], capture_output=True, check=True, timeout=30)
    before = output.read_bytes()
    report = json.loads(before)
    assert all(row["status"] == "NOT_SUBMITTED" for row in report["student_submission"])
    assert report["student_transfer"] == []
    assert len(report["outputs"]) == 7
    second = subprocess.run(command, cwd=BOOK.parents[1], capture_output=True, timeout=30)
    assert second.returncode != 0 and b"FileExistsError" in second.stderr
    assert output.read_bytes() == before
