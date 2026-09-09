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

# Chapter 1, Unit A — Build a grounded morning brief

**Student edition v1 · 2026-09-09 · 75–90 minutes**

Lucy wants a useful stock brief before opening her ice cream shop. You will build the boundary that accepts a completed model response, connect it to the shop snapshot, and save evidence for Unit B.

This notebook runs offline on Python 3.11 or newer with the standard library. It makes no purchase and needs no credential. A live model call is an optional comparison after the offline work; it is not required for the exercise.

Use the same loop throughout: **predict → construct → connect → challenge → explain**. Write each prediction before running the case. A wrong prediction is useful when you revise the explanation from evidence.

## 1. Predict from Lucy's records

Before running the cell, calculate the replenishment quantity for every product. What happens when stock equals its reorder point?

```python tags=["setup"]
import copy
import hashlib
import json
import sys
from pathlib import Path

assert sys.version_info >= (3, 11)

SHOP = {
    "customer": "Lucy",
    "currency": "GBP",
    "products": [
        {"sku": "SKU-VANILLA", "name": "Vanilla", "on_hand": 2, "reorder_point": 8},
        {"sku": "SKU-CHOCOLATE", "name": "Chocolate", "on_hand": 12, "reorder_point": 6},
        {"sku": "SKU-STRAWBERRY", "name": "Strawberry", "on_hand": 1, "reorder_point": 5},
    ],
}


def stock_facts(shop):
    return [
        {
            "sku": product["sku"],
            "name": product["name"],
            "on_hand": product["on_hand"],
            "needed": max(0, product["reorder_point"] - product["on_hand"]),
        }
        for product in sorted(shop["products"], key=lambda item: item["sku"])
    ]


FACTS = stock_facts(SHOP)
print(json.dumps(FACTS, indent=2))
assert [(row["sku"], row["needed"]) for row in FACTS] == [
    ("SKU-CHOCOLATE", 0),
    ("SKU-STRAWBERRY", 4),
    ("SKU-VANILLA", 6),
]
```

The calculation is deterministic business logic. A model can explain the facts, but it does not decide that `8 - 2` is six.

## 2. Inspect the request bytes

Predict where the current stock appears, which text is guidance, and what prevents a purchase.

```python tags=["setup"]
def messages(shop):
    return [
        {
            "role": "system",
            "content": (
                "Write Lucy a short morning stock brief. Use only the supplied shop facts. "
                "Do not purchase anything or claim that an order exists."
            ),
        },
        {"role": "user", "content": json.dumps(shop, sort_keys=True)},
    ]


def payload(shop, model="fixture-model"):
    return {
        "model": model,
        "messages": messages(shop),
        "stream": False,
        "temperature": 0,
        "max_tokens": 256,
    }


REQUEST = payload(SHOP)
print(json.dumps(REQUEST, indent=2))
assert json.loads(REQUEST["messages"][1]["content"]) == SHOP
```

The system prompt asks for bounded behavior. The program has no purchasing function, which is the stronger fact. Temperature zero does not prove that a live provider will return identical text.

## 3. Construct the response boundary

The starter below is a plausible first attempt. It accepts the happy-path fixture, but it also trusts missing fields and the first choice it sees. Repair `read_brief` so it accepts exactly one completed assistant text response and refuses tool calls, refusals, empty text, wrong roles, incomplete generation, and malformed containers.

```python tags=["exercise", "learner-owned", "unit-a-boundary"]
def read_brief(document):
    """Return one completed assistant text response, or raise ValueError."""
    # STARTER: make this boundary explicit before relying on it.
    return document["choices"][0]["message"]["content"]
```

<details><summary>Hint 1 — the decision</summary>

Check the envelope from the outside in. Refuse a shape you cannot interpret instead of guessing a default.

</details>

<details><summary>Hint 2 — the evidence</summary>

Inspect `choices`, `finish_reason`, `message.role`, `tool_calls`, `refusal`, and `content`. A completed string is a narrower claim than a correct business answer.

</details>

<details><summary>Hint 3 — the structure</summary>

Require a dictionary, then a list of length one, then a dictionary choice with `finish_reason == "stop"`, then an assistant message with no tool call/refusal, then nonempty text.

</details>

## 4. Run the visible contract

Predict which cases the starter mishandles. The grader catches candidate exceptions as observations so the notebook itself can finish. Passing visible cases is necessary; it is not the hidden transfer verdict.

```python tags=["assessment", "visible"]
GOOD_RESPONSE = {
    "choices": [
        {
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "Vanilla needs 6 tubs; strawberry needs 4. No order was placed.",
            },
        }
    ]
}

VISIBLE_CASES = [
    (GOOD_RESPONSE, "ACCEPT"),
    ({"choices": []}, "REFUSE"),
    (
        {
            "choices": [
                {"finish_reason": "length", "message": {"role": "assistant", "content": "Van"}}
            ]
        },
        "REFUSE",
    ),
    (
        {"choices": [{"finish_reason": "stop", "message": {"role": "user", "content": "six"}}]},
        "REFUSE",
    ),
    (
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"name": "buy"}],
                    },
                }
            ]
        },
        "REFUSE",
    ),
]


def grade_reader(candidate, cases):
    rows = []
    for number, (document, expected) in enumerate(cases, 1):
        supplied = copy.deepcopy(document)
        try:
            result = candidate(supplied)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            observed = "REFUSE"
            detail = type(error).__name__
        except Exception as error:
            observed = "ERROR"
            detail = type(error).__name__
        else:
            observed = "ACCEPT"
            detail = result if isinstance(result, str) else type(result).__name__
        rows.append(
            {
                "case": number,
                "expected": expected,
                "observed": observed,
                "status": "PASS" if observed == expected and supplied == document else "FAIL",
                "detail": detail,
            }
        )
    return rows


visible_results = grade_reader(read_brief, VISIBLE_CASES)
print(json.dumps(visible_results, indent=2))
VISIBLE_PASSED = all(row["status"] == "PASS" for row in visible_results)
print("VISIBLE_CONTRACT", "PASSED" if VISIBLE_PASSED else "NEEDS_WORK")
```

## 5. Connect your boundary to Lucy's brief

This is the cumulative behavior: `morning_brief` calls your `read_brief`, binds its result to the exact shop snapshot, and keeps deterministic stock facts beside model prose. It cannot silently use a supplied reference implementation.

```python tags=["integration", "learner-path"]
def snapshot_id(shop):
    return hashlib.sha256(json.dumps(shop, sort_keys=True).encode()).hexdigest()


def morning_brief(shop, response, reader):
    text = reader(response)
    return {
        "shop_snapshot": snapshot_id(shop),
        "facts": stock_facts(shop),
        "model_text": text,
        "claim": "DRAFT_FOR_REVIEW",
    }


connected = None
if VISIBLE_PASSED:
    connected = morning_brief(SHOP, GOOD_RESPONSE, read_brief)
    assert connected["facts"] == FACTS
    assert connected["claim"] == "DRAFT_FOR_REVIEW"
    print(json.dumps(connected, indent=2))
else:
    print("CONNECTION_NOT_READY — repair read_brief, then run this cell again.")
```

Trace the displayed `model_text` backward. Which function admitted it? Which fields were calculated without the model? This trace is part of the exercise evidence.

## 6. Challenge a fluent lie

Predict whether a valid response envelope can still carry a false business claim.

```python tags=["challenge"]
LYING_RESPONSE = copy.deepcopy(GOOD_RESPONSE)
LYING_RESPONSE["choices"][0]["message"]["content"] = (
    "I bought six vanilla tubs and the supplier accepted the order."
)

if VISIBLE_PASSED:
    challenged = morning_brief(SHOP, LYING_RESPONSE, read_brief)
    print(challenged["claim"], challenged["model_text"])
    assert challenged["claim"] == "DRAFT_FOR_REVIEW"
else:
    print("CHALLENGE_WAITING_FOR_BOUNDARY")
```

A passing envelope check proves response shape. It does not prove the supplier accepted anything. Chapter 9 will require durable intent and supplier evidence for that stronger claim.

## 7. Save the handoff for Unit B

After the visible contract passes, save the connected artifact. Unit B will refuse an absent or mismatched handoff instead of silently recreating it.

```python tags=["handoff"]
ARTIFACT_PATH = Path("ch01-unit-a-handoff-v1.json")
artifact_status = "NOT_WRITTEN"
if connected is not None:
    encoded = json.dumps(connected, indent=2, sort_keys=True) + "\n"
    ARTIFACT_PATH.write_text(encoded, encoding="utf-8")
    artifact_status = "WRITTEN"
    print(ARTIFACT_PATH, hashlib.sha256(encoded.encode()).hexdigest())
else:
    print("HANDOFF_NOT_WRITTEN — the learner boundary has not passed.")
```

## Exit ticket

Submit your prediction notes, repaired function, visible-case result, data-flow trace, and handoff artifact. In four sentences answer:

1. What does the system prompt change?
2. What does `read_brief` enforce?
3. Which facts remain unverified after `read_brief` succeeds?
4. What observation would falsify your claim that your function is connected?

```python tags=["exercise-report"]
exercise_report = {
    "unit": "ch01-a",
    "attempted": 1,
    "completed": int(VISIBLE_PASSED),
    "failed": int(not VISIBLE_PASSED),
    "skipped": 0,
    "connection": "PASSED" if connected is not None else "NOT_READY",
    "handoff": artifact_status,
}
print("EXERCISE_REPORT=" + json.dumps(exercise_report, sort_keys=True))
```

