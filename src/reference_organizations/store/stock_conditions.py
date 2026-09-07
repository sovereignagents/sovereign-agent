"""One durable work item per positive stock-need episode, with enforced SKU scope."""

from __future__ import annotations

import math
import time

from reference_organizations.store.agent import shop_dispatcher
from sovereign_agent.assistant_work import IntakeLimitError, _enqueue
from sovereign_agent.database import Database
from sovereign_agent.events import append_event
from sovereign_agent.model_turn import ToolCall


def watch(
    db: Database,
    identifier: str,
    session: str,
    sku: str,
    *,
    channel: str = "local",
    recipient: str = "",
) -> None:
    if any(
        not isinstance(value, str) or not value.strip() or len(value) > 100
        for value in (identifier, session, sku)
    ):
        raise ValueError("bounded condition identity, session and product required")
    if (
        len(channel) > 200
        or len(recipient) > 200
        or not (
            (channel == "local" and not recipient)
            or (channel.startswith("telegram:") and recipient.isdigit())
        )
    ):
        raise ValueError("local output or an explicit Telegram recipient required")
    with db.immediate() as connection:
        if not connection.execute(
            "SELECT 1 FROM inventory i JOIN products p ON p.sku=i.sku WHERE i.sku=?", (sku,)
        ).fetchone():
            raise ValueError("condition requires a known product with inventory")
        if connection.execute(
            "SELECT 1 FROM assistant_stock_conditions WHERE subject=? AND enabled=1 AND id!=?",
            (sku, identifier),
        ).fetchone():
            raise ValueError("one active stock condition per product is allowed")
        previous = connection.execute(
            "SELECT * FROM assistant_stock_conditions WHERE id=?", (identifier,)
        ).fetchone()
        if previous:
            if (
                previous["session"],
                previous["subject"],
                previous["channel"],
                previous["recipient"],
            ) != (session, sku, channel, recipient):
                raise ValueError("condition identity already binds another scope or route")
            if not previous["enabled"]:
                connection.execute(
                    "UPDATE assistant_stock_conditions SET enabled=1,armed=1 WHERE id=?",
                    (identifier,),
                )
        else:
            if (
                connection.execute("SELECT count(*) FROM assistant_stock_conditions").fetchone()[0]
                >= 100
            ):
                raise ValueError("teaching implementation supports at most 100 stock conditions")
            connection.execute(
                "INSERT INTO assistant_stock_conditions(id,session,subject,channel,recipient) "
                "VALUES (?,?,?,?,?)",
                (identifier, session, sku, channel, recipient),
            )


def disable(db: Database, identifier: str) -> None:
    with db.immediate() as connection:
        if (
            connection.execute(
                "UPDATE assistant_stock_conditions SET enabled=0 WHERE id=?", (identifier,)
            ).rowcount
            != 1
        ):
            raise ValueError("unknown stock condition")


def scan(db: Database, *, now: float | None = None, maximum: int = 100) -> list[str]:
    now = time.time() if now is None else now
    if not math.isfinite(now) or type(maximum) is not int or not 1 <= maximum <= 100:
        raise ValueError("finite observation time and bounded scan required")
    emitted = []
    with db.immediate() as connection:
        if connection.execute("SELECT paused FROM assistant_control WHERE id=1").fetchone()[0]:
            return []
        for condition in connection.execute(
            "SELECT * FROM assistant_stock_conditions WHERE enabled=1 ORDER BY id"
        ).fetchall():
            stock = shop_dispatcher(db, subject=condition["subject"]).invoke(
                ToolCall(id="condition-observation", name="list_stock", arguments={})
            )
            if not stock["ok"] or not stock["value"]:
                raise ValueError("condition inventory observation is unavailable")
            if stock["value"][0]["needed"] == 0:
                connection.execute(
                    "UPDATE assistant_stock_conditions SET armed=1 WHERE id=?", (condition["id"],)
                )
                continue
            if not condition["armed"]:
                continue
            generation = condition["generation"] + 1
            try:
                work = _enqueue(
                    connection,
                    f"stock-condition:{condition['id']}:{generation}",
                    condition["session"],
                    f"Prepare a replenishment draft for {condition['subject']} from current stock. "
                    "State GBP amounts.",
                    now,
                    condition["channel"],
                    condition["recipient"],
                    subject=condition["subject"],
                    require_admission=True,
                )
            except IntakeLimitError:
                continue  # Capacity did not admit work; leave this episode armed.
            connection.execute(
                "UPDATE assistant_stock_conditions SET armed=0,generation=? WHERE id=?",
                (generation, condition["id"]),
            )
            append_event(
                db,
                "assistant.stock_condition.triggered",
                {
                    "condition": condition["id"],
                    "subject": condition["subject"],
                    "generation": generation,
                    "work": work,
                },
            )
            emitted.append(work)
            if len(emitted) >= maximum:
                break
    return emitted
