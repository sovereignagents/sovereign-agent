"""Instructor-held checks appended after a submitted Chapter 3 Unit A notebook."""

# ruff: noqa: F821 - executed inside the submitted notebook namespace

import json

assert (
    decide_admission({"used_calls": 4, "max_calls": 4, "spent": 9, "next_cost": 3, "budget": 10})
    == "MODEL_CALL_LIMIT"
)
assert (
    decide_admission({"used_calls": 2, "max_calls": 4, "spent": 9, "next_cost": 3, "budget": 10})
    == "MODEL_COST_LIMIT"
)
assert (
    decide_admission({"used_calls": 2, "max_calls": 4, "spent": 7, "next_cost": 3, "budget": 10})
    == "CALL"
)


class HiddenFailedModel:
    def complete(self, messages, tools):
        raise ModelError("hidden fixture failure")


failed_hidden = run_loop(
    HiddenFailedModel(),
    dispatcher,
    INITIAL_MESSAGES,
    decide_admission,
    max_calls=5,
    call_cost=7,
    budget=20,
)
assert failed_hidden["status"] == "MODEL_FAILED"
assert failed_hidden["model_calls"] == 1
assert failed_hidden["estimated_pence"] == 7
handoff_connected = run_loop(
    ReplayModel(OPENING_TURNS), dispatcher, INITIAL_MESSAGES, decide_admission
)
assert handoff_connected["status"] == "COMPLETED"
Path("ch03-unit-a-handoff-v1.json").write_text(
    json.dumps(handoff_connected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print("HOLDOUT_RESULT=" + json.dumps({"unit": "ch03-a", "status": "PASSED"}, sort_keys=True))
