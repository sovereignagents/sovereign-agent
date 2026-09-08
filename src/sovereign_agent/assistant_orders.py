"""Exact-proposal approval, reserved spending, and uncertain external effects."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from sovereign_agent.assistant_work import Claim, assert_current
from sovereign_agent.database import Database
from sovereign_agent.events import append_event


@dataclass(frozen=True)
class SpendingPolicy:
    operators: frozenset[str]
    total_pence: int = 20_000
    automatic_order_pence: int = 0

    def __post_init__(self) -> None:
        if not self.operators or type(self.total_pence) is not int or self.total_pence <= 0:
            raise ValueError("operators and positive spending ceiling required")
        if (
            type(self.automatic_order_pence) is not int
            or not 0 <= self.automatic_order_pence <= self.total_pence
        ):
            raise ValueError("automatic allowance must fit the total ceiling")


class Supplier(Protocol):
    idempotent: bool

    @property
    def identity(self) -> str: ...

    @property
    def timeout(self) -> float: ...

    def lookup(self, operation: str) -> dict[str, Any] | None: ...
    def order(self, operation: str, proposal: dict[str, Any]) -> dict[str, Any]: ...


def propose(
    db: Database, work: Claim, sku: str, quantity: int, *, target: str = "lucy-local"
) -> str:
    if type(quantity) is not int or not 1 <= quantity <= 1000:
        raise ValueError("positive integral bounded quantity required")
    with db.immediate() as connection:
        assert_current(connection, work)
        if work.role != "shop":
            raise PermissionError("delegated research has no purchasing authority")
        if work.subject and work.subject != sku:
            raise PermissionError("proposal differs from the work item's subject")
        product = connection.execute("SELECT record FROM products WHERE sku=?", (sku,)).fetchone()
        if product is None:
            raise ValueError("unknown product")
        cost = json.loads(product[0])["unit_cost_cents"]
        if type(cost) is not int or cost <= 0:
            raise ValueError("invalid authoritative product cost")
        proposal = {
            "sku": sku,
            "quantity": quantity,
            "unit_cost_pence": cost,
            "supplier": "lucy-local",
            "currency": "GBP",
        }
        encoded = json.dumps(proposal, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256((target + "\n" + encoded).encode()).hexdigest()
        # One stable intent for this exact proposal in this assignment. A deliberate
        # second purchase requires another work item, not another random tool-call ID.
        identifier = uuid.uuid5(uuid.NAMESPACE_URL, work.id + ":" + digest).hex
        if connection.execute(
            "SELECT 1 FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone():
            return identifier  # Repeating an old revision never resurrects its authority.
        previous = connection.execute(
            "SELECT id,status,amount FROM assistant_orders "
            "WHERE work_id=? AND json_extract(proposal,'$.sku')=?",
            (work.id, sku),
        ).fetchall()
        if any(
            row["status"] in {"SENDING", "UNKNOWN", "CONFIRMED", "DELIVERED"} for row in previous
        ):
            raise PermissionError(
                "existing product effect must be resolved; new purchase needs new work"
            )
        for row in previous:
            if row["status"] not in {"DRAFT", "APPROVED"}:
                continue
            if row["status"] == "APPROVED":
                connection.execute(
                    "UPDATE assistant_spending SET reserved_pence=reserved_pence-? WHERE id=1",
                    (row["amount"],),
                )
            connection.execute(
                "UPDATE assistant_orders SET status='REVOKED',revoked=1 WHERE id=?", (row["id"],)
            )
            append_event(
                db, "assistant.order.superseded", {"order": row["id"], "replacement": identifier}
            )
        connection.execute(
            "INSERT OR IGNORE INTO assistant_orders"
            "(id,work_id,proposal,digest,amount,created,target) "
            "VALUES (?,?,?,?,?,?,?)",
            (identifier, work.id, encoded, digest, quantity * cost, time.time(), target),
        )
        return identifier


def approve(
    db: Database,
    identifier: str,
    digest: str,
    *,
    actor: str,
    policy: SpendingPolicy,
    expires: float,
    automatic: bool = False,
    now: float | None = None,
) -> None:
    now = time.time() if now is None else now
    if type(automatic) is not bool:
        raise ValueError("approval basis must be explicit")
    if not math.isfinite(expires) or not now < expires <= now + 86400:
        raise ValueError("approval must expire within one day")
    if actor not in policy.operators:
        raise PermissionError("operator is not allowlisted")
    with db.immediate() as connection:
        order = connection.execute(
            "SELECT * FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone()
        if (
            order is None
            or order["digest"] != digest
            or order["status"] not in {"DRAFT", "APPROVED"}
            or order["revoked"]
        ):
            raise PermissionError("approval does not match an eligible exact proposal")
        if automatic and order["amount"] > policy.automatic_order_pence:
            raise PermissionError("exact proposal needs operator approval")
        connection.execute(
            "INSERT OR IGNORE INTO assistant_spending(id,limit_pence) VALUES (1,?)",
            (policy.total_pence,),
        )
        budget = connection.execute("SELECT * FROM assistant_spending WHERE id=1").fetchone()
        assert budget
        addition = order["amount"] if order["status"] == "DRAFT" else 0
        # A supplied policy cannot silently raise the installed account ceiling.
        if budget["spent_pence"] + budget["reserved_pence"] + addition > min(
            budget["limit_pence"], policy.total_pence
        ):
            raise PermissionError("cumulative spending ceiling reached")
        connection.execute(
            "UPDATE assistant_spending SET reserved_pence=reserved_pence+? WHERE id=1", (addition,)
        )
        connection.execute(
            "UPDATE assistant_orders SET status='APPROVED',approved_by=?,approved_until=?,"
            "approval_basis=? WHERE id=?",
            (actor, expires, "AUTOMATIC" if automatic else "OPERATOR", identifier),
        )
        append_event(
            db,
            "assistant.order.approved",
            {"order": identifier, "digest": digest, "actor": actor, "automatic": automatic},
        )


def revoke(db: Database, identifier: str, *, actor: str, policy: SpendingPolicy) -> None:
    if actor not in policy.operators:
        raise PermissionError("operator is not allowlisted")
    with db.immediate() as connection:
        row = connection.execute(
            "SELECT * FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone()
        if row is None or row["revoked"]:
            return
        # In-flight/unknown reservations remain held until the supplier resolves them.
        if row["status"] == "APPROVED":
            connection.execute(
                "UPDATE assistant_spending SET reserved_pence=reserved_pence-? WHERE id=1",
                (row["amount"],),
            )
            connection.execute(
                "UPDATE assistant_orders SET status='REVOKED' WHERE id=?", (identifier,)
            )
        connection.execute(
            "UPDATE assistant_orders SET revoked=1,status=CASE WHEN status='DRAFT' "
            "THEN 'REVOKED' ELSE status END WHERE id=?",
            (identifier,),
        )
        append_event(db, "assistant.order.revoked", {"order": identifier, "actor": actor})


def _record(db: Database, work: Claim, identifier: str, receipt: dict[str, Any]) -> dict[str, Any]:
    with db.immediate() as connection:
        assert_current(connection, work)
        row = connection.execute(
            "SELECT * FROM assistant_orders WHERE id=? AND work_id=?", (identifier, work.id)
        ).fetchone()
        assert row
        if (
            receipt.get("operation") != identifier
            or json.dumps(
                receipt.get("proposal"), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            != row["proposal"]
        ):
            raise ValueError("supplier receipt does not match the exact intent")
        if receipt.get("status") not in {"ACCEPTED", "REJECTED"}:
            raise ValueError("supplier outcome is not conclusive")
        if row["status"] in {"CONFIRMED", "DELIVERED", "REJECTED"}:
            return dict(json.loads(row["receipt"]))
        if row["status"] not in {"SENDING", "UNKNOWN"}:
            raise PermissionError("order was not admitted for transmission")
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
            db, "assistant.order.reconciled", {"order": identifier, "status": receipt["status"]}
        )
    return receipt


def execute(
    db: Database, work: Claim, identifier: str, supplier: Supplier, *, policy: SpendingPolicy
) -> dict[str, Any]:
    """A recovered uncertain intent is discovered before any possible retransmission.

    Supplier idempotency is an explicit adapter contract, not a property inferred
    from HTTP or a local transaction. Fence admission; cannot recall a sent request.
    """
    row = db.connection.execute(
        "SELECT * FROM assistant_orders WHERE id=? AND work_id=?", (identifier, work.id)
    ).fetchone()
    if row is None:
        raise PermissionError("order belongs to another work item")
    assert_current(db.connection, work)
    if row["target"] != supplier.identity:
        raise PermissionError("supplier destination differs from the approved proposal")
    if row["status"] in {"CONFIRMED", "DELIVERED", "REJECTED"}:
        return dict(json.loads(row["receipt"]))
    if row["status"] in {"SENDING", "UNKNOWN"}:
        try:
            receipt = supplier.lookup(identifier)
            if receipt is not None:
                return _record(db, work, identifier, receipt)
        except OSError, ValueError:
            return {"status": "UNKNOWN", "operation": identifier}
        if not supplier.idempotent:
            return {"status": "UNKNOWN", "operation": identifier, "needs_operator": True}
    with db.immediate() as connection:
        assert_current(connection, work)
        current = connection.execute(
            "SELECT * FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone()
        assert current
        budget = connection.execute("SELECT * FROM assistant_spending WHERE id=1").fetchone()
        held = connection.execute(
            "SELECT coalesce(sum(amount),0) FROM assistant_orders "
            "WHERE status IN ('APPROVED','SENDING','UNKNOWN')"
        ).fetchone()[0]
        if (
            budget is None
            or budget["reserved_pence"] < held
            or budget["spent_pence"] + budget["reserved_pence"]
            > min(budget["limit_pence"], policy.total_pence)
            or current["approved_by"] not in policy.operators
            or current["approval_basis"] == "UNKNOWN"
            or (
                current["approval_basis"] == "AUTOMATIC"
                and current["amount"] > policy.automatic_order_pence
            )
        ):
            raise PermissionError("current spending authority or reservation is insufficient")
        expires = connection.execute(
            "SELECT expires FROM assistant_work WHERE id=? AND cancelled=0", (work.id,)
        ).fetchone()
        if expires is None:
            raise PermissionError("cancelled work cannot authorize a new send")
        expires = expires[0]
        if (
            not math.isfinite(supplier.timeout)
            or supplier.timeout <= 0
            or expires - time.time() <= supplier.timeout
        ):
            raise PermissionError("supplier wait would exceed current ownership")
        if (
            current["status"] not in {"APPROVED", "SENDING", "UNKNOWN"}
            or current["revoked"]
            or (current["approved_until"] or 0) <= time.time()
        ):
            raise PermissionError("current exact-order approval required")
        connection.execute("UPDATE assistant_orders SET status='SENDING' WHERE id=?", (identifier,))
        append_event(
            db, "assistant.order.intent", {"order": identifier, "generation": work.generation}
        )
    try:
        receipt = supplier.order(identifier, json.loads(row["proposal"]))
        return _record(db, work, identifier, receipt)
    except OSError, ValueError:
        with db.immediate() as connection:
            assert_current(connection, work)
            connection.execute(
                "UPDATE assistant_orders SET status='UNKNOWN' WHERE id=? AND status='SENDING'",
                (identifier,),
            )
        return {"status": "UNKNOWN", "operation": identifier}


def receive(
    db: Database, identifier: str, reference: str, *, actor: str, policy: SpendingPolicy
) -> dict[str, Any]:
    """Record one operator-observed full delivery; supplier acceptance is not stock."""
    if actor not in policy.operators:
        raise PermissionError("operator is not allowlisted")
    if not reference.strip() or len(reference) > 200:
        raise ValueError("a bounded delivery reference is required")
    with db.immediate() as connection:
        if connection.execute("SELECT paused FROM assistant_control WHERE id=1").fetchone()[0]:
            raise PermissionError("restored inventory requires reconciliation before receiving")
        previous = connection.execute(
            "SELECT * FROM assistant_deliveries WHERE order_id=?", (identifier,)
        ).fetchone()
        if previous:
            if previous["reference"] != reference:
                raise ValueError("a different delivery is already recorded for this order")
            return {"status": "DELIVERED", "order": identifier, "duplicate": True}
        row = connection.execute(
            "SELECT * FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone()
        if row is None or row["status"] != "CONFIRMED":
            raise PermissionError("a confirmed order is required before receiving")
        proposal = json.loads(row["proposal"])
        updated = connection.execute(
            "UPDATE inventory SET on_hand=on_hand+?,"
            "record=json_set(record,'$.on_hand',on_hand+?) WHERE sku=?",
            (proposal["quantity"], proposal["quantity"], proposal["sku"]),
        )
        if updated.rowcount != 1:
            raise ValueError("delivery product has no inventory record")
        connection.execute(
            "INSERT INTO assistant_deliveries VALUES (?,?,?,?,?)",
            (identifier, reference, actor, proposal["quantity"], time.time()),
        )
        connection.execute(
            "UPDATE assistant_orders SET status='DELIVERED' WHERE id=?", (identifier,)
        )
        append_event(
            db,
            "assistant.order.received",
            {
                "order": identifier,
                "reference": reference,
                "actor": actor,
                "quantity": proposal["quantity"],
            },
        )
    return {
        "status": "DELIVERED",
        "order": identifier,
        "quantity": proposal["quantity"],
        "duplicate": False,
    }
