"""Chapter 15: recover a consistent local snapshot against retained supplier history."""

import hashlib
import json
import runpy
import sqlite3
import tempfile
import time
from pathlib import Path

from reference_organizations.store.account_recovery import (
    configured_supplier,
    inspect_account,
    recover,
)
from reference_organizations.store.agent import OfflineShopModel, seed_lucy, shop_dispatcher
from reference_organizations.store.assistant import run_once
from sovereign_agent import assistant_orders as orders
from sovereign_agent import assistant_work as work
from sovereign_agent.assistant_service import backup, health, restore, unit_text
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ToolCall


def experiment(root, supplier_process):
    policy = orders.SpendingPolicy(frozenset({"lucy"}))
    with supplier_process(root) as (endpoint, supplier_path):
        db = Database(root / "agent.sqlite")
        observer = None
        try:
            seed_lucy(db)
            client = configured_supplier(db, endpoint.endpoint)

            def prepare(source, sku, quantity):
                identifier = work.enqueue(db, source, "lucy", "Prepare replenishment.")
                holder = work.claim(db, source, identifier=identifier)
                operation = orders.propose(db, holder, sku, quantity, target=client.identity)
                digest = db.connection.execute(
                    "SELECT digest FROM assistant_orders WHERE id=?", (operation,)
                ).fetchone()[0]
                orders.approve(
                    db, operation, digest, actor="lucy", policy=policy, expires=time.time() + 120
                )
                return holder, operation

            original, vanilla = prepare("morning", "SKU-VANILLA", 6)
            snapshot = backup(db, root / "morning.sqlite")
            snapshot_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
            try:
                backup(db, snapshot)
            except FileExistsError:
                pass
            else:
                raise AssertionError("backup overwrote prior evidence")
            assert snapshot.stat().st_mode & 0o077 == 0
            assert (
                orders.execute(db, original, vanilla, client, policy=policy)["status"] == "ACCEPTED"
            )
            orders.receive(db, vanilla, "delivery-A", actor="lucy", policy=policy)
            work.finish(db, original, "DONE", "received")
            later, strawberry = prepare("afternoon", "SKU-STRAWBERRY", 4)
            assert (
                orders.execute(db, later, strawberry, client, policy=policy)["status"] == "ACCEPTED"
            )
            work.finish(db, later, "DONE", "awaiting delivery")
            observer = Database(db.path)
            inode = db.path.stat().st_ino
            restore(db, snapshot)
            assert db.path.stat().st_ino == inode
            assert health(db)["paused"] is True
            assert work.claim(db, "replacement") is None
            try:
                work.assert_current(observer.connection, later)
            except PermissionError:
                pass
            else:
                raise AssertionError("pre-restore connection retained authority")
            assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 1
            assert db.connection.execute("SELECT revoked FROM assistant_orders").fetchone()[0] == 1
            inspection = inspect_account(db, client, actor="lucy", policy=policy)
            assert len(inspection["receipts"]) == 2
            plan = inspection["plan_template"]
            assert plan["inventory"]["SKU-VANILLA"]["on_hand"] is None
            plan["observed_at"] = time.time()
            # Authored physical observations are independent of the restored inventory.
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
            raw = json.dumps(plan).encode()
            digest = hashlib.sha256(raw).hexdigest()
            try:
                recover(db, client, raw, "0" * 64, actor="lucy", policy=policy)
            except ValueError:
                pass
            else:
                raise AssertionError("changed recovery bytes were accepted")
            assert health(db)["paused"] is True
            result = recover(db, client, raw, digest, actor="lucy", policy=policy)
            assert result == {
                "status": "ACTIVE",
                "duplicate": False,
                "orders": 2,
                "spent_pence": 2600,
            }
            assert (
                recover(db, client, raw, digest, actor="lucy", policy=policy)["duplicate"] is True
            )
            assert dict(db.connection.execute("SELECT id,status FROM assistant_orders")) == {
                vanilla: "DELIVERED",
                strawberry: "CONFIRMED",
            }
            stock = shop_dispatcher(db).invoke(
                ToolCall(id="stock", name="list_stock", arguments={})
            )
            assert [(row["on_hand"], row["on_order"], row["needed"]) for row in stock["value"]] == [
                (12, 0, 0),
                (1, 4, 0),
                (8, 0, 0),
            ]
            try:
                client.order("f" * 32, inspection["receipts"][0]["proposal"])
            except OSError:
                pass
            else:
                raise AssertionError("old supplier epoch could purchase")
            work.enqueue(db, "after-recovery", "lucy", "Prepare a stock brief.")
            assert run_once(db, OfflineShopModel())["status"] == "DONE"
            assert (
                db.connection.execute(
                    "SELECT history_complete FROM assistant_daily WHERE session='lucy'"
                ).fetchone()[0]
                == 0
            )
            assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == snapshot_hash
            with sqlite3.connect(supplier_path) as remote:
                assert remote.execute("SELECT count(*) FROM orders").fetchone()[0] == 2
            return {
                "same_inode": True,
                "old_connection_refused": True,
                "restored_local_orders": 1,
                "reconciled_orders": 2,
                "spent_pence": 2600,
                "vanilla_on_hand": 8,
                "strawberry_on_order": 4,
                "fresh_work": "DONE",
                "history_complete": False,
                "backup_unchanged": True,
            }
        finally:
            if observer is not None:
                observer.close()
            db.close()


def main():
    checkpoint_dir = Path(__file__).resolve().parent
    if not (checkpoint_dir / "ch08.py").exists():
        checkpoint_dir = Path("book/always_on/checkpoints")
    supplier_process = runpy.run_path(str(checkpoint_dir / "ch08.py"))["supplier_process"]
    with tempfile.TemporaryDirectory(prefix="lucy-maintenance-") as directory:
        result = experiment(Path(directory), supplier_process)
    unit = unit_text(
        Path("/srv/lucy/state"), Path("/srv/lucy/releases/one/.venv/bin/sovereign-agent")
    )
    assert "Restart=on-failure" in unit and "TimeoutStopSec=90" in unit
    print("Snapshot retained; original database inode preserved:", result["same_inode"])
    print("Old open connection and supplier epoch refused:", result["old_connection_refused"])
    print(
        "Local orders after restore / reconciled:",
        result["restored_local_orders"],
        result["reconciled_orders"],
    )
    print("Recovered expenditure:", result["spent_pence"], "pence")
    print(
        "Vanilla on hand / strawberry pending:",
        result["vanilla_on_hand"],
        result["strawberry_on_order"],
    )
    print(
        "Fresh work:",
        result["fresh_work"],
        "; historical model usage complete:",
        result["history_complete"],
    )
    print("Systemd host operations: NOT RUN by this portable checkpoint")


if __name__ == "__main__":
    main()
