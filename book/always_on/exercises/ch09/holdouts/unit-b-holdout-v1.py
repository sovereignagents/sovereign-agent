"""Instructor-held checks appended after a submitted Chapter 9 Unit B notebook."""

# ruff: noqa: F821 - executed inside the submitted notebook namespace

import json

hidden_lab = RuntimeLab(ROOT, 9)
try:
    hidden_lab.break_source()
    hidden_lab.repair(repair_fragment())
    hidden_repair = hidden_lab.run(
        "HIDDEN_RECONCILIATION",
        expected={
            "supplier_order_count": 1,
            "local_statuses": ["UNKNOWN", "ACCEPTED"],
            "same_id_retransmission_count": 1,
        },
    )
finally:
    hidden_lab.close()
assert hidden_repair["status"] == "PASS"

declined = run_partner_fixture(normalize_discovery, "declined")
assert declined == {
    "statuses": ["UNKNOWN", "REJECTED"],
    "local_status": "REJECTED",
    "events": ["order", "lookup"],
    "supplier_orders": 1,
    "money": (0, 0),
}

try:
    normalize_discovery(
        {
            "order_ref": "hidden",
            "payload": partner_proposal,
            "decision": "maybe",
        }
    )
except ValueError:
    pass
else:
    raise AssertionError("unknown partner decision was guessed")

print("HOLDOUT_RESULT=" + json.dumps({"unit": "ch09-b", "status": "PASSED"}, sort_keys=True))
