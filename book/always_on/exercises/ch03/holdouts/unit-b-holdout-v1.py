"""Instructor-held checks appended after a submitted Chapter 3 Unit B notebook."""

# ruff: noqa: F821 - executed inside the submitted notebook namespace

import json

hidden_lab = RuntimeLab(ROOT, 3)
try:
    original_probe = hidden_lab.probe.read_text(encoding="utf-8")
    assert original_probe.count("estimated_call_pence=5") == 1
    hidden_lab.probe.write_text(
        original_probe.replace("estimated_call_pence=5", "estimated_call_pence=7"),
        encoding="utf-8",
    )
    hidden_lab.break_source()
    hidden_lab.repair(repair_fragment())
    hidden_result = hidden_lab.run(
        "HIDDEN_REPAIR",
        expected={"estimated_pence": 7, "model_calls": 1, "stop_reason": "MODEL_FAILED"},
    )
finally:
    hidden_lab.close()
assert hidden_result["status"] == "PASS"
print("HOLDOUT_RESULT=" + json.dumps({"unit": "ch03-b", "status": "PASSED"}, sort_keys=True))
