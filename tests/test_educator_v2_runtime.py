"""Real copied-code failures, adversarial assessments and retained learner evidence."""

import contextlib
import copy
import io
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EDUCATOR = ROOT / "book/always_on/educator"
MANIFEST = json.loads((EDUCATOR / "curriculum-v2.json").read_text())


def notebook(chapter):
    name = next(row["notebook"] for row in MANIFEST["chapters"] if row["number"] == chapter)
    return json.loads((EDUCATOR / name).read_text())


def definitions(chapter):
    scope = {"copy": copy, "json": json}
    for cell in notebook(chapter)["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] != "code":
            continue
        if source.startswith("def grade"):
            exec(source, scope)
        if source.startswith("CASES ="):
            exec(source.split("submission_results =")[0], scope)
        if source.startswith("def worked_decide"):
            exec(source.split("worked_results =")[0], scope)
    return scope


@pytest.mark.parametrize("chapter", range(2, 17))
def test_real_source_fault_and_repair_preserve_original(chapter):
    support = runpy.run_path(str(EDUCATOR / "runtime_labs_v1.py"))
    lab = support["RuntimeLab"](ROOT, chapter)
    original = lab.source.read_bytes()
    try:
        baseline = lab.run("baseline", expected=lab.spec["expected_baseline"])
        lab.break_source()
        broken = lab.run("broken", expected=lab.spec["expected_broken"])
        assert baseline["status"] == broken["status"] == "PASS"
        assert baseline["observation"] != broken["observation"]
        lab.repair(lab.spec["before"])
        repaired = lab.run("student_repair", expected=lab.spec["expected_baseline"])
        assert repaired["status"] == "PASS"
        assert repaired["source_sha256"] == baseline["source_sha256"]
        assert lab.source.read_bytes() == original
        assert lab.trace({}, broken)["status"] == "NOT_SUBMITTED"
        assert "PRIVATE_TEST_TOKEN" not in baseline["stdout"]
    finally:
        copied_root = lab.root
        lab.close()
    assert not copied_root.exists()


@pytest.mark.parametrize("chapter", range(2, 17))
def test_assessment_diagnostics_remain_serializable_and_preserve_mutation(chapter):
    scope = definitions(chapter)
    grade = scope["grade"]
    for value in ({1}, b"bytes", object(), float("nan")):
        result = grade(lambda case, value=value: value, [({}, 1)])
        assert result[0]["status"] == "FAILED"
        assert result[0]["reason"] == "unsupported_return_type"
        json.dumps(result, allow_nan=False)
    result = grade(lambda case: case.update(changed=True) or 1, [({}, 1)])
    assert result[0]["mutated"] and result[0]["reason"] == "input_mutated"
    assert result[0]["expected"] == result[0]["observed"]
    assert (
        scope["assessment_status"]([{"status": "PASS"}, {"status": "NOT_SUBMITTED"}])["status"]
        == "PARTIAL"
    )
    assert all(r["status"] == "PASS" for r in grade(scope["worked_decide"], scope["CASES"]))


@pytest.mark.parametrize(
    "chapter,old,new",
    [
        (2, "type(quantity) is not int", "not isinstance(quantity, int)"),
        (2, "type(quantity) is not int", "not isinstance(quantity, (int, float))"),
        (
            4,
            "if used + size > case['budget']:\n            continue",
            "if used + size > case['budget']:\n            break",
        ),
        (4, "used += size", "used = size"),
        (4, "len(row['value'])", "len(row['value'].encode())"),
        (5, "return sorted(", "return list("),
        (6, "not message['private']", "False"),
        (6, "message['is_bot']", "False"),
        (
            6,
            "key = [message['account'], message['update_id']]",
            "key = (message['account'], message['update_id'])",
        ),
        (10, "('work', 'owner', 'generation', 'epoch')", "('owner', 'generation', 'epoch')"),
        (10, "('work', 'owner', 'generation', 'epoch')", "('work', 'owner', 'epoch')"),
        (10, "('work', 'owner', 'generation', 'epoch')", "('work', 'generation', 'epoch')"),
        (10, "('work', 'owner', 'generation', 'epoch')", "('work', 'owner', 'generation')"),
        (10, "current['status'] == 'RUNNING'", "True"),
        (11, "set(case['registered'])", "set(case['requested'])"),
        (12, "row['total_pence']", "1500"),
        (13, "!= case['current_generation']", "< case['current_generation']"),
        (14, "1 <= guests <= 200", "1 < guests < 200"),
        (14, "type(guests) is not int", "not isinstance(guests, (int, float))"),
        (15, "value < 0", "value < -1"),
        (
            15,
            "set(observed) != set(case['required_skus'])",
            "len(observed) != len(case['required_skus'])",
        ),
        (16, "local == supplier", "sum(local.values()) == sum(supplier.values())"),
        (16, "or len(supplier) != len(case['supplier'])", ""),
    ],
)
def test_named_wrong_implementations_are_rejected(chapter, old, new):
    scope = definitions(chapter)
    source = next(
        "".join(c["source"]).split("worked_results =")[0]
        for c in notebook(chapter)["cells"]
        if "".join(c["source"]).startswith("def worked_decide")
    )
    # Formatting normalizes quotes; compare normalized literals without changing whitespace.
    old, new = old.replace("'", '"'), new.replace("'", '"')
    source = source.replace("'", '"')
    assert old in source
    exec(source.replace(old, new), scope)
    assert any(
        r["status"] == "FAILED" for r in scope["grade"](scope["worked_decide"], scope["CASES"])
    )


def test_runner_retains_unsupported_student_results_and_reaches_worked_repair(tmp_path):
    doc = notebook(2)
    for cell in doc["cells"]:
        source = "".join(cell["source"])
        if source.startswith("def grade"):
            source = source.replace(
                "raise NotImplementedError("
                "'Write your function before consulting the worked solution.')",
                "return {1}",
            )
            source = source.replace(
                "raise NotImplementedError("
                '"Write your function before consulting the worked solution.")',
                "return {1}",
            )
            cell["source"] = source.splitlines(keepends=True)
    path = tmp_path / "student.ipynb"
    path.write_text(json.dumps(doc))
    output = tmp_path / "evidence.json"
    command = [
        sys.executable,
        str(EDUCATOR / "run_lesson_v2.py"),
        "--chapter",
        "2",
        "--notebook",
        str(path),
        "--output",
        str(output),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text())
    assert report["submission_summary"]["status"] == "FAILED"
    assert all(r["reason"] == "unsupported_return_type" for r in report["student_submission"])
    assert report["runtime"]["worked_repair"]["status"] == "PASS"
    assert report["runtime"]["student_repair"]["status"] == "NOT_SUBMITTED"
    before = output.read_bytes()
    assert subprocess.run(command, cwd=ROOT, capture_output=True, timeout=10).returncode != 0
    assert output.read_bytes() == before


def test_chapter3_student_model_changes_actual_loop_observations(monkeypatch):
    monkeypatch.chdir(ROOT)
    scope = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for cell in notebook(3)["cells"]:
            source = "".join(cell["source"])
            if cell["cell_type"] != "code":
                continue
            exec(source, scope)
            if "def integrate_student" in source:
                break
    try:
        limits = scope["Limits"](model_calls=2, estimated_call_pence=5)
        replay = scope["integrate_student"](scope["ReplayModel"](scope["opening_turns"]()), limits)
        assert (
            replay["stop_reason"],
            replay["model_calls"],
            replay["tool_calls"],
            replay["estimated_pence"],
        ) == ("MODEL_CALL_LIMIT", 2, 3, 10)
        assert len(replay["tool_evidence"]) == 3

        class Failed:
            def complete(self, *args, **kwargs):
                raise scope["ModelError"]("fixture")

        failed = scope["integrate_student"](Failed(), limits)
        assert (
            failed["stop_reason"],
            failed["model_calls"],
            failed["tool_calls"],
            failed["estimated_pence"],
        ) == ("MODEL_FAILED", 1, 0, 5)
        assert failed["tool_evidence"] == []
    finally:
        scope["lab"].close()
