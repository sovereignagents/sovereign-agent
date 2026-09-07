"""Challenge assignment identity, shared allowance, cancellation and actual worker routing."""

import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import replace

import pytest

from reference_organizations.store.agent import OfflineShopModel, seed_lucy
from reference_organizations.store.assistant import run_once as shop_once
from reference_organizations.store.delegation import (
    Inquiry,
    OfflineCateringModel,
    delegate,
    quote,
    run_once,
)
from sovereign_agent.assistant_orders import propose
from sovereign_agent.assistant_service import unit_text
from sovereign_agent.assistant_work import (
    assert_current,
    cancel,
    claim,
    enqueue,
    finish,
    reserve_model_call,
)
from sovereign_agent.cli import main
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ModelTurn, ToolCall


def setup(tmp_path, **limits):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    parent = enqueue(db, "catering-inquiry", "lucy", "Prepare the stock brief.")
    deadline = time.time() + 120
    child = delegate(db, parent, Inquiry(sku="SKU-VANILLA", guests=40), deadline=deadline, **limits)
    return db, parent, child, deadline


def test_quote_has_authored_boundary_expectations(tmp_path):
    db, _, _, _ = setup(tmp_path)
    for guests, tubs, total in [(1, 1, 500), (10, 1, 500), (11, 2, 1000), (200, 20, 10000)]:
        result = quote(db, Inquiry(sku="SKU-VANILLA", guests=guests))
        assert (result["tubs"], result["total_pence"], result["currency"]) == (tubs, total, "GBP")
    for guests in [0, 201, True]:
        with pytest.raises(ValueError):
            Inquiry(sku="SKU-VANILLA", guests=guests)
    db.close()


def test_duplicate_handoff_is_identical_and_contract_cannot_change(tmp_path):
    db, parent, child, deadline = setup(tmp_path)
    other = Database(db.path)
    assert (
        delegate(other, parent, Inquiry(sku="SKU-VANILLA", guests=40), deadline=deadline) == child
    )
    with pytest.raises(ValueError):
        delegate(other, parent, Inquiry(sku="SKU-VANILLA", guests=41), deadline=deadline)
    with pytest.raises(PermissionError):
        delegate(other, child, Inquiry(sku="SKU-VANILLA", guests=40), deadline=deadline)
    with pytest.raises(sqlite3.IntegrityError):
        with db.immediate() as connection:
            connection.execute("UPDATE assistant_delegations SET budget_pence=999")
    assert db.connection.execute("SELECT count(*) FROM assistant_delegations").fetchone()[0] == 1
    other.close()
    db.close()


def test_handoff_rolls_back_on_event_failure(tmp_path, monkeypatch):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    parent = enqueue(db, "parent", "lucy", "brief")

    def crash(*args, **kwargs):
        raise RuntimeError("crash at handoff")

    monkeypatch.setattr("reference_organizations.store.delegation.append_event", crash)
    with pytest.raises(RuntimeError):
        delegate(db, parent, Inquiry(sku="SKU-VANILLA", guests=40), deadline=time.time() + 60)
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 1
    assert db.connection.execute("SELECT count(*) FROM assistant_delegations").fetchone()[0] == 0
    db.close()


def test_research_and_stock_have_separate_claims_and_one_delivery_result(tmp_path):
    db, parent, child, _ = setup(tmp_path)
    other = Database(db.path)

    class ConcurrentModel(OfflineCateringModel):
        def complete(self, messages, tools, **kwargs):
            assert [t["function"]["name"] for t in tools] == ["catering_quote"]
            if len(messages) == 2:
                assert shop_once(other, OfflineShopModel())["status"] == "DONE"
            return super().complete(messages, tools, **kwargs)

    result = run_once(db, ConcurrentModel(), identifier=child)
    assert result["status"] == "DONE"
    assert result["report"]["quote"]["total_pence"] == 2000
    assert result["report"]["loop"]["model_calls"] == 2
    assert result["report"]["baseline"]["model_calls"] == 0
    assert run_once(other, OfflineCateringModel(), identifier=child) == {"status": "IDLE"}
    assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 0
    assert (
        db.connection.execute("SELECT status FROM assistant_work WHERE id=?", (parent,)).fetchone()[
            0
        ]
        == "DONE"
    )
    assert (
        db.connection.execute(
            "SELECT model_calls FROM assistant_daily WHERE session='lucy'"
        ).fetchone()[0]
        == 5
    )
    other.close()
    db.close()


def test_model_cannot_expand_tools_or_purchase_at_core_boundary(tmp_path):
    db, _, child, _ = setup(tmp_path)
    work = claim(db, "research", role="research", identifier=child)
    with pytest.raises(PermissionError):
        propose(db, work, "SKU-VANILLA", 6)
    with pytest.raises(PermissionError):
        assert_current(db.connection, replace(work, role="shop"))
    finish(db, work, "BLOCKED", "probe complete")
    with db.immediate() as connection:
        connection.execute(
            "UPDATE assistant_work SET status='READY',available_after=0 WHERE id=?", (child,)
        )

    class HostileModel:
        def complete(self, messages, tools, **kwargs):
            if messages[-1]["role"] != "tool":
                return ModelTurn(calls=(ToolCall(id="buy", name="propose_order", arguments={}),))
            return ModelTurn(content="I purchased everything.")

    result = run_once(db, HostileModel())
    assert result["status"] == "BLOCKED"
    assert (
        result["report"]["loop"]["messages"][-2]["content"]
        == '{"ok": false, "error": "tool_not_allowed"}'
    )
    assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 0
    db.close()


def test_shared_daily_allowance_rolls_back_child_counter_when_exhausted(tmp_path):
    db, _, child, _ = setup(tmp_path, estimated_call_pence=7)
    work = claim(db, "research", role="research", identifier=child)
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_daily SET model_calls=99 WHERE session='lucy'")
    reserve_model_call(db, work, 7)
    with pytest.raises(PermissionError):
        reserve_model_call(db, work, 7)
    assert db.connection.execute("SELECT model_calls FROM assistant_delegations").fetchone()[0] == 1
    assert (
        db.connection.execute(
            "SELECT estimated_cost_pence FROM assistant_work WHERE id=?", (child,)
        ).fetchone()[0]
        == 7
    )
    db.close()


def test_assignment_allowance_survives_replacement_and_estimate_cannot_change(tmp_path):
    db, _, child, _ = setup(tmp_path, model_calls=1, estimated_call_pence=5)
    first = claim(db, "old", role="research", identifier=child)
    with pytest.raises(PermissionError):
        reserve_model_call(db, first, 0)
    reserve_model_call(db, first, 5)
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_work SET expires=0 WHERE id=?", (child,))
    replacement = claim(db, "new", role="research", identifier=child)
    with pytest.raises(PermissionError):
        reserve_model_call(db, replacement, 5)
    with pytest.raises(PermissionError):
        finish(db, first, "DONE", "stale result")
    assert replacement.generation == first.generation + 1
    db.close()


def test_parent_cancel_during_model_call_prevents_tool_and_result(tmp_path):
    db, parent, child, _ = setup(tmp_path)
    other = Database(db.path)

    class CancellingModel(OfflineCateringModel):
        def complete(self, messages, tools, **kwargs):
            cancel(other, parent)
            return super().complete(messages, tools, **kwargs)

    assert run_once(db, CancellingModel())["status"] == "AUTHORITY_STOP"
    assert (
        db.connection.execute("SELECT status FROM assistant_work WHERE id=?", (child,)).fetchone()[
            0
        ]
        == "CANCELLED"
    )
    assert db.connection.execute("SELECT count(*) FROM assistant_transcript").fetchone()[0] == 0
    other.close()
    db.close()


def test_deadline_cancels_without_model_call(tmp_path, monkeypatch):
    db, _, child, deadline = setup(tmp_path)
    monkeypatch.setattr("reference_organizations.store.delegation.time.time", lambda: deadline + 1)
    assert run_once(db, OfflineCateringModel()) == {"status": "IDLE"}
    assert (
        db.connection.execute("SELECT status FROM assistant_work WHERE id=?", (child,)).fetchone()[
            0
        ]
        == "CANCELLED"
    )
    db.close()


def test_cli_assignment_routes_to_separate_real_unattended_worker(tmp_path, capsys):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    parent = enqueue(db, "parent", "lucy", "brief")
    assert main(["agent", "delegate", parent, "--root", str(tmp_path), "--guests", "41"]) == 0
    child = json.loads(capsys.readouterr().out)["work"]
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("SOVEREIGN_AGENT_")
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "sovereign_agent",
            "agent",
            "serve",
            "--research-worker",
            "--root",
            str(tmp_path),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = db.connection.execute(
                "SELECT status,result FROM assistant_work WHERE id=?", (child,)
            ).fetchone()
            if row[0] == "DONE":
                break
            time.sleep(0.02)
        assert row[0] == "DONE" and "GBP 25.00" in row[1]
        assert (
            db.connection.execute(
                "SELECT status FROM assistant_work WHERE id=?", (parent,)
            ).fetchone()[0]
            == "READY"
        )
    finally:
        process.terminate()
        process.communicate(timeout=5)
        db.close()


def test_separate_service_uses_separate_operator_environment(tmp_path):
    executable = tmp_path / "sovereign-agent"
    text = unit_text(tmp_path, executable, research=True)
    assert "--research-worker" in text and "/research.env" in text
    assert "/agent.env" not in text


def test_graceful_stop_requeues_without_resetting_assignment_usage(tmp_path):
    db, _, child, _ = setup(tmp_path)
    stopping = False

    class StopAfterReply(OfflineCateringModel):
        def complete(self, messages, tools, **kwargs):
            nonlocal stopping
            stopping = True
            return super().complete(messages, tools, **kwargs)

    assert run_once(db, StopAfterReply(), should_stop=lambda: stopping)["status"] == "STOPPED"
    assert (
        db.connection.execute("SELECT status FROM assistant_work WHERE id=?", (child,)).fetchone()[
            0
        ]
        == "READY"
    )
    result = run_once(db, OfflineCateringModel())
    assert result["status"] == "DONE"
    assert result["report"]["assignment_usage"]["model_calls"] == 3
    db.close()


def test_assignment_cost_limit_and_forged_billing_session_are_refused(tmp_path):
    db, _, child, _ = setup(tmp_path, estimated_call_pence=60, budget_pence=100)
    work = claim(db, "research", role="research", identifier=child)
    with pytest.raises(PermissionError):
        reserve_model_call(db, replace(work, session="different-account"), 60)
    reserve_model_call(db, work, 60)
    with pytest.raises(PermissionError):
        reserve_model_call(db, work, 60)
    assert (
        db.connection.execute(
            "SELECT estimated_cost_pence FROM assistant_daily WHERE session='lucy'"
        ).fetchone()[0]
        == 60
    )
    db.close()


def test_model_cannot_change_the_catering_inquiry(tmp_path):
    db, _, _, _ = setup(tmp_path)

    class ChangedInquiryModel:
        def complete(self, messages, tools, **kwargs):
            if messages[-1]["role"] != "tool":
                return ModelTurn(
                    calls=(
                        ToolCall(
                            id="changed",
                            name="catering_quote",
                            arguments={"sku": "SKU-CHOCOLATE", "guests": 200},
                        ),
                    )
                )
            return ModelTurn(content="The changed quote is ready.")

    result = run_once(db, ChangedInquiryModel())
    assert result["status"] == "BLOCKED"
    assert result["report"]["quote"] is None
    db.close()


def test_cancelling_completed_parent_stops_child_without_undoing_stock_result(tmp_path):
    db, parent, child, _ = setup(tmp_path)
    assert shop_once(db, OfflineShopModel())["status"] == "DONE"
    cancel(db, parent)
    assert run_once(db, OfflineCateringModel()) == {"status": "IDLE"}
    assert (
        db.connection.execute("SELECT status FROM assistant_work WHERE id=?", (parent,)).fetchone()[
            0
        ]
        == "DONE"
    )
    assert (
        db.connection.execute("SELECT status FROM assistant_work WHERE id=?", (child,)).fetchone()[
            0
        ]
        == "CANCELLED"
    )
    db.close()
