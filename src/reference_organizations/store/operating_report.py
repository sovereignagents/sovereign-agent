"""A deterministic current-state report; prose is never an accounting source."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from reference_organizations.store.agent import shop_dispatcher
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ToolCall


def operating_report(db: Database) -> dict[str, Any]:
    """Read one SQLite snapshot. Retained totals are not daily revenue or cash profit."""
    connection = db.connection
    if connection.in_transaction:
        raise ValueError("report requires its own read snapshot")
    observed = time.time()
    day = int(observed // 86400)
    connection.execute("BEGIN")
    try:
        paused = bool(
            connection.execute("SELECT paused FROM assistant_control WHERE id=1").fetchone()[0]
        )
        work = dict(
            connection.execute("SELECT status,count(*) FROM assistant_work GROUP BY status")
        )
        orders = dict(
            connection.execute("SELECT status,count(*) FROM assistant_orders GROUP BY status")
        )
        totals = connection.execute(
            "SELECT coalesce(sum(CASE WHEN status IN ('CONFIRMED','DELIVERED') "
            "THEN amount ELSE 0 END),0),"
            "coalesce(sum(CASE WHEN status IN ('APPROVED','SENDING','UNKNOWN') "
            "THEN amount ELSE 0 END),0) "
            "FROM assistant_orders"
        ).fetchone()
        budget = connection.execute(
            "SELECT reserved_pence,spent_pence FROM assistant_spending WHERE id=1"
        ).fetchone()
        reserved, spent = (0, 0) if budget is None else tuple(budget)
        stock = shop_dispatcher(db).invoke(
            ToolCall(id="report-stock", name="list_stock", arguments={})
        )
        if not stock["ok"]:
            raise ValueError("current stock could not be read")
        usage = connection.execute(
            "SELECT coalesce(sum(model_calls),0),coalesce(sum(estimated_cost_pence),0),"
            "min(history_complete) "
            "FROM assistant_daily WHERE day=?",
            (day,),
        ).fetchone()
        pending = [
            dict(row)
            for row in connection.execute(
                "SELECT id,status,subject FROM assistant_work "
                "WHERE status IN ('READY','RUNNING','BLOCKED') "
                "ORDER BY created,id LIMIT 20"
            )
        ]
        recent = [
            dict(row)
            for row in connection.execute(
                "SELECT id,work_id,status,amount,proposal,approval_basis,revoked "
                "FROM assistant_orders "
                "ORDER BY created DESC,id LIMIT 20"
            )
        ]
        deliveries = dict(
            connection.execute(
                "SELECT delivery,count(*) FROM assistant_reports "
                "WHERE channel LIKE 'telegram:%' GROUP BY delivery"
            )
        )
        research = connection.execute(
            "SELECT count(*) FROM assistant_work WHERE role='research' AND status='DONE'"
        ).fetchone()[0]
    finally:
        connection.rollback()
    exceptions = []
    if paused:
        exceptions.append("Restored operation is paused for reconciliation.")
    if work.get("BLOCKED", 0):
        exceptions.append(f"{work['BLOCKED']} work item(s) are blocked; inspect their records.")
    uncertain = orders.get("SENDING", 0) + orders.get("UNKNOWN", 0)
    if uncertain:
        exceptions.append(f"{uncertain} supplier outcome(s) remain uncertain.")
    uncertain_delivery = deliveries.get("SENDING", 0) + deliveries.get("UNKNOWN", 0)
    if uncertain_delivery:
        exceptions.append(f"{uncertain_delivery} outbound delivery outcome(s) remain uncertain.")
    matching = (spent, reserved) == tuple(totals)
    if not matching:
        exceptions.append("Spending ledger and retained order totals disagree.")
    if usage[2] == 0:
        exceptions.append(
            "Historical model usage is incomplete; recorded usage is not the full bill."
        )
    report = {
        "schema_version": 1,
        "observed_at": datetime.fromtimestamp(observed, UTC).isoformat(),
        "scope": (
            "Current local snapshot; work, orders and spending cover all retained history. "
            "Model usage covers the current UTC day. No external account audit was performed."
        ),
        "paused": paused,
        "work": work,
        "orders": orders,
        "spending": {
            "accepted_pence": spent,
            "reserved_pence": reserved,
            "order_totals_match": matching,
        },
        "stock": stock["value"],
        "recent_orders": recent,
        "orders_omitted": max(0, sum(orders.values()) - len(recent)),
        "pending_work": pending,
        "pending_work_omitted": max(
            0, sum(work.get(s, 0) for s in ("READY", "RUNNING", "BLOCKED")) - len(pending)
        ),
        "research_quotes_completed": research,
        "model_usage": {
            "utc_day": datetime.fromtimestamp(observed, UTC).date().isoformat(),
            "reserved_calls": usage[0],
            "estimated_pence": usage[1],
            "history_complete": None if usage[2] is None else bool(usage[2]),
        },
        "exceptions": exceptions,
    }
    lines = [
        "Lucy's operating report",
        f"Observed: {report['observed_at']}",
        report["scope"],
        "",
        f"Supplier purchases accepted: GBP {spent // 100}.{spent % 100:02d}",
        f"Allowance reserved for pending orders: GBP {reserved // 100}.{reserved % 100:02d}",
        f"Orders delivered: {orders.get('DELIVERED', 0)}; "
        f"accepted and awaiting delivery: {orders.get('CONFIRMED', 0)}",
        f"Order drafts awaiting approval: {orders.get('DRAFT', 0)}; "
        f"uncertain supplier outcomes: {uncertain}",
        f"Work completed: {work.get('DONE', 0)}; blocked: {work.get('BLOCKED', 0)}; "
        f"cancelled: {work.get('CANCELLED', 0)}",
        f"Read-only research quotes completed: {research}",
        "",
        "Current stock:",
    ]
    for row in stock["value"]:
        name = json.dumps(row["sku"], ensure_ascii=True)
        lines.append(
            f"- {name}: {row['on_hand']} on hand, {row['reserved']} reserved, "
            f"{row['on_order']} pending replenishment, {row['needed']} still needed"
        )
    lines.extend(
        [
            "",
            f"Model calls reserved today: {usage[0]}; configured estimate: {usage[1]} pence. "
            "This is not a provider invoice.",
            "",
            "Exceptions requiring inspection:",
        ]
    )
    lines.extend(f"- {item}" for item in exceptions)
    if not exceptions:
        lines.append(
            "- No recorded exceptions in this local snapshot; "
            "external outcomes still require their own evidence."
        )
    if pending:
        lines.append("Pending work IDs: " + ", ".join(row["id"] for row in pending))
    lines.append(
        f"Evidence detail: {len(recent)} recent order records; "
        f"{report['orders_omitted']} older orders omitted from detail, included in totals."
    )
    report["text"] = "\n".join(lines)
    return report
