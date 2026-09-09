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

# Chapter 3, Unit A — Build a bounded model and tool loop

**Student edition v1 · 2026-09-09 · 75–90 minutes**

Lucy asks what needs ordering. One model turn requests stock, another requests two drafts, and a final turn explains the results. You will implement the admission decision that governs every model call, connect it to a real Chapter 2 tool dispatcher, and retain the transcript for Unit B.

This unit requires the Sovereign Agent checkout and Python 3.14. It uses authored model turns and makes no network call or purchase.

## 1. Locate the cumulative code

```python tags=["setup"]
import copy
import json
import os
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path

assert sys.version_info >= (3, 14)
start = Path(os.environ.get("SOVEREIGN_AGENT_REPO", Path.cwd())).resolve()
ROOT = next(
    (
        path
        for path in (start, *start.parents)
        if (path / "book/always_on/learner/ch02.py").is_file()
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


chapter2 = run_book("book/always_on/learner/ch02.py")
ToolCall = chapter2["ToolCall"]
dispatcher = chapter2["build_tools"](chapter2["SHOP"])
print("tools", [schema["function"]["name"] for schema in dispatcher.schemas()])
```

Predict the transcript roles for stock lookup, two draft calls and a final answer. A tool observation must retain the request's call identifier.

## 2. Represent authored model turns

```python tags=["setup"]
class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelTurn:
    content: str = ""
    calls: tuple = ()

    def message(self):
        message = {"role": "assistant", "content": self.content}
        if self.calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, sort_keys=True),
                    },
                }
                for call in self.calls
            ]
        return message


class ReplayModel:
    def __init__(self, turns):
        self.turns = iter(turns)

    def complete(self, messages, tools):
        try:
            return next(self.turns)
        except StopIteration:
            raise ModelError("fixture exhausted") from None


OPENING_TURNS = [
    ModelTurn(calls=(ToolCall(id="stock-1", name="list_stock", arguments={}),)),
    ModelTurn(
        calls=(
            ToolCall(
                id="draft-v", name="draft_order", arguments={"sku": "SKU-VANILLA", "quantity": 6}
            ),
            ToolCall(
                id="draft-s", name="draft_order", arguments={"sku": "SKU-STRAWBERRY", "quantity": 4}
            ),
        )
    ),
    ModelTurn("Drafts total 2600 pence GBP. No purchase was made."),
]
```

## 3. Construct model-call admission

The starter always admits another call. Repair it so call count and configured estimated exposure both stop the loop before another provider attempt. Check the call limit first. Inputs are already validated nonnegative integers.

```python tags=["exercise", "learner-owned", "ch03-admission"]
def decide_admission(case):
    """Return CALL, MODEL_CALL_LIMIT, or MODEL_COST_LIMIT."""
    return "CALL"
```

<details><summary>Hint 1 — the decision</summary>

Admission asks whether the *next* call may begin. Used attempts never disappear because the previous provider failed.

</details>

<details><summary>Hint 2 — the evidence</summary>

Inspect `used_calls`, `max_calls`, `spent`, `next_cost`, and `budget`. Equality at the money boundary is allowed; exceeding it is not.

</details>

<details><summary>Hint 3 — the structure</summary>

Return `MODEL_CALL_LIMIT` when `used_calls >= max_calls`; otherwise return `MODEL_COST_LIMIT` when `spent + next_cost > budget`; otherwise return `CALL`.

</details>

```python tags=["assessment", "visible"]
VISIBLE_CASES = [
    ({"used_calls": 0, "max_calls": 3, "spent": 0, "next_cost": 2, "budget": 6}, "CALL"),
    (
        {"used_calls": 3, "max_calls": 3, "spent": 0, "next_cost": 0, "budget": 6},
        "MODEL_CALL_LIMIT",
    ),
    (
        {"used_calls": 1, "max_calls": 3, "spent": 5, "next_cost": 2, "budget": 6},
        "MODEL_COST_LIMIT",
    ),
    ({"used_calls": 1, "max_calls": 3, "spent": 4, "next_cost": 2, "budget": 6}, "CALL"),
]


def grade_admission(candidate, cases):
    rows = []
    for number, (case, expected) in enumerate(cases, 1):
        supplied = copy.deepcopy(case)
        try:
            observed = candidate(supplied)
        except Exception as error:
            observed = type(error).__name__
        rows.append(
            {
                "case": number,
                "expected": expected,
                "observed": observed,
                "status": "PASS" if observed == expected and supplied == case else "FAIL",
            }
        )
    return rows


visible_results = grade_admission(decide_admission, VISIBLE_CASES)
VISIBLE_PASSED = all(row["status"] == "PASS" for row in visible_results)
print(json.dumps(visible_results, indent=2))
print("VISIBLE_CONTRACT", "PASSED" if VISIBLE_PASSED else "NEEDS_WORK")
```

## 4. Connect admission to the loop

The loop calls your decision before every model attempt. It increments calls and estimated exposure before invoking the provider, preserves assistant tool requests, invokes the real Chapter 2 dispatcher, and appends identified observations.

```python tags=["integration", "learner-path"]
def run_loop(
    model, tool_dispatcher, initial_messages, admission, *, max_calls=4, call_cost=2, budget=8
):
    transcript = copy.deepcopy(initial_messages)
    model_calls = 0
    tool_calls = 0
    spent = 0
    seen = set()
    while True:
        decision = admission(
            {
                "used_calls": model_calls,
                "max_calls": max_calls,
                "spent": spent,
                "next_cost": call_cost,
                "budget": budget,
            }
        )
        if decision != "CALL":
            return {
                "status": decision,
                "messages": transcript,
                "model_calls": model_calls,
                "tool_calls": tool_calls,
                "estimated_pence": spent,
            }
        model_calls += 1
        spent += call_cost
        try:
            turn = model.complete(copy.deepcopy(transcript), tool_dispatcher.schemas())
        except ModelError:
            return {
                "status": "MODEL_FAILED",
                "messages": transcript,
                "model_calls": model_calls,
                "tool_calls": tool_calls,
                "estimated_pence": spent,
            }
        identifiers = [call.id for call in turn.calls]
        if len(identifiers) != len(set(identifiers)) or seen.intersection(identifiers):
            return {
                "status": "REPEATED_CALL_ID",
                "messages": transcript,
                "model_calls": model_calls,
                "tool_calls": tool_calls,
                "estimated_pence": spent,
            }
        seen.update(identifiers)
        transcript.append(turn.message())
        if not turn.calls:
            return {
                "status": "COMPLETED" if turn.content.strip() else "EMPTY_REPLY",
                "messages": transcript,
                "model_calls": model_calls,
                "tool_calls": tool_calls,
                "estimated_pence": spent,
                "answer": turn.content,
            }
        for call in turn.calls:
            tool_calls += 1
            result = tool_dispatcher.invoke(call)
            transcript.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, sort_keys=True),
                }
            )


INITIAL_MESSAGES = [
    {"role": "system", "content": "Use stock tools to prepare drafts. Never purchase."},
    {"role": "user", "content": "What needs ordering?"},
]
connected = None
if VISIBLE_PASSED:
    connected = run_loop(
        ReplayModel(OPENING_TURNS),
        dispatcher,
        INITIAL_MESSAGES,
        decide_admission,
    )
    print(connected["status"], connected["model_calls"], connected["tool_calls"])
    print([message["role"] for message in connected["messages"]])
    assert connected["status"] == "COMPLETED"
    assert (connected["model_calls"], connected["tool_calls"]) == (3, 3)
else:
    print("CONNECTION_NOT_READY — repair decide_admission, then run again.")
```

Trace one `tool_call_id` from assistant request to tool observation. Final prose alone does not prove the two draft tools returned valid results.

## 5. Save the bounded transcript

```python tags=["handoff"]
ARTIFACT_PATH = Path("ch03-unit-a-handoff-v1.json")
artifact_status = "NOT_WRITTEN"
if connected is not None:
    encoded = json.dumps(connected, indent=2, sort_keys=True) + "\n"
    ARTIFACT_PATH.write_text(encoded, encoding="utf-8")
    artifact_status = "WRITTEN"
    print(ARTIFACT_PATH)
else:
    print("HANDOFF_NOT_WRITTEN")
```

## Exit ticket

Explain why failed provider attempts count, why call-limit precedence matters when two limits are exhausted, and which transcript observation proves each draft tool actually ran.

```python tags=["exercise-report"]
exercise_report = {
    "unit": "ch03-a",
    "attempted": 1,
    "completed": int(VISIBLE_PASSED),
    "failed": int(not VISIBLE_PASSED),
    "skipped": 0,
    "connection": "PASSED" if connected else "NOT_READY",
    "handoff": artifact_status,
}
print("EXERCISE_REPORT=" + json.dumps(exercise_report, sort_keys=True))
```
