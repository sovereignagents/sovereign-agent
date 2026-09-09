# ruff: noqa: F821 - executed inside the submitted notebook namespace

import json

from sovereign_agent.events import append_event


def record_transition(db, work_id, identifier, event, receipt=None):
    with db.immediate() as connection:
        row = connection.execute(
            "SELECT * FROM assistant_orders WHERE id=? AND work_id=?", (identifier, work_id)
        ).fetchone()
        if row is None:
            raise PermissionError("operation does not belong to this work")
        if event == "ADMIT":
            if row["status"] != "APPROVED":
                raise PermissionError("only an approved operation may be sent")
            connection.execute(
                "UPDATE assistant_orders SET status='SENDING' WHERE id=?", (identifier,)
            )
            append_event(db, "assistant.order.intent", {"order": identifier})
        elif event == "UNKNOWN":
            if row["status"] != "SENDING":
                raise PermissionError("only an admitted send may become unknown")
            connection.execute(
                "UPDATE assistant_orders SET status='UNKNOWN' WHERE id=?", (identifier,)
            )
        elif event == "RECEIPT":
            if not isinstance(receipt, dict):
                raise ValueError("receipt required")
            encoded = json.dumps(
                receipt.get("proposal"), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            if receipt.get("operation") != identifier or encoded != row["proposal"]:
                raise ValueError("receipt does not match exact intent")
            if receipt.get("status") not in {"ACCEPTED", "REJECTED"}:
                raise ValueError("receipt is not conclusive")
            if row["status"] in {"CONFIRMED", "REJECTED"}:
                if json.loads(row["receipt"]) != receipt:
                    raise ValueError("receipt contradicts recorded outcome")
                return order_observation(db, identifier)
            if row["status"] not in {"SENDING", "UNKNOWN"}:
                raise PermissionError("operation was not admitted")
            accepted = receipt["status"] == "ACCEPTED"
            connection.execute(
                "UPDATE assistant_orders SET status=?,receipt=? WHERE id=?",
                ("CONFIRMED" if accepted else "REJECTED", json.dumps(receipt), identifier),
            )
            connection.execute(
                "UPDATE assistant_spending SET reserved_pence=reserved_pence-?,"
                "spent_pence=spent_pence+? WHERE id=1",
                (row["amount"], row["amount"] if accepted else 0),
            )
            append_event(
                db,
                "assistant.order.reconciled",
                {"order": identifier, "status": receipt["status"]},
            )
        else:
            raise ValueError("unknown transition")
    return order_observation(db, identifier)
