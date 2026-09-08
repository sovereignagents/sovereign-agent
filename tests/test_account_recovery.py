"""An old local snapshot is reconciled against a separate, fenced supplier database."""

import hashlib
import json
import sqlite3
import subprocess
import sys
import time
import uuid

import pytest

from reference_organizations.store.account_recovery import (
    configured_supplier,
    inspect_account,
    recover,
)
from reference_organizations.store.agent import OfflineShopModel, seed_lucy, shop_dispatcher
from reference_organizations.store.assistant import run_once
from reference_organizations.store.supplier import SupplierClient
from sovereign_agent import assistant_orders as orders
from sovereign_agent import assistant_work as work
from sovereign_agent.assistant_service import backup, restore
from sovereign_agent.cli import main
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ToolCall

POLICY = orders.SpendingPolicy(frozenset({"lucy"}))


@pytest.fixture
def supplier(tmp_path):
    ready = tmp_path / "ready"
    path = tmp_path / "supplier.sqlite"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "reference_organizations.store.supplier",
            "--database",
            str(path),
            "--port",
            "0",
            "--ready",
            str(ready),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.02)
        assert ready.exists()
        yield "http://127.0.0.1:" + ready.read_text(), path
    finally:
        process.terminate()
        process.communicate(timeout=5)


def prepare_order(db, client, session, sku, quantity):
    identifier = work.enqueue(db, "request:" + session, session, "Replenish.")
    claim = work.claim(db, session, identifier=identifier)
    operation = orders.propose(db, claim, sku, quantity, target=client.identity)
    digest = db.connection.execute(
        "SELECT digest FROM assistant_orders WHERE id=?", (operation,)
    ).fetchone()[0]
    orders.approve(db, operation, digest, actor="lucy", policy=POLICY, expires=time.time() + 120)
    return claim, operation


def restored(tmp_path, supplier):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    client = configured_supplier(db, supplier[0])
    first, vanilla = prepare_order(db, client, "lucy", "SKU-VANILLA", 6)
    snapshot = backup(db, tmp_path / "before.sqlite")
    assert orders.execute(db, first, vanilla, client, policy=POLICY)["status"] == "ACCEPTED"
    orders.receive(db, vanilla, "delivery-A", actor="lucy", policy=POLICY)
    work.finish(db, first, "DONE", "received")
    second, strawberry = prepare_order(db, client, "afternoon", "SKU-STRAWBERRY", 4)
    assert orders.execute(db, second, strawberry, client, policy=POLICY)["status"] == "ACCEPTED"
    restore(db, snapshot)
    return db, client, first, vanilla, strawberry


def observed_plan(db, client, vanilla, strawberry):
    report = inspect_account(db, client, actor="lucy", policy=POLICY)
    plan = report["plan_template"]
    plan["observed_at"] = time.time()
    plan["inventory"] = {
        "SKU-VANILLA": {"on_hand": 8, "reserved": 0},
        "SKU-CHOCOLATE": {"on_hand": 12, "reserved": 0},
        "SKU-STRAWBERRY": {"on_hand": 1, "reserved": 0},
    }
    plan["deliveries"] = {
        vanilla: {"received": True, "reference": "delivery-A"},
        strawberry: {"received": False, "reference": ""},
    }
    plan["model_grants"] = {"lucy": {"calls": 5, "estimated_pence": 100}}
    return plan


def apply(db, client, plan):
    raw = json.dumps(plan).encode()
    return recover(db, client, raw, hashlib.sha256(raw).hexdigest(), actor="lucy", policy=POLICY)


def test_old_snapshot_imports_new_orders_and_delivery_without_double_stock_or_spending(
    tmp_path, supplier
):
    db, old, old_claim, vanilla, strawberry = restored(tmp_path, supplier)
    assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 1
    plan = observed_plan(db, old, vanilla, strawberry)
    result = apply(db, old, plan)
    assert result == {"status": "ACTIVE", "duplicate": False, "orders": 2, "spent_pence": 2600}
    assert apply(db, old, plan)["duplicate"] is True
    assert tuple(
        db.connection.execute(
            "SELECT reserved_pence,spent_pence FROM assistant_spending"
        ).fetchone()
    ) == (0, 2600)
    assert dict(db.connection.execute("SELECT id,status FROM assistant_orders")) == {
        vanilla: "DELIVERED",
        strawberry: "CONFIRMED",
    }
    values = shop_dispatcher(db).invoke(ToolCall(id="stock", name="list_stock", arguments={}))[
        "value"
    ]
    assert [(r["sku"], r["on_hand"], r["on_order"], r["needed"]) for r in values] == [
        ("SKU-CHOCOLATE", 12, 0, 0),
        ("SKU-STRAWBERRY", 1, 4, 0),
        ("SKU-VANILLA", 8, 0, 0),
    ]
    with pytest.raises(PermissionError):
        work.assert_current(db.connection, old_claim)
    fresh = configured_supplier(db, supplier[0])
    assert fresh.account == old.account and fresh.epoch == 1
    work.enqueue(db, "fresh", "lucy", "Prepare a stock brief.")
    assert run_once(db, OfflineShopModel())["status"] == "DONE"
    assert (
        db.connection.execute(
            "SELECT history_complete FROM assistant_daily WHERE session='lucy'"
        ).fetchone()[0]
        == 0
    )
    db.close()


def test_fence_is_idempotent_and_refuses_late_old_client_and_legacy_client(tmp_path, supplier):
    db, old, _, vanilla, strawberry = restored(tmp_path, supplier)
    first = inspect_account(db, old, actor="lucy", policy=POLICY)
    second = inspect_account(db, old, actor="lucy", policy=POLICY)
    assert first["provider_epoch"] == second["provider_epoch"] == 1
    proposal = first["receipts"][0]["proposal"]
    for client in [old, SupplierClient(supplier[0])]:
        with pytest.raises(OSError):
            client.order(uuid.uuid4().hex, proposal)
    with sqlite3.connect(supplier[1]) as remote:
        assert remote.execute("SELECT count(*) FROM orders").fetchone()[0] == 2
        assert remote.execute("SELECT count(*) FROM rotations").fetchone()[0] == 1
    db.close()


@pytest.mark.parametrize(
    "mutation", ["missing_count", "missing_delivery", "stale", "wrong_epoch", "unknown_grant"]
)
def test_incomplete_or_stale_plan_cannot_resume(tmp_path, supplier, mutation):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    plan = observed_plan(db, client, vanilla, strawberry)
    if mutation == "missing_count":
        plan["inventory"].pop("SKU-CHOCOLATE")
    elif mutation == "missing_delivery":
        plan["deliveries"].pop(strawberry)
    elif mutation == "stale":
        plan["observed_at"] -= 3601
    elif mutation == "wrong_epoch":
        plan["authority_epoch"] = "f" * 32
    else:
        plan["model_grants"]["invented"] = {"calls": 100, "estimated_pence": 1000}
    with pytest.raises((ValueError, PermissionError)):
        apply(db, client, plan)
    assert db.connection.execute("SELECT paused FROM assistant_control").fetchone()[0] == 1
    assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 1
    db.close()


def test_plan_digest_and_operator_are_checked_before_network(tmp_path, supplier, monkeypatch):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    plan = observed_plan(db, client, vanilla, strawberry)
    raw = json.dumps(plan).encode()
    monkeypatch.setattr(
        client, "account_call", lambda *a, **k: pytest.fail("unauthorized network call")
    )
    with pytest.raises(ValueError):
        recover(db, client, raw, "wrong", actor="lucy", policy=POLICY)
    with pytest.raises(PermissionError):
        recover(db, client, raw, hashlib.sha256(raw).hexdigest(), actor="model", policy=POLICY)
    db.close()


def test_local_recovery_rolls_back_but_retries_same_remote_fence(tmp_path, supplier, monkeypatch):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    plan = observed_plan(db, client, vanilla, strawberry)
    with monkeypatch.context() as patch:

        def crash(*args, **kwargs):
            raise RuntimeError("crash before local activation")

        patch.setattr("reference_organizations.store.account_recovery.append_event", crash)
        with pytest.raises(RuntimeError):
            apply(db, client, plan)
    assert db.connection.execute("SELECT paused FROM assistant_control").fetchone()[0] == 1
    assert db.connection.execute("SELECT epoch FROM assistant_supplier_bindings").fetchone()[0] == 0
    assert (
        db.connection.execute("SELECT on_hand FROM inventory WHERE sku='SKU-VANILLA'").fetchone()[0]
        == 2
    )
    assert apply(db, client, plan)["spent_pence"] == 2600
    assert db.connection.execute("SELECT epoch FROM assistant_supplier_bindings").fetchone()[0] == 1
    db.close()


def test_changed_supplier_account_cannot_be_adopted_at_same_endpoint(tmp_path, supplier):
    db, client, _, _, _ = restored(tmp_path, supplier)
    with sqlite3.connect(supplier[1]) as remote:
        remote.execute("UPDATE account SET identity=?", (uuid.uuid4().hex,))
    with pytest.raises(OSError):
        inspect_account(db, client, actor="lucy", policy=POLICY)
    assert db.connection.execute("SELECT paused FROM assistant_control").fetchone()[0] == 1
    db.close()


def test_no_implicit_model_allowance_is_restored(tmp_path, supplier):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    plan = observed_plan(db, client, vanilla, strawberry)
    plan["model_grants"] = {}
    apply(db, client, plan)
    work.enqueue(db, "fresh", "lucy", "brief")
    current = work.claim(db, "fresh")
    with pytest.raises(PermissionError):
        work.reserve_model_call(db, current, 0)
    db.close()


def test_previously_confirmed_receipt_cannot_disappear_from_account(tmp_path, supplier):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    client = configured_supplier(db, supplier[0])
    owner, operation = prepare_order(db, client, "lucy", "SKU-VANILLA", 6)
    orders.execute(db, owner, operation, client, policy=POLICY)
    snapshot = backup(db, tmp_path / "confirmed.sqlite")
    restore(db, snapshot)
    with sqlite3.connect(supplier[1]) as remote:
        remote.execute("DELETE FROM orders WHERE operation=?", (operation,))
    plan = inspect_account(db, client, actor="lucy", policy=POLICY)["plan_template"]
    plan["observed_at"] = time.time()
    plan["inventory"] = {
        "SKU-VANILLA": {"on_hand": 2, "reserved": 0},
        "SKU-CHOCOLATE": {"on_hand": 12, "reserved": 0},
        "SKU-STRAWBERRY": {"on_hand": 1, "reserved": 0},
    }
    with pytest.raises(ValueError, match="conclusive"):
        apply(db, client, plan)
    assert db.connection.execute("SELECT paused FROM assistant_control").fetchone()[0] == 1
    db.close()


def test_known_delivery_cannot_be_reclassified_as_pending(tmp_path, supplier):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    plan = observed_plan(db, client, vanilla, strawberry)
    apply(db, client, plan)
    snapshot = backup(db, tmp_path / "delivered.sqlite")
    restore(db, snapshot)
    client = configured_supplier(db, supplier[0])
    plan = observed_plan(db, client, vanilla, strawberry)
    plan["deliveries"][vanilla] = {"received": False, "reference": ""}
    with pytest.raises(ValueError, match="receiving"):
        apply(db, client, plan)
    db.close()


@pytest.mark.parametrize("corruption", ["incomplete", "duplicate", "proposal"])
def test_export_corruption_fails_closed(tmp_path, supplier, monkeypatch, corruption):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    plan = observed_plan(db, client, vanilla, strawberry)
    original = client.account_call

    def corrupted(path="/account", **kwargs):
        result = original(path, **kwargs)
        if path == "/account/snapshot":
            if corruption == "incomplete":
                result["complete"] = False
            elif corruption == "duplicate":
                result["receipts"].append(result["receipts"][0])
            else:
                result["receipts"] = sorted(
                    result["receipts"], key=lambda r: r["operation"] != vanilla
                )
                result["receipts"][0]["proposal"]["quantity"] = 7
        return result

    monkeypatch.setattr(client, "account_call", corrupted)
    with pytest.raises(ValueError):
        apply(db, client, plan)
    assert db.connection.execute("SELECT paused FROM assistant_control").fetchone()[0] == 1
    db.close()


def test_newer_fence_makes_previous_recovery_export_unusable(tmp_path, supplier):
    db, client, _, _, _ = restored(tmp_path, supplier)
    first = inspect_account(db, client, actor="lucy", policy=POLICY)
    newer = client.account_call(
        "/account/fence", data={"account": client.account, "rotation": uuid.uuid4().hex}
    )
    assert newer["epoch"] > first["provider_epoch"]
    with pytest.raises(OSError):
        inspect_account(db, client, actor="lucy", policy=POLICY)
    db.close()


def test_cli_inspection_and_exact_plan_recovery(tmp_path, supplier, capsys):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    assert (
        main(["agent", "inspect-account", "--root", str(tmp_path), "--supplier", supplier[0]]) == 0
    )
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["plan_template"]["inventory"]["SKU-VANILLA"]["on_hand"] is None
    plan = observed_plan(db, client, vanilla, strawberry)
    path = tmp_path / "recovery.json"
    raw = json.dumps(plan).encode()
    path.write_bytes(raw)
    assert (
        main(
            [
                "agent",
                "recover-account",
                str(path),
                "--root",
                str(tmp_path),
                "--supplier",
                supplier[0],
                "--digest",
                hashlib.sha256(raw).hexdigest(),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "ACTIVE"
    db.close()


def test_old_request_accepted_after_local_restore_is_included_before_fence(tmp_path, supplier):
    db, old, _, vanilla, strawberry = restored(tmp_path, supplier)
    late = uuid.uuid4().hex
    proposal = {
        "sku": "SKU-CHOCOLATE",
        "quantity": 1,
        "unit_cost_pence": 300,
        "supplier": "lucy-local",
        "currency": "GBP",
    }
    assert old.order(late, proposal)["status"] == "ACCEPTED"
    plan = observed_plan(db, old, vanilla, strawberry)
    plan["deliveries"][late] = {"received": False, "reference": ""}
    result = apply(db, old, plan)
    assert result["orders"] == 3 and result["spent_pence"] == 2900
    assert (
        db.connection.execute("SELECT status FROM assistant_orders WHERE id=?", (late,)).fetchone()[
            0
        ]
        == "CONFIRMED"
    )
    with pytest.raises(OSError):
        old.order(uuid.uuid4().hex, proposal)
    db.close()


def test_absent_old_approval_is_closed_without_a_send(tmp_path, supplier):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    client = configured_supplier(db, supplier[0])
    old, operation = prepare_order(db, client, "lucy", "SKU-VANILLA", 6)
    snapshot = backup(db, tmp_path / "unsent.sqlite")
    restore(db, snapshot)
    plan = inspect_account(db, client, actor="lucy", policy=POLICY)["plan_template"]
    plan["observed_at"] = time.time()
    plan["inventory"] = {
        "SKU-VANILLA": {"on_hand": 2, "reserved": 0},
        "SKU-CHOCOLATE": {"on_hand": 12, "reserved": 0},
        "SKU-STRAWBERRY": {"on_hand": 1, "reserved": 0},
    }
    assert apply(db, client, plan)["spent_pence"] == 0
    assert (
        db.connection.execute(
            "SELECT status FROM assistant_orders WHERE id=?", (operation,)
        ).fetchone()[0]
        == "REVOKED"
    )
    with sqlite3.connect(supplier[1]) as remote:
        assert remote.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
    with pytest.raises(PermissionError):
        orders.execute(db, old, operation, client, policy=POLICY)
    db.close()


def test_replaying_recovery_does_not_renew_fresh_model_grant(tmp_path, supplier):
    db, client, _, vanilla, strawberry = restored(tmp_path, supplier)
    plan = observed_plan(db, client, vanilla, strawberry)
    plan["model_grants"]["lucy"] = {"calls": 1, "estimated_pence": 0}
    apply(db, client, plan)
    work.enqueue(db, "fresh", "lucy", "brief")
    owner = work.claim(db, "fresh")
    work.reserve_model_call(db, owner, 0)
    assert apply(db, client, plan)["duplicate"] is True
    with pytest.raises(PermissionError):
        work.reserve_model_call(db, owner, 0)
    db.close()


def test_initial_binding_refuses_historical_local_orders(tmp_path, supplier):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    client = SupplierClient(supplier[0])
    prepare_order(db, client, "lucy", "SKU-VANILLA", 6)
    with pytest.raises(PermissionError, match="historical"):
        configured_supplier(db, supplier[0])
    assert (
        db.connection.execute("SELECT count(*) FROM assistant_supplier_bindings").fetchone()[0] == 0
    )
    db.close()
