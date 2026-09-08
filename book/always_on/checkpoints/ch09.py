"""Chapter 9: an accepted order with a lost response and independent receipts."""

import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from reference_organizations.store.agent import seed_lucy
from reference_organizations.store.supplier import SupplierClient
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose
from sovereign_agent.assistant_work import claim, enqueue
from sovereign_agent.database import Database


@contextmanager
def independent_supplier(root):
    ready = root / "supplier-ready"
    supplier_path = root / "supplier.sqlite"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "reference_organizations.store.supplier",
            "--database",
            str(supplier_path),
            "--port",
            "0",
            "--ready",
            str(ready),
            "--drop-first-response",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.02)
        if not ready.exists():
            raise RuntimeError("independent supplier did not become ready")
        yield SupplierClient("http://127.0.0.1:" + ready.read_text()), supplier_path
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def spending(db):
    row = db.connection.execute(
        "SELECT reserved_pence,spent_pence FROM assistant_spending WHERE id=1"
    ).fetchone()
    return tuple(row)


def experiment(root):
    with independent_supplier(root) as (supplier, supplier_path):
        db = Database(root / "agent.sqlite")
        try:
            seed_lucy(db)
            enqueue(db, "chapter9:morning", "lucy", "Replenish vanilla")
            work = claim(db, "chapter9-worker")
            identifier = propose(db, work, "SKU-VANILLA", 6, target=supplier.identity)
            assert propose(db, work, "SKU-VANILLA", 6, target=supplier.identity) == identifier
            digest = db.connection.execute(
                "SELECT digest FROM assistant_orders WHERE id=?", (identifier,)
            ).fetchone()[0]
            policy = SpendingPolicy(frozenset({"lucy"}), total_pence=2000)
            approve(db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60)
            initial = execute(db, work, identifier, supplier, policy=policy)
            assert initial["status"] == "UNKNOWN"
            print("initial", initial["status"])
            print("reserved and spent", *spending(db))
            with sqlite3.connect(supplier_path) as remote:
                assert remote.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
            # Reopen the durable ledger while the same ownership claim remains valid.
            # Worker death and replacement are a separate Chapter 10 experiment.
            db.close()
            db = Database(root / "agent.sqlite")
            receipt = execute(db, work, identifier, supplier, policy=policy)
            assert receipt["status"] == "ACCEPTED"
            assert execute(db, work, identifier, supplier, policy=policy) == receipt
            status = db.connection.execute(
                "SELECT status FROM assistant_orders WHERE id=?", (identifier,)
            ).fetchone()[0]
            print("after reconciliation", receipt["status"], status)
            print("reserved and spent", *spending(db))
            with sqlite3.connect(supplier_path) as remote:
                count = remote.execute("SELECT count(*) FROM orders").fetchone()[0]
                assert count == 1
                print("supplier orders", count)
            assert spending(db) == (0, 1500)
        finally:
            db.close()


def main():
    with tempfile.TemporaryDirectory(prefix="lucy-chapter9-") as directory:
        experiment(Path(directory))


if __name__ == "__main__":
    main()
