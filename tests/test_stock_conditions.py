"""Stock episodes coalesce atomically and their durable product scope reaches tools."""

import json
import os
import subprocess
import sys
import time
from dataclasses import replace

import pytest

from reference_organizations.store.agent import OfflineShopModel, seed_lucy, shop_dispatcher
from reference_organizations.store.assistant import run_once
from reference_organizations.store.stock_conditions import disable, scan, watch
from sovereign_agent.assistant_orders import propose
from sovereign_agent.assistant_work import assert_current, cancel, claim, enqueue
from sovereign_agent.cli import main
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ModelTurn, ToolCall
from sovereign_agent.telegram_channel import deliver_one


def setup(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    watch(db, "vanilla-low", "lucy", "SKU-VANILLA")
    return db


def test_episode_coalesces_across_connections_and_rearms_after_false(tmp_path):
    db = setup(tmp_path)
    first = scan(db)
    other = Database(db.path)
    assert len(first) == 1 and scan(other) == []
    watch(other, "vanilla-low", "lucy", "SKU-VANILLA")
    assert scan(db) == []
    result = run_once(db, OfflineShopModel())
    assert result["status"] == "DONE"
    assert "SKU-VANILLA" in result["answer"] and "SKU-STRAWBERRY" not in result["answer"]
    observations = [
        json.loads(m["content"]) for m in result["loop"]["messages"] if m["role"] == "tool"
    ]
    assert [row["sku"] for row in observations[0]["value"]] == ["SKU-VANILLA"]
    with db.immediate() as connection:
        connection.execute("UPDATE inventory SET on_hand=8 WHERE sku='SKU-VANILLA'")
    assert scan(other) == []
    with db.immediate() as connection:
        connection.execute("UPDATE inventory SET on_hand=1 WHERE sku='SKU-VANILLA'")
    second = scan(other)
    assert len(second) == 1 and second != first
    assert (
        db.connection.execute("SELECT generation FROM assistant_stock_conditions").fetchone()[0]
        == 2
    )
    other.close()
    db.close()


def test_condition_and_intake_rollback_together(tmp_path, monkeypatch):
    db = setup(tmp_path)

    def crash(*args, **kwargs):
        raise RuntimeError("crash before condition commit")

    monkeypatch.setattr("reference_organizations.store.stock_conditions.append_event", crash)
    with pytest.raises(RuntimeError):
        scan(db)
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 0
    assert tuple(
        db.connection.execute("SELECT armed,generation FROM assistant_stock_conditions").fetchone()
    ) == (1, 0)
    db.close()


def test_capacity_defers_without_consuming_or_rejecting_the_episode(tmp_path):
    db = setup(tmp_path)
    queued = [enqueue(db, f"ordinary:{number}", "lucy", "brief") for number in range(20)]
    assert scan(db) == []
    assert tuple(
        db.connection.execute("SELECT armed,generation FROM assistant_stock_conditions").fetchone()
    ) == (1, 0)
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 20
    cancel(db, queued[0])
    assert len(scan(db)) == 1
    assert (
        db.connection.execute(
            "SELECT count(*) FROM assistant_work WHERE status='REJECTED'"
        ).fetchone()[0]
        == 0
    )
    db.close()


def test_product_scope_is_enforced_by_claim_tools_and_effect_boundary(tmp_path):
    db = setup(tmp_path)
    scan(db)
    work = claim(db, "worker")
    assert work.subject == "SKU-VANILLA"
    with pytest.raises(PermissionError):
        assert_current(db.connection, replace(work, subject="SKU-STRAWBERRY"))
    with pytest.raises(PermissionError):
        propose(db, work, "SKU-STRAWBERRY", 4)
    result = shop_dispatcher(db, subject=work.subject).invoke(
        ToolCall(id="outside", name="supplier", arguments={"sku": "SKU-STRAWBERRY"})
    )
    assert result["ok"] is False
    with pytest.raises(ValueError, match="different content"):
        enqueue(db, "stock-condition:vanilla-low:1", "lucy", work.prompt, subject="SKU-STRAWBERRY")
    db.close()


def test_disabled_or_paused_conditions_do_not_consume_an_episode(tmp_path):
    db = setup(tmp_path)
    disable(db, "vanilla-low")
    assert scan(db) == []
    watch(db, "vanilla-low", "lucy", "SKU-VANILLA")
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_control SET paused=1")
    assert scan(db) == []
    assert db.connection.execute("SELECT armed FROM assistant_stock_conditions").fetchone()[0] == 1
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_control SET paused=0")
    assert len(scan(db)) == 1
    disable(db, "vanilla-low")
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 1
    db.close()


def test_cli_watch_flows_into_a_scoped_worker_turn(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SOVEREIGN_AGENT_MODEL_MODE", raising=False)
    assert main(["agent", "watch-stock", "SKU-VANILLA", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "WATCHING"
    assert main(["agent", "work", "--root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DONE" and "SKU-STRAWBERRY" not in result["answer"]
    db = Database(tmp_path / "agent.sqlite")
    assert (
        db.connection.execute("SELECT subject FROM assistant_work").fetchone()[0] == "SKU-VANILLA"
    )
    db.close()


def test_unattended_process_consumes_a_persisted_condition_without_a_prompt(tmp_path):
    db = setup(tmp_path)
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("SOVEREIGN_AGENT_")
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "sovereign_agent", "agent", "serve", "--root", str(tmp_path)],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and process.poll() is None:
            row = db.connection.execute(
                "SELECT subject,status,result FROM assistant_work"
            ).fetchone()
            if row and row["status"] == "DONE":
                break
            time.sleep(0.02)
        row = db.connection.execute("SELECT subject,status,result FROM assistant_work").fetchone()
        assert row is not None and row["subject"] == "SKU-VANILLA" and row["status"] == "DONE"
        assert "SKU-STRAWBERRY" not in row["result"]
        assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 0
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
        db.close()


def test_another_condition_cannot_duplicate_the_same_product_need(tmp_path):
    db = setup(tmp_path)
    with pytest.raises(ValueError, match="one active stock condition"):
        watch(db, "another-name", "another-session", "SKU-VANILLA")
    assert len(scan(db)) == 1
    db.close()


def test_condition_output_reaches_its_configured_operator_channel(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    watch(
        db,
        "vanilla-phone",
        "telegram:test:123",
        "SKU-VANILLA",
        channel="telegram:test",
        recipient="123",
    )
    scan(db)
    assert run_once(db, OfflineShopModel())["status"] == "DONE"

    class Bot:
        account = "test"
        sent = []

        def call(self, method, data):
            assert method == "sendMessage"
            self.sent.append(data)
            return {"message_id": 1}

    bot = Bot()
    assert deliver_one(db, bot, frozenset({123})) == "SENT"
    assert bot.sent[0]["chat_id"] == 123 and "SKU-VANILLA" in bot.sent[0]["text"]
    assert deliver_one(db, bot, frozenset({123})) is None
    db.close()


def test_scoped_work_cannot_finish_with_only_a_fluent_recommendation(tmp_path):
    db = setup(tmp_path)
    scan(db)

    class DescriptionOnly:
        def complete(self, *args, **kwargs):
            return ModelTurn("Vanilla needs six tubs; I will draft it.")

    result = run_once(db, DescriptionOnly())
    assert result["loop"]["status"] == "COMPLETED"
    assert result["status"] == "BLOCKED"
    assert db.connection.execute("SELECT status FROM assistant_work").fetchone()[0] == "BLOCKED"
    db.close()
