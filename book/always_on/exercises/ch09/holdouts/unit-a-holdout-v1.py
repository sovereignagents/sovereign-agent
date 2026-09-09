"""Instructor-held checks appended after a submitted Chapter 9 Unit A notebook."""

# ruff: noqa: F821 - executed inside the submitted notebook namespace

import json

with tempfile.TemporaryDirectory(prefix="ch09-transition-hidden-") as directory:
    db, work, identifier = approved_order(Path(directory), sku="SKU-STRAWBERRY", quantity=4)
    try:
        admitted = record_transition(db, work.id, identifier, "ADMIT")
        unknown = record_transition(db, work.id, identifier, "UNKNOWN")
        rejected = {
            "operation": identifier,
            "proposal": unknown["proposal"],
            "status": "REJECTED",
        }
        final = record_transition(db, work.id, identifier, "RECEIPT", rejected)
        replay = record_transition(db, work.id, identifier, "RECEIPT", rejected)
        assert admitted["status"] == "SENDING"
        assert (unknown["reserved_pence"], unknown["spent_pence"]) == (1100, 0)
        assert final["status"] == replay["status"] == "REJECTED"
        assert (replay["reserved_pence"], replay["spent_pence"]) == (0, 0)
        try:
            record_transition(db, work.id, identifier, "UNKNOWN")
        except PermissionError:
            pass
        else:
            raise AssertionError("terminal evidence was overwritten by uncertainty")
    finally:
        db.close()

with tempfile.TemporaryDirectory(prefix="ch09-handoff-hidden-") as directory:
    root = Path(directory)
    with independent_supplier(root) as (supplier, supplier_path):
        db, work, identifier = approved_order(root, target=supplier.identity)
        try:
            sent = record_transition(db, work.id, identifier, "ADMIT")
            try:
                supplier.order(identifier, sent["proposal"])
            except OSError:
                after_loss = record_transition(db, work.id, identifier, "UNKNOWN")
            receipt = supplier.lookup(identifier)
            final = record_transition(db, work.id, identifier, "RECEIPT", receipt)
            with sqlite3.connect(supplier_path) as remote:
                count = remote.execute("SELECT count(*) FROM orders").fetchone()[0]
            handoff = {
                "operation": identifier,
                "proposal": final["proposal"],
                "after_loss": after_loss,
                "final": final,
                "supplier_orders": count,
            }
            Path("ch09-unit-a-handoff-v1.json").write_text(
                json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        finally:
            db.close()
assert handoff["after_loss"]["status"] == "UNKNOWN"
assert handoff["final"]["status"] == "CONFIRMED"
assert handoff["supplier_orders"] == 1
print("HOLDOUT_RESULT=" + json.dumps({"unit": "ch09-a", "status": "PASSED"}, sort_keys=True))
