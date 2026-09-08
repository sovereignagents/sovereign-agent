"""Adversarial regressions drawn from both reviews in org issue 603."""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest

from reference_organizations.store.agent import seed_lucy
from sovereign_agent import relay, supervisor
from sovereign_agent.agent_loop import Limits, run_loop
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose
from sovereign_agent.assistant_work import (
    claim,
    enqueue,
    reserve_model_call,
    schedule,
    tick,
)
from sovereign_agent.database import Database
from sovereign_agent.ids import utc_now
from sovereign_agent.model_turn import ModelError
from sovereign_agent.telegram_channel import Telegram, poll
from sovereign_agent.tool_dispatch import Dispatcher


@pytest.mark.parametrize("reader", ["inbox", "supervisor"])
def test_expiry_sweep_cannot_overwrite_fresh_claim_from_stale_read(tmp_path, reader):
    db = Database(tmp_path / "state.sqlite")
    message = relay.send(db, "sender", "recipient", "stock", "brief")
    relay.claim(db, message.id, "recipient")
    expired = (utc_now() - timedelta(hours=1)).isoformat()
    with db.transaction():
        db.connection.execute(
            "UPDATE messages SET claim_expires_at=?,"
            "record=json_set(record,'$.claim_expires_at',?) WHERE id=?",
            (expired, expired, message.id),
        )
    stale_record = db.connection.execute(
        "SELECT record FROM messages WHERE id=?", (message.id,)
    ).fetchall()
    stale_id = db.connection.execute("SELECT id FROM messages WHERE id=?", (message.id,)).fetchall()
    second = Database(db.path)
    fresh = relay.claim(second, message.id, "recipient")
    actual = db.connection

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class Connection:
        def __getattr__(self, name):
            return getattr(actual, name)

        def __setattr__(self, name, value):
            if name == "isolation_level":
                actual.isolation_level = value
            else:
                object.__setattr__(self, name, value)

        def execute(self, sql, args=()):
            if sql == "SELECT record FROM messages WHERE recipient = ?":
                return Cursor(stale_record)
            if sql.startswith("SELECT id FROM messages WHERE state"):
                return Cursor(stale_id)
            return actual.execute(sql, args)

    db.connection = Connection()
    try:
        if reader == "inbox":
            relay.inbox(db, "recipient")
        else:
            assert supervisor.sweep_expired_mailbox_claims(db) == []
        row = actual.execute("SELECT * FROM messages WHERE id=?", (message.id,)).fetchone()
        assert row["state"] == "CLAIMED" and row["fencing_token"] == fresh.fencing_token
        assert (
            actual.execute(
                "SELECT count(*) FROM events WHERE kind='message.claim_swept'"
            ).fetchone()[0]
            == 0
        )
    finally:
        db.connection = actual


def test_immediate_does_not_silently_commit_someone_elses_transaction(tmp_path):
    db = Database(tmp_path / "state.sqlite")
    db.connection.execute("INSERT INTO assistant_daily(session,day) VALUES ('lucy',1)")
    with pytest.raises(RuntimeError):
        with db.immediate():
            pass
    assert db.connection.in_transaction
    db.connection.rollback()
    reopened = Database(db.path)
    assert reopened.connection.execute("SELECT count(*) FROM assistant_daily").fetchone()[0] == 0


def test_two_schedulers_coalesce_one_occurrence_after_long_outage(tmp_path):
    db = Database(tmp_path / "state.sqlite")
    schedule(db, "morning", "lucy", "brief", first_due=0, interval_seconds=60)
    barrier = Barrier(2)

    def contender():
        other = Database(db.path)
        barrier.wait(timeout=5)
        return tick(other, now=10800)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: contender(), range(2)))
    assert sum(map(len, results)) == 1
    assert db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == 10860
    assert tick(db, now=10000) == []  # Wall-clock rollback cannot replay the occurrence.


def test_backlog_and_daily_model_limits_survive_restart(tmp_path):
    db = Database(tmp_path / "state.sqlite")
    for i in range(21):
        enqueue(db, f"msg:{i}", "lucy", "brief")
    rows = db.connection.execute(
        "SELECT status,count(*) FROM assistant_work GROUP BY status"
    ).fetchall()
    assert dict(rows) == {"READY": 20, "REJECTED": 1}
    work = claim(Database(db.path), "worker")
    for _ in range(100):
        reserve_model_call(db, work, 1)
    with pytest.raises(PermissionError):
        reserve_model_call(Database(db.path), work, 1)
    row = db.connection.execute("SELECT * FROM assistant_daily").fetchone()
    assert row["model_calls"] == 100 and row["estimated_cost_pence"] == 100


def test_unknown_model_call_retains_estimated_exposure():
    class LostModel:
        def complete(self, *args, **kwargs):
            raise ModelError("reply lost")

    result = run_loop(
        LostModel(),
        Dispatcher([], allowed=frozenset()),
        [],
        limits=Limits(estimated_call_pence=7, model_budget_pence=10),
    )
    assert result.status == "MODEL_FAILED" and result.estimated_cost_pence == 7


def test_bot_account_namespace_and_duplicate_payload_conflict(tmp_path):
    db = Database(tmp_path / "state.sqlite")

    class Bot:
        def __init__(self, account, text="brief"):
            self.account, self.text = account, text

        def call(self, *args):
            return [
                {
                    "update_id": 1,
                    "message": {
                        "from": {"id": 123},
                        "chat": {"id": 123, "type": "private"},
                        "text": self.text,
                    },
                }
            ]

    assert len(poll(db, Bot("A"), frozenset({123}))) == 1
    assert len(poll(db, Bot("B"), frozenset({123}))) == 1
    with pytest.raises(ValueError):
        poll(db, Bot("A", "changed"), frozenset({123}))
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 2


def test_second_poller_refuses_before_network_and_token_never_leaks(tmp_path, monkeypatch, capsys):
    db = Database(tmp_path / "state.sqlite")
    sentinel = "123:SENTINEL_PRIVATE_TOKEN"
    bot = Telegram(sentinel)
    with db.immediate() as connection:
        connection.execute(
            "INSERT INTO assistant_channel_leases VALUES (?,?,?)",
            ("telegram:123", "other", time.time() + 60),
        )
    monkeypatch.setattr(
        "sovereign_agent.telegram_channel.request",
        lambda *a, **k: pytest.fail("second poller sent a request"),
    )
    with pytest.raises(PermissionError):
        poll(db, bot, frozenset({123}))

    def failed(*args, **kwargs):
        raise OSError(sentinel)

    monkeypatch.setattr("sovereign_agent.telegram_channel.request", failed)
    with pytest.raises(OSError) as caught:
        bot.call("getUpdates", {})
    assert sentinel not in str(caught.value)
    assert sentinel not in capsys.readouterr().out
    assert sentinel.encode() not in db.path.read_bytes()


def test_concurrent_reservations_cannot_overspend(tmp_path):
    db = Database(tmp_path / "state.sqlite")
    seed_lucy(db)
    orders = []
    for i in range(2):
        enqueue(db, f"order:{i}", f"session:{i}", "buy")
        work = claim(db, f"worker:{i}")
        identifier = propose(db, work, "SKU-VANILLA", 28)  # £70 each against £100 total.
        digest = db.connection.execute(
            "SELECT digest FROM assistant_orders WHERE id=?", (identifier,)
        ).fetchone()[0]
        orders.append((identifier, digest))
    policy = SpendingPolicy(frozenset({"lucy"}), total_pence=10000)
    barrier = Barrier(2)

    def contender(order):
        other = Database(db.path)
        barrier.wait(timeout=5)
        try:
            approve(other, *order, actor="lucy", policy=policy, expires=time.time() + 60)
            return True
        except PermissionError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(contender, orders)) == [False, True]
    assert (
        db.connection.execute("SELECT reserved_pence FROM assistant_spending").fetchone()[0] == 7000
    )


def test_changed_supplier_or_expired_worker_cannot_send(tmp_path):
    db = Database(tmp_path / "state.sqlite")
    seed_lucy(db)
    enqueue(db, "first", "lucy", "buy")
    work = claim(db, "worker")
    identifier = propose(db, work, "SKU-VANILLA", 6, target="original")
    digest = db.connection.execute("SELECT digest FROM assistant_orders").fetchone()[0]
    policy = SpendingPolicy(frozenset({"lucy"}))
    approve(db, identifier, digest, actor="lucy", policy=policy, expires=time.time() + 60)

    class Destination:
        identity = "changed"
        timeout = 3
        idempotent = True

        def order(self, *args):
            pytest.fail("unauthorized send")

        def lookup(self, *args):
            pytest.fail("wrong target lookup")

    with pytest.raises(PermissionError):
        execute(db, work, identifier, Destination(), policy=policy)
    Destination.identity = "original"
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_work SET expires=0")
    with pytest.raises(PermissionError):
        execute(db, work, identifier, Destination(), policy=policy)
