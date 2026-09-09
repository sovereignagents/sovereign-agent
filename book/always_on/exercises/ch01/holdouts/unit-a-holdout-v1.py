"""Instructor-held checks appended after a submitted Unit A notebook."""

# ruff: noqa: F821 - executed inside the submitted notebook namespace

import copy
import json


def expect_refusal(document):
    try:
        read_brief(copy.deepcopy(document))
    except ValueError:
        return
    raise AssertionError("hidden case was accepted")


expect_refusal(None)
expect_refusal({"choices": [{"finish_reason": "stop", "message": []}]})
expect_refusal(
    {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "   ", "refusal": None},
            }
        ]
    }
)
expect_refusal(
    {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "text", "refusal": "blocked"},
            }
        ]
    }
)

hidden_shop = copy.deepcopy(SHOP)
hidden_shop["products"] = [
    {"sku": "SKU-MINT", "name": "Mint", "on_hand": 7, "reorder_point": 7},
    *reversed(hidden_shop["products"]),
]
hidden_response = copy.deepcopy(GOOD_RESPONSE)
hidden_response["choices"][0]["message"]["content"] = "A completed draft for review."
hidden_connected = morning_brief(hidden_shop, hidden_response, read_brief)
assert hidden_connected["shop_snapshot"] == snapshot_id(hidden_shop)
assert next(row for row in hidden_connected["facts"] if row["sku"] == "SKU-MINT")["needed"] == 0
assert hidden_connected["claim"] == "DRAFT_FOR_REVIEW"
print("HOLDOUT_RESULT=" + json.dumps({"unit": "ch01-a", "status": "PASSED"}, sort_keys=True))
