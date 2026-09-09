"""Instructor-held checks appended after a submitted Unit B notebook."""

# ruff: noqa: F821 - executed inside the submitted notebook namespace

import copy
import json

expanded = copy.deepcopy(SHOP)
expanded["products"] = [
    {"sku": "SKU-LIME", "name": "Lime", "on_hand": 0, "reorder_point": 4},
    *reversed(expanded["products"]),
]
prices = {**PRICES, "SKU-LIME": 225}
proposal = {
    "action": "draft_order",
    "drafts": [
        {"sku": "SKU-LIME", "quantity": 4},
        {"sku": "SKU-STRAWBERRY", "quantity": 4},
        {"sku": "SKU-VANILLA", "quantity": 6},
    ],
    "explanation": "Derived from the supplied records.",
}
accepted = validate_draft(copy.deepcopy(proposal), expanded, prices, estimate_limit=4000)
assert accepted["estimated_pence"] == 3500
assert [row["sku"] for row in accepted["drafts"]] == [
    "SKU-LIME",
    "SKU-STRAWBERRY",
    "SKU-VANILLA",
]

wrong = copy.deepcopy(proposal)
wrong["drafts"][0]["quantity"] = 3
try:
    validate_draft(wrong, expanded, prices, estimate_limit=4000)
except ValueError:
    pass
else:
    raise AssertionError("changed hidden threshold was accepted")

extra = copy.deepcopy(proposal)
extra["drafts"][0]["comment"] = "looks safe"
try:
    validate_draft(extra, expanded, prices, estimate_limit=4000)
except ValueError:
    pass
else:
    raise AssertionError("undeclared row field was accepted")

connected_hidden = Harness(validate_draft, estimate_limit=4000).run(proposal, expanded, prices)
assert connected_hidden["status"] == "DRAFT_READY"
assert connected_hidden["draft"]["estimated_pence"] == 3500
print("HOLDOUT_RESULT=" + json.dumps({"unit": "ch01-b", "status": "PASSED"}, sort_keys=True))
