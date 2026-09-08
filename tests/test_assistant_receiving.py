"""Acceptance is not delivery; receiving credits observed physical stock once."""

import json
import time

import pytest

from reference_organizations.store.agent import seed_lucy, shop_dispatcher
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose, receive
from sovereign_agent.assistant_work import claim, enqueue
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ToolCall


class Supplier:
    identity = "lucy-local"
    idempotent = True
    timeout = 1
    sends = 0

    def order(self, operation, proposal):
        self.sends += 1
        return {"operation": operation, "proposal": proposal, "status": "ACCEPTED"}

    def lookup(self, operation):
        return None


def setup(tmp_path, *, confirmed=True):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    enqueue(db, "receive:one", "lucy", "replenish")
    work = claim(db, "worker")
    identifier = propose(db, work, "SKU-VANILLA", 6)
    policy = SpendingPolicy(frozenset({"lucy"}))
    supplier = Supplier()
    if confirmed:
        digest = db.connection.execute(
            "SELECT digest FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone()[0]
        approve(db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60)
        execute(db, work, identifier, supplier, policy=policy)
    return db, work, identifier, policy, supplier


def vanilla(db):
    rows = shop_dispatcher(db).invoke(ToolCall(id="stock", name="list_stock", arguments={}))
    return next(row for row in rows["value"] if row["sku"] == "SKU-VANILLA")


def test_delivery_moves_incoming_to_physical_stock_exactly_once(tmp_path):
    db, work, identifier, policy, supplier = setup(tmp_path)
    before = vanilla(db)
    assert (before["on_hand"], before["on_order"], before["needed"]) == (2, 6, 0)
    received = receive(db, identifier, "delivery-note-1", actor="lucy", policy=policy)
    assert received["duplicate"] is False
    after = vanilla(db)
    assert (after["on_hand"], after["on_order"], after["needed"]) == (8, 0, 0)
    other = Database(db.path)
    assert (
        receive(other, identifier, "delivery-note-1", actor="lucy", policy=policy)["duplicate"]
        is True
    )
    assert vanilla(db)["on_hand"] == 8
    with pytest.raises(ValueError, match="different delivery"):
        receive(db, identifier, "another-note", actor="lucy", policy=policy)
    assert execute(db, work, identifier, supplier, policy=policy)["status"] == "ACCEPTED"
    assert supplier.sends == 1
    assert tuple(
        db.connection.execute(
            "SELECT reserved_pence,spent_pence FROM assistant_spending"
        ).fetchone()
    ) == (0, 1500)
    record = db.connection.execute(
        "SELECT record FROM inventory WHERE sku='SKU-VANILLA'"
    ).fetchone()[0]
    assert json.loads(record)["on_hand"] == 8
    other.close()
    db.close()


def test_unconfirmed_or_unauthorized_delivery_cannot_credit_stock(tmp_path):
    db, _, identifier, policy, _ = setup(tmp_path, confirmed=False)
    with pytest.raises(PermissionError, match="allowlisted"):
        receive(db, identifier, "note", actor="model", policy=policy)
    with pytest.raises(PermissionError, match="confirmed order"):
        receive(db, identifier, "note", actor="lucy", policy=policy)
    assert vanilla(db)["on_hand"] == 2
    assert db.connection.execute("SELECT count(*) FROM assistant_deliveries").fetchone()[0] == 0
    db.close()


def test_receiving_rollback_preserves_stock_order_and_delivery_record(tmp_path, monkeypatch):
    db, _, identifier, policy, _ = setup(tmp_path)

    def crash(*args, **kwargs):
        raise RuntimeError("crash before receiving commit")

    monkeypatch.setattr("sovereign_agent.assistant_orders.append_event", crash)
    with pytest.raises(RuntimeError):
        receive(db, identifier, "note", actor="lucy", policy=policy)
    assert vanilla(db)["on_hand"] == 2 and vanilla(db)["on_order"] == 6
    assert db.connection.execute("SELECT status FROM assistant_orders").fetchone()[0] == "CONFIRMED"
    assert db.connection.execute("SELECT count(*) FROM assistant_deliveries").fetchone()[0] == 0
    db.close()


def test_restored_paused_inventory_cannot_receive_without_reconciliation(tmp_path):
    db, _, identifier, policy, _ = setup(tmp_path)
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_control SET paused=1")
    with pytest.raises(PermissionError, match="reconciliation"):
        receive(db, identifier, "note", actor="lucy", policy=policy)
    assert vanilla(db)["on_hand"] == 2
    db.close()
