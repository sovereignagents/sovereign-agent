"""Failure experiments across database connections and an independent supplier."""

import sqlite3
import subprocess
import sys
import time

import pytest

from reference_organizations.store.agent import seed_lucy
from reference_organizations.store.supplier import SupplierClient
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose, revoke
from sovereign_agent.assistant_work import claim, enqueue, finish, schedule, tick
from sovereign_agent.database import Database


def test_intake_conflict_and_exclusive_session(tmp_path):
    db = Database(tmp_path / "state.db")
    first = enqueue(db, "phone:1", "lucy", "stock", now=10)
    assert enqueue(db, "phone:1", "lucy", "stock", now=11) == first
    with pytest.raises(ValueError):
        enqueue(db, "phone:1", "lucy", "buy", now=11)
    enqueue(db, "phone:2", "lucy", "next", now=12)
    one = claim(db, "one", now=13, ttl=2)
    other = Database(db.path)
    assert claim(other, "two", now=14) is None
    two = claim(other, "two", now=15, ttl=10)
    assert one.id == two.id and two.generation == one.generation + 1
    with pytest.raises(PermissionError):
        finish(db, one, "DONE", "stale", now=15)
    finish(other, two, "DONE", "current", now=16)
    assert claim(db, "one", now=17).prompt == "next"


def test_schedule_advances_with_work_and_coalesces(tmp_path):
    db = Database(tmp_path / "state.db")
    schedule(db, "morning", "lucy", "brief", first_due=10, interval_seconds=60)
    work = tick(db, now=190)
    assert len(work) == 1
    assert tick(Database(db.path), now=190) == []
    assert db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == 250
    assert claim(db, "worker", now=191).id == work[0]


def test_schedule_transaction_rolls_back_before_ack(tmp_path, monkeypatch):
    db = Database(tmp_path / "state.db")
    schedule(db, "morning", "lucy", "brief", first_due=10, interval_seconds=60)

    def fail(*args, **kwargs):
        raise RuntimeError("crash before commit")

    monkeypatch.setattr("sovereign_agent.assistant_work.append_event", fail)
    with pytest.raises(RuntimeError):
        tick(db, now=10)
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 0
    assert db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == 10


def order_context(tmp_path, target="lucy-local"):
    db = Database(tmp_path / "agent.db")
    seed_lucy(db)
    enqueue(db, "first", "lucy", "replenish")
    work = claim(db, "worker")
    identifier = propose(db, work, "SKU-VANILLA", 6, target=target)
    row = db.connection.execute(
        "SELECT * FROM assistant_orders WHERE id=?", (identifier,)
    ).fetchone()
    return db, work, identifier, row["digest"]


def test_exact_approval_and_cumulative_reservation(tmp_path):
    db, work, identifier, digest = order_context(tmp_path)
    policy = SpendingPolicy(frozenset({"lucy"}), total_pence=2000)
    with pytest.raises(PermissionError):
        approve(db, identifier, "changed", actor="lucy", policy=policy, expires=time.time() + 60)
    with pytest.raises(PermissionError):
        approve(db, identifier, digest, actor="model", policy=policy, expires=time.time() + 60)
    approve(db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60)
    approve(db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60)
    second = propose(db, work, "SKU-STRAWBERRY", 4)
    second_digest = db.connection.execute(
        "SELECT digest FROM assistant_orders WHERE id=?", (second,)
    ).fetchone()[0]
    with pytest.raises(PermissionError):
        approve(db, second, second_digest, actor="lucy", policy=policy, expires=time.time() + 60)
    assert (
        db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0] == 1500
    )
    revoke(db, identifier, actor="lucy", policy=policy)
    assert db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0] == 0


@pytest.fixture
def supplier(tmp_path):
    ready = tmp_path / "ready"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "reference_organizations.store.supplier",
            "--database",
            str(tmp_path / "supplier.db"),
            "--port",
            "0",
            "--ready",
            str(ready),
            "--drop-first-response",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(0.02)
        assert ready.exists(), process.communicate(timeout=1)
        yield SupplierClient("http://127.0.0.1:" + ready.read_text()), tmp_path / "supplier.db"
    finally:
        process.terminate()
        process.communicate(timeout=5)


def test_lost_supplier_response_then_restart_never_duplicates(tmp_path, supplier):
    db, work, identifier, digest = order_context(tmp_path, supplier[0].identity)
    policy = SpendingPolicy(frozenset({"lucy"}))
    approve(db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60)
    client, supplier_path = supplier
    result = execute(db, work, identifier, client, policy=policy)
    assert result["status"] == "UNKNOWN"
    with sqlite3.connect(supplier_path) as connection:
        assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
    # Kill ownership, then reopen independent client state. The receipt is at
    # the remote supplier, not copied into the agent database by the fixture.
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_work SET expires=0 WHERE id=?", (work.id,))
    replacement_db = Database(db.path)
    replacement = claim(replacement_db, "replacement")
    with pytest.raises(PermissionError):
        execute(db, work, identifier, client, policy=policy)
    recovered = execute(replacement_db, replacement, identifier, client, policy=policy)
    assert recovered["status"] == "ACCEPTED"
    assert execute(replacement_db, replacement, identifier, client, policy=policy) == recovered
    with sqlite3.connect(supplier_path) as connection:
        assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
    budget = replacement_db.connection.execute("SELECT * FROM assistant_spending").fetchone()
    assert (budget["reserved_pence"], budget["spent_pence"]) == (0, 1500)


def test_revocation_still_reconciles_already_accepted_order(tmp_path, supplier):
    db, work, identifier, digest = order_context(tmp_path, supplier[0].identity)
    policy = SpendingPolicy(frozenset({"lucy"}))
    approve(db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60)
    client, _ = supplier
    assert execute(db, work, identifier, client, policy=policy)["status"] == "UNKNOWN"
    revoke(db, identifier, actor="lucy", policy=policy)
    assert (
        db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0] == 1500
    )
    assert execute(db, work, identifier, client, policy=policy)["status"] == "ACCEPTED"


def test_unknown_without_discovery_never_retries(tmp_path):
    db, work, identifier, digest = order_context(tmp_path)
    approve(
        db,
        identifier,
        digest,
        actor="lucy",
        policy=SpendingPolicy(frozenset({"lucy"})),
        expires=time.time() + 60,
    )

    class BlindSupplier:
        idempotent = False
        identity = "lucy-local"
        timeout = 3
        calls = 0

        def order(self, *args):
            self.calls += 1
            raise TimeoutError()

        def lookup(self, *args):
            raise OSError("discovery unavailable")

    supplier = BlindSupplier()
    assert (
        execute(db, work, identifier, supplier, policy=SpendingPolicy(frozenset({"lucy"})))[
            "status"
        ]
        == "UNKNOWN"
    )
    assert (
        execute(db, work, identifier, supplier, policy=SpendingPolicy(frozenset({"lucy"})))[
            "status"
        ]
        == "UNKNOWN"
    )
    assert supplier.calls == 1
