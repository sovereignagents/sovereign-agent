"""Process-level proof at the remote-commit / local-receipt boundary."""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time

import pytest

from reference_organizations.store.agent import OfflineShopModel, seed_lucy
from reference_organizations.store.assistant import reconcile_once, run_once
from sovereign_agent import assistant_orders as orders
from sovereign_agent import assistant_work as work
from sovereign_agent.agent_loop import Limits, run_loop
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ModelTurn, ToolCall


def wait_until(check, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.02)
    pytest.fail("bounded process observation timed out")


@pytest.mark.parametrize("hard_kill", [False, True])
def test_process_stops_after_supplier_commit_and_recovers_before_new_work(tmp_path, hard_kill):
    ready, committed = tmp_path / "ready", tmp_path / "committed"
    supplier_db = tmp_path / "supplier.sqlite"
    supplier = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "reference_organizations.store.supplier",
            "--database",
            str(supplier_db),
            "--port",
            "0",
            "--ready",
            str(ready),
            "--committed",
            str(committed),
            "--hold-response-seconds",
            "4",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    agent = replacement = None
    try:
        wait_until(ready.exists)
        root = tmp_path / "agent"
        root.mkdir()
        db = Database(root / "agent.sqlite")
        seed_lucy(db)
        # One shortage keeps the process experiment's accounting independent.
        with db.immediate() as connection:
            connection.execute("UPDATE inventory SET on_hand=10 WHERE sku='SKU-STRAWBERRY'")
        first = work.enqueue(db, "first", "lucy", "stock")
        command = [
            sys.executable,
            "-m",
            "sovereign_agent",
            "agent",
            "serve",
            "--root",
            str(root),
            "--supplier",
            "http://127.0.0.1:" + ready.read_text(),
            "--automatic-pence",
            "2000",
        ]
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("SOVEREIGN_AGENT_")
        }
        agent = subprocess.Popen(
            command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        wait_until(committed.exists)
        operation = committed.read_text()
        agent.send_signal(signal.SIGKILL if hard_kill else signal.SIGTERM)
        output, error = agent.communicate(timeout=6)
        assert agent.returncode == (-signal.SIGKILL if hard_kill else 0), error
        row = db.connection.execute("SELECT * FROM assistant_orders").fetchone()
        assert row["id"] == operation
        assert row["status"] == ("SENDING" if hard_kill else "UNKNOWN")
        assert (
            db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0]
            == 1500
        )
        if not hard_kill:
            assert b"STOPPED" in output
        # Accelerate lease/backoff expiry; no wall-clock minute is needed in a lab.
        with db.immediate() as connection:
            connection.execute(
                "UPDATE assistant_work SET expires=0,available_after=0 WHERE id=?", (first,)
            )
        later = work.enqueue(db, "later", "other-session", "stock")
        replacement = subprocess.Popen(
            command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        wait_until(
            lambda: (
                db.connection.execute("SELECT status FROM assistant_orders").fetchone()[0]
                == "CONFIRMED"
            )
        )
        replacement.send_signal(signal.SIGTERM)
        output, error = replacement.communicate(timeout=6)
        assert replacement.returncode == 0, error
        # First recovered service pass refers to the old work, before the new turn.
        passes = [json.loads(line) for line in output.splitlines() if line.startswith(b'{"status"')]
        assert passes[-1] == {"status": "DONE", "work": first}
        assert all(
            item["work"] == first or item == {"status": "RECOVERY_WAIT", "work": None}
            for item in passes
        )
        assert all(item["status"] in {"BLOCKED", "RECOVERY_WAIT", "DONE"} for item in passes)
        assert (
            db.connection.execute(
                "SELECT status FROM assistant_work WHERE id=?", (later,)
            ).fetchone()[0]
            == "READY"
        )
        with sqlite3.connect(supplier_db) as independent:
            assert independent.execute("SELECT operation FROM orders").fetchall() == [(operation,)]
        assert tuple(
            db.connection.execute(
                "SELECT reserved_pence,spent_pence FROM assistant_spending"
            ).fetchone()
        ) == (0, 1500)
    finally:
        for process in (agent, replacement, supplier):
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)


class AcceptedSupplier:
    identity, timeout, idempotent = "lucy-local", 1, True

    def __init__(self):
        self.sent = []
        self.receipts = {}

    def lookup(self, identifier):
        return self.receipts.get(identifier)

    def order(self, identifier, proposal):
        self.sent.append(identifier)
        receipt = {"operation": identifier, "proposal": proposal, "status": "ACCEPTED"}
        self.receipts[identifier] = receipt
        return receipt


def prepared(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    work.enqueue(db, "first", "lucy", "stock")
    claim = work.claim(db, "first")
    identifiers = [orders.propose(db, claim, sku, 1) for sku in ("SKU-VANILLA", "SKU-STRAWBERRY")]
    policy = orders.SpendingPolicy(frozenset({"lucy"}))
    for identifier in identifiers:
        digest = db.connection.execute(
            "SELECT digest FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone()[0]
        orders.approve(
            db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60
        )
    return db, claim, identifiers, policy


def test_reconciliation_finishes_all_approved_orders_without_model(tmp_path):
    db, claim, identifiers, policy = prepared(tmp_path)
    supplier = AcceptedSupplier()
    proposal = json.loads(
        db.connection.execute(
            "SELECT proposal FROM assistant_orders WHERE id=?", (identifiers[0],)
        ).fetchone()[0]
    )
    supplier.receipts[identifiers[0]] = {
        "operation": identifiers[0],
        "proposal": proposal,
        "status": "ACCEPTED",
    }
    with db.immediate() as connection:
        connection.execute(
            "UPDATE assistant_orders SET status='UNKNOWN' WHERE id=?", (identifiers[0],)
        )
        connection.execute("UPDATE assistant_work SET expires=0 WHERE id=?", (claim.id,))
    result = reconcile_once(db, supplier, policy)
    assert result["status"] == "DONE"
    assert supplier.sent == [identifiers[1]]
    assert {r[0] for r in db.connection.execute("SELECT status FROM assistant_orders")} == {
        "CONFIRMED"
    }


def test_stop_drains_one_effect_without_starting_the_next(tmp_path):
    db, claim, identifiers, policy = prepared(tmp_path)
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_work SET expires=0 WHERE id=?", (claim.id,))
    supplier = AcceptedSupplier()
    result = run_once(
        db,
        OfflineShopModel(),
        supplier=supplier,
        policy=policy,
        should_stop=lambda: bool(supplier.sent),
    )
    assert result["status"] == "BLOCKED"
    assert len(supplier.sent) == 1
    assert sorted(r[0] for r in db.connection.execute("SELECT status FROM assistant_orders")) == [
        "APPROVED",
        "CONFIRMED",
    ]
    assert "No purchases made" not in result["answer"]


def test_stop_after_model_response_dispatches_no_tools(tmp_path):
    from reference_organizations.store.agent import shop_dispatcher

    stopped = False

    class Model:
        def complete(self, *args, **kwargs):
            nonlocal stopped
            stopped = True
            return ModelTurn(calls=(ToolCall(id="stock", name="list_stock", arguments={}),))

    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    result = run_loop(
        Model(), shop_dispatcher(db), [], limits=Limits(), should_stop=lambda: stopped
    )
    assert result.status == "STOP_REQUESTED" and result.tool_calls == 0


def test_control_messages_survive_full_normal_backlog(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    for i in range(21):
        work.enqueue(db, f"normal:{i}", "phone", "stock", channel="telegram:one", recipient="42")
    identifier = work.enqueue(
        db, "control:1", "phone", "/revoke missing", channel="telegram:one", recipient="42"
    )
    result = run_once(
        db, OfflineShopModel(), policy=orders.SpendingPolicy(frozenset({"42"})), control_only=True
    )
    assert result["work"] == identifier and result["status"] == "DONE"
    row = db.connection.execute("SELECT admitted,controls FROM assistant_daily").fetchone()
    assert tuple(row) == (20, 1)
