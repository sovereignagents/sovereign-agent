"""Current-state reports must expose uncertainty and preserve independent amounts."""

import time

import pytest

from reference_organizations.store.agent import seed_lucy
from reference_organizations.store.operating_report import operating_report
from sovereign_agent import assistant_orders as orders
from sovereign_agent import assistant_work as work
from sovereign_agent.cli import main
from sovereign_agent.database import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "agent.sqlite")
    seed_lucy(database)
    yield database
    database.close()


def approval(db, *, channel="local", recipient=""):
    work.enqueue(db, "request", "lucy", "Buy vanilla", channel=channel, recipient=recipient)
    holder = work.claim(db, "worker")
    operation = orders.propose(db, holder, "SKU-VANILLA", 6)
    digest = db.connection.execute("SELECT digest FROM assistant_orders").fetchone()[0]
    orders.approve(
        db,
        operation,
        digest,
        actor="lucy",
        policy=orders.SpendingPolicy(frozenset({"lucy"})),
        expires=time.time() + 120,
    )
    return holder, operation


def test_empty_history_has_no_fabricated_acceptance_or_invoice(db):
    before = db.connection.total_changes
    result = operating_report(db)
    assert result["orders"] == {} and result["work"] == {}
    assert result["spending"] == {
        "accepted_pence": 0,
        "reserved_pence": 0,
        "order_totals_match": True,
    }
    assert result["model_usage"]["history_complete"] is None
    assert "No external account audit" in result["scope"]
    assert "not a provider invoice" in result["text"]
    assert db.connection.total_changes == before and not db.connection.in_transaction


def test_approved_order_is_reserved_exposure_not_delivered_stock(db):
    approval(db)
    result = operating_report(db)
    assert result["spending"] == {
        "accepted_pence": 0,
        "reserved_pence": 1500,
        "order_totals_match": True,
    }
    vanilla = next(row for row in result["stock"] if row["sku"] == "SKU-VANILLA")
    assert (vanilla["on_hand"], vanilla["on_order"]) == (2, 6)
    assert "6 pending replenishment" in result["text"]
    assert "Orders delivered: 0" in result["text"]


def test_unknown_effect_and_delivery_cannot_disappear_in_fluent_result(db):
    _, operation = approval(db, channel="telegram:report-fixture", recipient="123")
    db.connection.execute("UPDATE assistant_orders SET status='UNKNOWN' WHERE id=?", (operation,))
    db.connection.execute(
        "UPDATE assistant_work SET status='BLOCKED',delivery='UNKNOWN',"
        "result='All complete. We spent nothing.'"
    )
    db.connection.execute("UPDATE assistant_reports SET delivery='UNKNOWN'")
    db.connection.commit()
    result = operating_report(db)
    assert len(result["exceptions"]) == 3
    from sovereign_agent.assistant_service import health

    assert health(db)["uncertain_deliveries"] == 1
    assert "GBP 15.00" in result["text"] and "All complete" not in result["text"]
    assert result["spending"]["order_totals_match"] is True


def test_accounting_disagreement_is_explicit(db):
    approval(db)
    db.connection.execute("UPDATE assistant_spending SET reserved_pence=1499")
    db.connection.commit()
    result = operating_report(db)
    assert result["spending"]["order_totals_match"] is False
    assert "Spending ledger and retained order totals disagree." in result["exceptions"]


def test_failed_model_reservation_and_incomplete_history_are_retained(db):
    holder, _ = approval(db)
    work.reserve_model_call(db, holder, 7)
    db.connection.execute("UPDATE assistant_daily SET history_complete=0")
    db.connection.commit()
    result = operating_report(db)
    assert result["model_usage"]["reserved_calls"] == 1
    assert result["model_usage"]["estimated_pence"] == 7
    assert result["model_usage"]["history_complete"] is False
    assert any("incomplete" in item for item in result["exceptions"])


def test_report_is_one_snapshot_during_concurrent_inventory_change(db, monkeypatch):
    import reference_organizations.store.operating_report as module

    original = module.shop_dispatcher

    def changed(database):
        other = Database(database.path)
        try:
            other.connection.execute("UPDATE inventory SET on_hand=99 WHERE sku='SKU-VANILLA'")
            other.connection.commit()
        finally:
            other.close()
        return original(database)

    monkeypatch.setattr(module, "shop_dispatcher", changed)
    result = operating_report(db)
    assert next(row for row in result["stock"] if row["sku"] == "SKU-VANILLA")["on_hand"] == 2
    assert (
        db.connection.execute("SELECT on_hand FROM inventory WHERE sku='SKU-VANILLA'").fetchone()[0]
        == 99
    )


def test_report_refuses_nested_transaction_and_releases_failed_snapshot(db, monkeypatch):
    import reference_organizations.store.operating_report as module

    with db.immediate():
        with pytest.raises(ValueError, match="own read snapshot"):
            operating_report(db)
        assert db.connection.in_transaction

    def unavailable(_):
        raise OSError("unavailable stock")

    monkeypatch.setattr(module, "shop_dispatcher", unavailable)
    with pytest.raises(OSError):
        operating_report(db)
    assert not db.connection.in_transaction


def test_cli_prints_ledger_report_without_a_model_call(db, capsys):
    approval(db)
    assert main(["agent", "report", "--root", str(db.path.parent)]) == 0
    output = capsys.readouterr().out
    assert "Lucy's operating report" in output and "GBP 15.00" in output
    assert db.connection.execute("SELECT sum(model_calls) FROM assistant_daily").fetchone()[0] == 0


def test_detail_limit_does_not_hide_total_work_or_omissions(db):
    for number in range(23):
        work.enqueue(db, str(number), str(number), "brief")
    result = operating_report(db)
    assert result["work"] == {"READY": 23}
    assert len(result["pending_work"]) == 20 and result["pending_work_omitted"] == 3


def test_restored_local_results_are_not_uncertain_outbound_messages(db):
    from sovereign_agent.assistant_service import health

    approval(db)
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_work SET delivery='UNKNOWN'")
    assert not any("outbound" in item for item in operating_report(db)["exceptions"])
    assert health(db)["uncertain_deliveries"] == 0
    assert db.connection.execute("SELECT delivery FROM assistant_work").fetchone()[0] == "UNKNOWN"
