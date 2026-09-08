"""Current elder counterexamples: successive reports, interrupts and uncertain authority."""

import json
import sqlite3
import time

import pytest

from reference_organizations.store.agent import seed_lucy
from sovereign_agent import assistant_orders as orders
from sovereign_agent import assistant_work as work
from sovereign_agent.assistant_service import health
from sovereign_agent.database import Database
from sovereign_agent.telegram_channel import deliver_one


@pytest.mark.parametrize("failure", [KeyboardInterrupt, SystemExit])
def test_interrupted_transaction_cannot_later_commit(tmp_path, failure):
    db = Database(tmp_path / "agent.sqlite")
    with pytest.raises(failure):
        with db.immediate() as connection:
            connection.execute("UPDATE assistant_control SET paused=1")
            raise failure()
    assert not db.connection.in_transaction
    db.connection.commit()
    other = Database(db.path)
    assert other.connection.execute("SELECT paused FROM assistant_control").fetchone()[0] == 0
    other.close()
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_control SET paused=1")
    assert not db.connection.in_transaction


def test_failed_begin_preserves_original_lock_error(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    other = Database(db.path)
    other.connection.execute("PRAGMA busy_timeout=1")
    with db.immediate():
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            with other.immediate():
                pytest.fail("must not acquire an already held write lock")
    assert not other.connection.in_transaction
    with other.immediate():
        pass


def report_context(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    identifier = work.enqueue(db, "one", "lucy", "order", channel="telegram:123", recipient="123")
    owner = work.claim(db, "first")
    work.finish(db, owner, "BLOCKED", "Approve the exact draft.")
    return db, identifier


def next_report(db, identifier, status="DONE", text="Order confirmed."):
    with db.immediate() as connection:
        connection.execute(
            "UPDATE assistant_work SET status='READY',available_after=0 WHERE id=?", (identifier,)
        )
    owner = work.claim(db, "next", identifier=identifier)
    work.finish(db, owner, status, text)


@pytest.mark.parametrize("late", [False, True])
def test_approval_and_final_report_have_independent_receipts(tmp_path, late):
    db, identifier = report_context(tmp_path)
    other = Database(db.path)
    sent = []

    class Bot:
        account = "123"

        def call(self, method, data):
            sent.append(data["text"])
            if late and len(sent) == 1:
                next_report(other, identifier)
            return {"message_id": len(sent), "private_extra": "do not retain"}

    assert deliver_one(db, Bot(), frozenset({123})) == "SENT"
    if not late:
        next_report(other, identifier)
    rows = db.connection.execute("SELECT id,delivery FROM assistant_reports ORDER BY id").fetchall()
    assert [tuple(row) for row in rows] == [(1, "SENT"), (2, "PENDING")]
    assert deliver_one(other, Bot(), frozenset({123})) == "SENT"
    assert deliver_one(db, Bot(), frozenset({123})) is None
    assert sent == ["Approve the exact draft.", "Order confirmed."]
    assert [
        json.loads(row[0])
        for row in db.connection.execute("SELECT receipt FROM assistant_reports ORDER BY id")
    ] == [{"message_id": 1}, {"message_id": 2}]
    events = [
        json.loads(row[0])
        for row in db.connection.execute(
            "SELECT payload FROM events WHERE kind='assistant.channel.sent' ORDER BY seq"
        )
    ]
    assert [event["report"] for event in events] == [1, 2]


def test_unknown_report_does_not_prevent_new_report_or_replay_old_one(tmp_path):
    db, identifier = report_context(tmp_path)

    class Bot:
        account = "123"

        def call(self, *args):
            raise TimeoutError()

    assert deliver_one(db, Bot(), frozenset({123})) == "UNKNOWN"
    next_report(db, identifier)
    next_report(db, identifier)  # Unchanged reconciliation report does not spam.
    assert db.connection.execute("SELECT count(*) FROM assistant_reports").fetchone()[0] == 2
    assert health(db)["uncertain_deliveries"] == 1
    assert deliver_one(db, Bot(), frozenset({123})) == "UNKNOWN"
    assert deliver_one(db, Bot(), frozenset({123})) is None
    assert health(db)["uncertain_deliveries"] == 2
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.connection.execute("UPDATE assistant_reports SET body='rewritten'")
    db.connection.rollback()


class Supplier:
    idempotent = True
    identity = "lucy-local"
    timeout = 1
    calls = 0
    available = False

    def lookup(self, operation):
        return None

    def order(self, operation, proposal):
        self.calls += 1
        if not self.available:
            raise TimeoutError()
        return {"operation": operation, "proposal": proposal, "status": "ACCEPTED"}


def uncertain(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    work.enqueue(db, "first", "lucy", "order")
    owner = work.claim(db, "worker")
    identifier = orders.propose(db, owner, "SKU-VANILLA", 6)
    row = db.connection.execute("SELECT * FROM assistant_orders").fetchone()
    policy = orders.SpendingPolicy(frozenset({"lucy"}))
    orders.approve(
        db, identifier, row["digest"], actor="lucy", policy=policy, expires=time.time() + 60
    )
    supplier = Supplier()
    assert orders.execute(db, owner, identifier, supplier, policy=policy)["status"] == "UNKNOWN"
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_orders SET approved_until=0")
    return db, owner, row, policy, supplier


@pytest.mark.parametrize("uncertain_state", ["UNKNOWN", "SENDING"])
def test_expired_unknown_can_renew_same_identity_without_double_reserving(
    tmp_path, uncertain_state
):
    db, owner, row, policy, supplier = uncertain(tmp_path)
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_orders SET status=?", (uncertain_state,))
    with pytest.raises(PermissionError, match="approval required"):
        orders.execute(db, owner, row["id"], supplier, policy=policy)
    orders.approve(
        db,
        row["id"],
        row["digest"],
        actor="lucy",
        policy=policy,
        expires=time.time() + 60,
        supplier=supplier,
    )
    assert (
        db.connection.execute("SELECT status FROM assistant_orders").fetchone()[0]
        == uncertain_state
    )
    assert (
        db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0] == 1500
    )
    supplier.available = True
    assert orders.execute(db, owner, row["id"], supplier, policy=policy)["status"] == "ACCEPTED"
    assert supplier.calls == 2
    assert tuple(
        db.connection.execute(
            "SELECT reserved_pence,spent_pence FROM assistant_spending"
        ).fetchone()
    ) == (0, 1500)


@pytest.mark.parametrize(
    "mutation", ["non_idempotent", "target", "revoked", "cancelled", "automatic"]
)
def test_unknown_renewal_cannot_expand_authority(tmp_path, mutation):
    db, owner, row, policy, supplier = uncertain(tmp_path)
    if mutation == "non_idempotent":
        supplier.idempotent = False
    elif mutation == "target":
        supplier.identity = "other"
    elif mutation == "revoked":
        orders.revoke(db, row["id"], actor="lucy", policy=policy)
    elif mutation == "cancelled":
        work.cancel(db, owner.id)
    with pytest.raises(PermissionError):
        orders.approve(
            db,
            row["id"],
            row["digest"],
            actor="lucy",
            policy=policy,
            expires=time.time() + 60,
            supplier=supplier,
            automatic=mutation == "automatic",
        )
    assert (
        db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0] == 1500
    )


@pytest.mark.parametrize("outcome", ["ACCEPTED", "REJECTED"])
def test_operator_exact_receipt_resolves_cancelled_unknown_once(tmp_path, outcome):
    db, owner, row, policy, supplier = uncertain(tmp_path)
    work.cancel(db, owner.id)
    receipt = {"operation": row["id"], "proposal": json.loads(row["proposal"]), "status": outcome}
    kwargs = dict(
        target=row["target"],
        evidence="supplier signed closure reference 42",
        actor="lucy",
        policy=policy,
    )
    for _ in range(2):
        assert orders.resolve(db, row["id"], row["digest"], receipt, **kwargs) == receipt
    assert tuple(
        db.connection.execute(
            "SELECT reserved_pence,spent_pence FROM assistant_spending"
        ).fetchone()
    ) == (0, 1500 if outcome == "ACCEPTED" else 0)
    for kind in ("assistant.order.resolved", "assistant.order.reconciled"):
        assert (
            db.connection.execute("SELECT count(*) FROM events WHERE kind=?", (kind,)).fetchone()[0]
            == 1
        )
    with pytest.raises(ValueError, match="contradicts"):
        orders.resolve(
            db,
            row["id"],
            row["digest"],
            {**receipt, "status": "REJECTED" if outcome == "ACCEPTED" else "ACCEPTED"},
            **kwargs,
        )
    assert supplier.calls == 1


@pytest.mark.parametrize(
    "mutation", ["actor", "digest", "target", "proposal", "operation", "status"]
)
def test_operator_resolution_refuses_mismatched_or_inconclusive_evidence(tmp_path, mutation):
    db, owner, row, policy, supplier = uncertain(tmp_path)
    receipt = {
        "operation": row["id"],
        "proposal": json.loads(row["proposal"]),
        "status": "REJECTED",
    }
    kwargs = dict(target=row["target"], evidence="supplier closure", actor="lucy", policy=policy)
    digest = row["digest"]
    if mutation in kwargs:
        kwargs[mutation] = "untrusted"
    elif mutation == "digest":
        digest = "different"
    else:
        receipt[mutation] = "NOT_PLACED"
    with pytest.raises((ValueError, PermissionError)):
        orders.resolve(db, row["id"], digest, receipt, **kwargs)
    assert (
        db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0] == 1500
    )


def test_saturated_clock_defers_without_rejected_work_or_repeated_notice(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    for n in range(20):
        work.enqueue(db, str(n), "lucy", "brief", now=10)
    work.schedule(db, "morning", "lucy", "brief", first_due=10, interval_seconds=60)
    assert work.tick(db, now=10) == work.tick(db, now=70) == []
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 20
    assert db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == 10
    assert (
        db.connection.execute(
            "SELECT count(*) FROM events WHERE kind='assistant.job.deferred'"
        ).fetchone()[0]
        == 1
    )
    owner = work.claim(db, "worker", now=71)
    work.finish(db, owner, "DONE", "done", now=72)
    assert len(work.tick(db, now=73)) == 1
    assert db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == 130


def test_version_25_upgrade_preserves_sent_and_uncertain_report_states(tmp_path, monkeypatch):
    import sovereign_agent.database as storage

    migrations = storage.MIGRATIONS
    monkeypatch.setattr(storage, "MIGRATIONS", tuple(item for item in migrations if item[0] < 26))
    db = Database(tmp_path / "agent.sqlite")
    for name, state in (("delivered", "SENT"), ("ambiguous", "UNKNOWN")):
        with db.immediate() as connection:
            connection.execute(
                "INSERT INTO assistant_work(id,origin,session,prompt,created,status,result,"
                "channel,recipient,delivery) VALUES (?,?,?,?,0,'DONE',?,'telegram:123','123',?)",
                (name, name, name, "brief", name, state),
            )
    db.close()
    monkeypatch.setattr(storage, "MIGRATIONS", migrations)
    reopened = Database(db.path)
    assert [
        tuple(row)
        for row in reopened.connection.execute(
            "SELECT work_id,body,delivery FROM assistant_reports ORDER BY id"
        )
    ] == [("delivered", "delivered", "SENT"), ("ambiguous", "ambiguous", "UNKNOWN")]
    assert 26 in reopened.applied_versions()
    assert health(reopened)["uncertain_deliveries"] == 1


def test_failed_restore_copy_can_retry_without_unfencing_old_worker(tmp_path, monkeypatch):
    from sovereign_agent import assistant_service as service

    db = Database(tmp_path / "agent.sqlite")
    work.enqueue(db, "one", "lucy", "brief")
    owner = work.claim(db, "old")
    snapshot = service.backup(db, tmp_path / "snapshot.sqlite")
    original = sqlite3.connect

    class FailCopy(sqlite3.Connection):
        def backup(self, target, **kwargs):
            if target is db.connection:
                raise sqlite3.OperationalError("injected disk copy failure")
            return super().backup(target, **kwargs)

    def connection(*args, **kwargs):
        return original(*args, factory=FailCopy, **kwargs)

    monkeypatch.setattr(service.sqlite3, "connect", connection)
    with pytest.raises(sqlite3.OperationalError, match="disk copy"):
        service.restore(db, snapshot)
    with pytest.raises(PermissionError):
        work.assert_current(db.connection, owner)
    monkeypatch.setattr(service.sqlite3, "connect", original)
    service.restore(db, snapshot)
    assert health(db)["paused"]
    assert (
        db.path.with_suffix(".authority").read_text()
        == db.connection.execute("SELECT epoch FROM assistant_control").fetchone()[0]
    )
    with pytest.raises(PermissionError):
        work.assert_current(db.connection, owner)


def test_two_product_phone_request_delivers_approval_then_final_report(tmp_path):
    from reference_organizations.store.agent import OfflineShopModel
    from reference_organizations.store.assistant import run_once

    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    identifier = work.enqueue(
        db, "phone:1", "telegram:123:123", "replenish", channel="telegram:123", recipient="123"
    )
    policy = orders.SpendingPolicy(frozenset({"123"}))
    supplier = Supplier()
    supplier.available = True
    sent = []

    class Bot:
        account = "123"

        def call(self, method, data):
            sent.append(data["text"])
            return {"message_id": len(sent)}

    assert run_once(db, OfflineShopModel(), supplier=supplier, policy=policy)["status"] == "BLOCKED"
    assert deliver_one(db, Bot(), frozenset({123})) == "SENT"
    for row in db.connection.execute("SELECT id,digest FROM assistant_orders").fetchall():
        orders.approve(
            db, row["id"], row["digest"], actor="123", policy=policy, expires=time.time() + 60
        )
    with db.immediate() as connection:
        connection.execute(
            "UPDATE assistant_work SET status='READY',available_after=0 WHERE id=?", (identifier,)
        )
    assert run_once(db, OfflineShopModel(), supplier=supplier, policy=policy)["status"] == "DONE"
    assert deliver_one(db, Bot(), frozenset({123})) == "SENT"
    assert (
        len(sent) == 2
        and sent[0].count("Approval required") == 2
        and sent[1].count("CONFIRMED") == 2
    )
    assert supplier.calls == 2
