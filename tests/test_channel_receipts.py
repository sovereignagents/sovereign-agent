"""Malformed channel data cannot crash parsing or counterfeit a durable delivery receipt."""

import json

import pytest

from sovereign_agent import assistant_work as work
from sovereign_agent import telegram_channel as channel
from sovereign_agent.database import Database
from sovereign_agent.http_transport import HTTPResult


def update(identifier=1):
    return {
        "update_id": identifier,
        "message": {
            "from": {"id": 123},
            "chat": {"id": 123, "type": "private"},
            "text": "Prepare a brief",
        },
    }


class Bot:
    account = "shape-test"

    def __init__(self, updates):
        self.updates = updates
        self.sent = []

    def call(self, method, data):
        if method == "getUpdates":
            return self.updates
        self.sent.append(data)
        return {"message_id": 901}


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        {"update_id": 2, "message": None},
        {"update_id": 2, "message": {"from": []}},
        {"update_id": 2, "message": {"chat": None}},
    ],
)
def test_malformed_batch_rolls_back_and_releases_poller_lease(tmp_path, bad):
    db = Database(tmp_path / "agent.sqlite")
    bot = Bot([update(), bad])
    with pytest.raises(ValueError, match="Telegram"):
        channel.poll(db, bot, frozenset({123}))
    for table in ("assistant_work", "assistant_channel_cursor", "assistant_channel_leases"):
        assert db.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    bot.updates = [update()]
    assert len(channel.poll(db, bot, frozenset({123}))) == 1
    db.close()


@pytest.mark.parametrize("payload", [None, [], True, {"ok": True}])
def test_malformed_api_envelope_raises_sanitized_transport_error(monkeypatch, payload):
    monkeypatch.setattr(
        channel, "request", lambda *a, **k: HTTPResult(200, json.dumps(payload).encode())
    )
    with pytest.raises(OSError, match="Telegram request failed"):
        channel.Telegram("123:PRIVATE_SENTINEL").call("getUpdates", {})


def test_boolean_chat_id_cannot_match_numeric_operator(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    incoming = update()
    incoming["message"]["from"]["id"] = 1
    incoming["message"]["chat"]["id"] = True
    assert channel.poll(db, Bot([incoming]), frozenset({1})) == []
    assert db.connection.execute("SELECT offset FROM assistant_channel_cursor").fetchone()[0] == 2
    db.close()


def ready(db):
    identifier = work.enqueue(
        db, "request", "lucy", "brief", channel="telegram:shape-test", recipient="123"
    )
    current = work.claim(db, "worker", identifier=identifier)
    work.finish(db, current, "DONE", "No purchase was made.")
    return identifier


def test_successful_receipt_is_durable_once_and_contains_no_raw_response(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    identifier = ready(db)
    bot = Bot([])
    assert channel.deliver_one(db, bot, frozenset({123})) == "SENT"
    db.close()
    db = Database(db.path)
    assert channel.deliver_one(db, bot, frozenset({123})) is None
    events = db.connection.execute(
        "SELECT payload FROM events WHERE kind='assistant.channel.sent'"
    ).fetchall()
    assert len(events) == 1
    assert json.loads(events[0][0]) == {
        "work": identifier,
        "channel": "telegram:shape-test",
        "recipient": "123",
        "message_id": 901,
        "report": 1,
    }
    assert len(bot.sent) == 1
    db.close()


@pytest.mark.parametrize("message_id", [False, 0, -1, "901"])
def test_invalid_receipt_is_unknown_and_not_repeated(tmp_path, message_id):
    db = Database(tmp_path / "agent.sqlite")
    ready(db)
    bot = Bot([])
    bot.call = lambda *a: {"message_id": message_id}
    assert channel.deliver_one(db, bot, frozenset({123})) == "UNKNOWN"
    assert channel.deliver_one(db, bot, frozenset({123})) is None
    assert (
        db.connection.execute(
            "SELECT count(*) FROM events WHERE kind='assistant.channel.sent'"
        ).fetchone()[0]
        == 0
    )
    db.close()


def test_changed_delivery_state_cannot_gain_a_stale_success_event(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    identifier = ready(db)
    other = Database(db.path)
    bot = Bot([])

    def accepted_after_state_changed(*args):
        with other.immediate() as connection:
            connection.execute(
                "UPDATE assistant_reports SET delivery='UNKNOWN' WHERE work_id=?", (identifier,)
            )
        return {"message_id": 901}

    bot.call = accepted_after_state_changed
    assert channel.deliver_one(db, bot, frozenset({123})) == "UNKNOWN"
    assert (
        db.connection.execute(
            "SELECT count(*) FROM events WHERE kind='assistant.channel.sent'"
        ).fetchone()[0]
        == 0
    )
    other.close()
    db.close()


def test_receipt_event_failure_keeps_ambiguous_sending_without_repeating(tmp_path, monkeypatch):
    db = Database(tmp_path / "agent.sqlite")
    identifier = ready(db)
    bot = Bot([])

    def fail(*args):
        raise RuntimeError("failed local receipt commit")

    monkeypatch.setattr(channel, "append_event", fail)
    with pytest.raises(RuntimeError, match="receipt commit"):
        channel.deliver_one(db, bot, frozenset({123}))
    assert (
        db.connection.execute(
            "SELECT delivery FROM assistant_work WHERE id=?", (identifier,)
        ).fetchone()[0]
        == "SENDING"
    )
    assert channel.deliver_one(db, bot, frozenset({123})) is None
    assert len(bot.sent) == 1
    db.close()
