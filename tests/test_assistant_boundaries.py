"""External-review regressions: intake, privacy, restore, deadlines, and tool identity."""

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from reference_organizations.store.agent import OfflineShopModel, seed_lucy
from reference_organizations.store.assistant import run_once
from sovereign_agent import assistant_context
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose
from sovereign_agent.assistant_service import backup, restore, unit_text
from sovereign_agent.assistant_work import assert_current, claim, enqueue
from sovereign_agent.database import Database
from sovereign_agent.http_transport import request
from sovereign_agent.mcp_client import MCPClient
from sovereign_agent.model_turn import HTTPModel
from sovereign_agent.telegram_channel import deliver_one, poll


def test_preferences_are_scoped_correctable_and_forgettable(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    assistant_context.remember(db, "lucy", "supplier", "A", "message:1")
    assistant_context.remember(db, "other", "supplier", "private", "message:2")
    assistant_context.remember(db, "lucy", "supplier", "B", "message:3")
    rows = assistant_context.preferences(Database(db.path), "lucy", "supplier")
    assert [(r["value"], r["source"]) for r in rows] == [("B", "message:3")]
    assistant_context.forget(db, "lucy", "supplier")
    assert assistant_context.preferences(db, "lucy") == []
    assert (
        db.connection.execute(
            "SELECT count(*) FROM assistant_preferences WHERE session='lucy'"
        ).fetchone()[0]
        == 0
    )


def test_skills_are_immutable_guidance_with_required_regressions(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    path = tmp_path / "opening.toml"
    path.write_text(
        'name="opening"\nversion="1"\ninstructions="Read stock before drafting."\n'
        'requires=["list_stock"]\n'
    )
    assistant_context.stage_skill(db, path)
    with pytest.raises(ValueError):
        assistant_context.activate_skill(
            db,
            "opening",
            "1",
            evaluate=lambda _: {"new": True},
            required_cases=frozenset({"old", "new"}),
        )
    assistant_context.activate_skill(
        db,
        "opening",
        "1",
        evaluate=lambda _: {"old": True, "new": True},
        required_cases=frozenset({"old", "new"}),
    )
    assert (
        "Read stock"
        in assistant_context.context(db, "lucy", "brief", allowed=frozenset({"list_stock"}))[0][
            "content"
        ]
    )
    assert (
        "Read stock"
        not in assistant_context.context(db, "lucy", "brief", allowed=frozenset())[0]["content"]
    )
    path.write_text(path.read_text().replace("Read stock before drafting.", "Spend all the money."))
    with pytest.raises(ValueError):
        assistant_context.stage_skill(db, path)
    assert (
        "Spend all"
        not in assistant_context.context(db, "lucy", "brief", allowed=frozenset({"list_stock"}))[0][
            "content"
        ]
    )


class FakeBot:
    def __init__(self, updates):
        self.updates = updates
        self.offsets = []
        self.sent = []

    def call(self, method, data):
        if method == "getUpdates":
            self.offsets.append(data["offset"])
            return self.updates
        self.sent.append(data)
        return {"message_id": 900}


def update(identifier, actor=123, text="brief"):
    return {
        "update_id": identifier,
        "message": {
            "from": {"id": actor, "is_bot": False},
            "chat": {"id": actor, "type": "private"},
            "text": text,
        },
    }


def test_telegram_commit_contains_executable_work_and_cursor(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    bot = FakeBot([update(101), update(102, actor=999)])
    ids = poll(db, bot, frozenset({123}))
    assert len(ids) == 1
    restarted = Database(db.path)
    assert poll(restarted, bot, frozenset({123})) == []
    assert bot.offsets == [0, 103]
    result = run_once(restarted, OfflineShopModel())
    assert result["status"] == "DONE"
    assert deliver_one(restarted, bot, frozenset({123})) == "SENT"
    assert deliver_one(restarted, bot, frozenset({123})) is None
    assert len(bot.sent) == 1 and bot.sent[0]["chat_id"] == 123


def test_telegram_bad_batch_does_not_advance_cursor(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    bot = FakeBot([update(101), {"update_id": "broken"}])
    with pytest.raises(ValueError):
        poll(db, bot, frozenset({123}))
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 0
    assert db.connection.execute("SELECT count(*) FROM assistant_channel_cursor").fetchone()[0] == 0
    bot.updates = [update(101), update(102)]
    assert len(poll(db, bot, frozenset({123}))) == 2
    assert bot.offsets == [0, 0]


def test_ambiguous_delivery_is_not_blindly_repeated(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    bot = FakeBot([update(1)])
    poll(db, bot, frozenset({123}))
    run_once(db, OfflineShopModel())

    class LostReply:
        def call(self, *args):
            raise TimeoutError("reply lost")

    assert deliver_one(db, LostReply(), frozenset({123})) == "UNKNOWN"
    assert deliver_one(Database(db.path), bot, frozenset({123})) is None
    assert not bot.sent


def test_restore_pauses_old_and_new_workers_and_obsolete_approval(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    enqueue(db, "first", "lucy", "order")
    original = claim(db, "original")
    identifier = propose(db, original, "SKU-VANILLA", 6)
    digest = db.connection.execute("SELECT digest FROM assistant_orders").fetchone()[0]
    approve(
        db,
        identifier,
        digest,
        actor="lucy",
        policy=SpendingPolicy(frozenset({"lucy"})),
        expires=time.time() + 60,
    )
    snapshot = backup(db, tmp_path / "snapshot.sqlite")
    other = Database(db.path)
    restore(db, snapshot)
    with pytest.raises(PermissionError):
        assert_current(other.connection, original)
    control = db.connection.execute("SELECT * FROM assistant_control").fetchone()
    assert control["paused"] == 1
    row = db.connection.execute("SELECT * FROM assistant_orders").fetchone()
    assert row["revoked"] == 1 and row["approved_until"] == 0

    class NoCall:
        def __getattr__(self, name):
            pytest.fail("restored runtime must not contact supplier")

    with pytest.raises(PermissionError):
        execute(Database(db.path), original, identifier, NoCall())
    with pytest.raises(FileExistsError):
        backup(db, snapshot)


def test_mcp_initialization_allowlist_and_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SOVEREIGN_AGENT_TELEGRAM_TOKEN", "SENTINEL_DO_NOT_INHERIT")
    with MCPClient(
        [sys.executable, "-m", "reference_organizations.store.mcp_server"],
        allowed=frozenset({"catalog"}),
        environment={},
    ) as client:
        result = client.invoke("catalog", {})
        assert "SKU-VANILLA" in result["content"][0]["text"]
        with pytest.raises(PermissionError):
            client.invoke("purchase", {})
        pid = client.process.pid
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    probe = tmp_path / "probe.py"
    probe.write_text(
        'import os,sys\nassert "SOVEREIGN_AGENT_TELEGRAM_TOKEN" not in os.environ\n'
        "from reference_organizations.store.mcp_server import main\nmain()\n"
    )
    with MCPClient(
        [sys.executable, str(probe)], allowed=frozenset({"catalog"}), environment={}
    ) as client:
        assert client.invoke("catalog", {})["isError"] is False


def test_mcp_hung_server_is_killed_on_initialization_failure():
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        MCPClient(
            [sys.executable, "-c", "import time;time.sleep(60)"],
            allowed=frozenset(),
            environment={},
            timeout=0.2,
        )
    assert time.monotonic() - start < 2


@pytest.fixture
def hostile_http():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.do_GET()

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            try:
                if self.path == "/slow":
                    for _ in range(100):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.05)
                elif self.path == "/large":
                    self.wfile.write(b"x" * 100_000)
                else:
                    self.wfile.write(
                        b'{"choices":[{"finish_reason":"stop","message":{"content":"brief"}}],"usage":{"completion_tokens":2}}'
                    )
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_bounds_total_slow_drip_and_response_bytes(hostile_http):
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        request(hostile_http + "/slow", timeout=0.25)
    assert time.monotonic() - start < 2
    with pytest.raises(OSError):
        request(hostile_http + "/large", maximum_bytes=128)
    assert (
        HTTPModel(hostile_http).complete([], [], timeout=2, max_output_tokens=10).content == "brief"
    )


def test_service_unit_refuses_expansion_and_names_explicit_run_path(tmp_path):
    from pathlib import Path

    unit = unit_text(tmp_path, Path("/usr/local/bin/sovereign-agent"))
    assert "agent serve --root" in unit and "Restart=on-failure" in unit
    assert "NoNewPrivileges=true" in unit
    with pytest.raises(ValueError):
        unit_text(Path("/tmp/with space"), Path("/usr/bin/sovereign-agent"))
