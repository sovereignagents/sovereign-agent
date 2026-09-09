---
jupyter:
  jupytext:
    text_representation:
      extension: .md
      format_name: markdown
      format_version: '1.3'
  kernelspec:
    display_name: Python 3
    language: python
    name: python3
---

# Chapter 3, Unit B — Repair failed-call accounting

**Student edition v1 · 2026-09-09 · 60–75 minutes**

The bounded loop works when the provider cooperates. Now a provider fails on its first admitted call. You will break a temporary copy of the actual Chapter 3 learner implementation, repair the accounting line, and test a second failure shape.

This unit runs reviewed local course code in bounded subprocesses. It is not a security sandbox.

## 1. Verify the Unit A handoff and load the real experiment

```python tags=["setup", "handoff-consumer"]
import json
import os
import runpy
import sys
from pathlib import Path

assert sys.version_info >= (3, 14)
start = Path(os.environ.get("SOVEREIGN_AGENT_REPO", Path.cwd())).resolve()
ROOT = next(
    (
        path
        for path in (start, *start.parents)
        if (path / "book/always_on/learner/ch03.py").is_file()
    ),
    None,
)
if ROOT is None:
    raise RuntimeError("Set SOVEREIGN_AGENT_REPO to the Sovereign Agent checkout.")


def run_book(relative):
    previous = Path.cwd()
    try:
        os.chdir(ROOT)
        return runpy.run_path(str(ROOT / relative))
    finally:
        os.chdir(previous)


HANDOFF_PATH = Path("ch03-unit-a-handoff-v1.json")
handoff_status = "MISSING"
if HANDOFF_PATH.is_file():
    handoff = json.loads(HANDOFF_PATH.read_text(encoding="utf-8"))
    handoff_status = "VERIFIED" if handoff.get("status") == "COMPLETED" else "INVALID"
print("UNIT_A_HANDOFF", handoff_status)

support = runpy.run_path(str(ROOT / "book/always_on/educator/runtime_labs_v1.py"))
RuntimeLab = support["RuntimeLab"]
```

Predict the baseline observation. If the provider fails after admission, should the local result record zero or one model attempt? Should the configured five-pence exposure disappear?

## 2. Break the real source copy

```python tags=["failure-experiment"]
lab = RuntimeLab(ROOT, 3)
baseline = lab.run("BASELINE", expected=lab.spec["expected_baseline"])
lab.break_source()
broken = lab.run("BROKEN", expected=lab.spec["expected_broken"])
print(json.dumps({"baseline": baseline["observation"], "broken": broken["observation"]}, indent=2))
assert baseline["status"] == "PASS"
assert broken["status"] == "PASS"
```

The broken source changes `exposure += limits.estimated_call_pence` to `exposure += 0`. The model-call counter still advances. This separates attempted calls from configured cost exposure and makes repeated failures look free.

## 3. Construct the repair

Return the complete replacement for the one marked broken fragment. The starter repeats the broken code and therefore fails the baseline contract.

```python tags=["exercise", "learner-owned", "ch03-repair"]
def repair_fragment():
    return "exposure += 0"
```

<details><summary>Hint 1 — the decision</summary>

Repair the accounting statement; do not change the provider fixture, expected result, or call counter.

</details>

<details><summary>Hint 2 — the evidence</summary>

Compare `baseline["observation"]` with `broken["observation"]`. Only `estimated_pence` should change.

</details>

<details><summary>Hint 3 — the structure</summary>

The replacement adds `limits.estimated_call_pence` to `exposure` before `model.complete` begins.

</details>

```python tags=["integration", "learner-path"]
lab.repair(repair_fragment())
student_repair = lab.run("STUDENT_REPAIR", expected=lab.spec["expected_baseline"])
REPAIR_PASSED = student_repair["status"] == "PASS"
print(json.dumps(student_repair["observation"], indent=2))
print("REAL_SOURCE_REPAIR", "PASSED" if REPAIR_PASSED else "NEEDS_WORK")
lab.close()
```

The original checkout is never edited. `RuntimeLab` fingerprints it, copies the real source and probe, executes the copy, and checks the original again after every run.

## 4. Challenge two termination paths

Use the real Chapter 3 loop. First, repeat a tool-call identifier. Then fail on the first provider call. Predict the result status and counters before running.

```python tags=["challenge"]
chapter3 = run_book("book/always_on/learner/ch03.py")
ToolCall = chapter3["ToolCall"]
ModelTurn = chapter3["ModelTurn"]
ReplayModel = chapter3["ReplayModel"]
Limits = chapter3["Limits"]
run_loop = chapter3["run_loop"]
dispatcher = chapter3["shop_tools"]["build_tools"](chapter3["shop_tools"]["SHOP"])

repeated = run_loop(
    ReplayModel(
        [
            ModelTurn(calls=(ToolCall(id="same", name="list_stock", arguments={}),)),
            ModelTurn(calls=(ToolCall(id="same", name="list_stock", arguments={}),)),
        ]
    ),
    dispatcher,
    chapter3["messages"],
)


class FailedModel:
    def complete(self, *args, **kwargs):
        raise chapter3["ModelError"]("fixture failure")


failed = run_loop(
    FailedModel(),
    dispatcher,
    chapter3["messages"],
    limits=Limits(estimated_call_pence=5, model_budget_pence=10),
)
print("repeated", repeated.status, repeated.model_calls, repeated.tool_calls)
print("failed", failed.status, failed.model_calls, failed.estimated_cost_pence)
assert repeated.status == "REPEATED_CALL_ID"
assert (failed.status, failed.model_calls, failed.estimated_cost_pence) == ("MODEL_FAILED", 1, 5)
```

## 5. Transfer the repair

Change the copied probe so the failed model is invoked twice through two separate `run_loop` calls and retain both observations. Explain why each run begins a new local budget and why a durable organization later needs budget reservations outside this in-memory loop.

The instructor holdout also applies your fragment to a fresh copy and uses an unseen configured estimate. A repair that prints five, changes expected data, or special-cases the visible observation will fail.

## Exit ticket

Submit the baseline, broken and repaired observations; your fragment; the repeated-ID and provider-failure results; and a causal explanation naming what would falsify it.

```python tags=["exercise-report"]
exercise_report = {
    "unit": "ch03-b",
    "attempted": 1,
    "completed": int(REPAIR_PASSED),
    "failed": int(not REPAIR_PASSED),
    "skipped": 0,
    "connection": "PASSED" if REPAIR_PASSED else "NOT_READY",
    "handoff": handoff_status,
}
print("EXERCISE_REPORT=" + json.dumps(exercise_report, sort_keys=True))
```
