"""Lucy's deterministic shop tools and offline model, using the real ledger."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sovereign_agent.database import Database
from sovereign_agent.model_turn import Message, ModelTurn, ToolCall
from sovereign_agent.tool_dispatch import Dispatcher, ExecutableTool

CATALOG = (
    ("SKU-VANILLA", "Vanilla", 2, 8, 250),
    ("SKU-CHOCOLATE", "Chocolate", 12, 6, 300),
    ("SKU-STRAWBERRY", "Strawberry", 1, 5, 275),
)


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StockArguments(NoArguments):
    sku: str = Field(min_length=1, max_length=100)


class DraftArguments(StockArguments):
    quantity: int = Field(gt=0, le=1_000)


def seed_lucy(db: Database) -> None:
    """Initialize once; rerunning must not replenish stock or reset cash."""
    with db.immediate() as connection:
        for sku, name, stock, threshold, cost in CATALOG:
            connection.execute(
                "INSERT OR IGNORE INTO products(sku, record) VALUES (?, ?)",
                (
                    sku,
                    json.dumps(
                        {"sku": sku, "name": name, "unit_cost_cents": cost, "price_cents": 500}
                    ),
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO inventory"
                "(sku, on_hand, reserved, reorder_point, record) VALUES (?, ?, 0, ?, ?)",
                (sku, stock, threshold, json.dumps({"sku": sku})),
            )
        connection.execute(
            "INSERT OR IGNORE INTO cash_entries(id, amount_cents, record) "
            "VALUES ('cash-opening', 20000, ?)",
            (json.dumps({"reason": "opening"}),),
        )


def shop_dispatcher(db: Database, *, subject: str = "") -> Dispatcher:
    def list_stock(_: NoArguments) -> list[dict[str, Any]]:
        rows = [
            dict(row)
            for row in db.connection.execute(
                "SELECT i.sku,i.on_hand,i.reserved,i.reorder_point,coalesce((SELECT "
                "sum(json_extract(o.proposal,'$.quantity')) FROM assistant_orders o WHERE "
                "json_extract(o.proposal,'$.sku')=i.sku AND "
                "o.status IN ('APPROVED','SENDING','UNKNOWN','CONFIRMED')),0) AS on_order "
                "FROM inventory i WHERE (?='' OR i.sku=?) ORDER BY i.sku",
                (subject, subject),
            )
        ]
        for row in rows:
            row["needed"] = max(
                0, row["reorder_point"] - row["on_hand"] + row["reserved"] - row["on_order"]
            )
        return rows

    def supplier(args: StockArguments) -> dict[str, Any]:
        if subject and args.sku != subject:
            raise PermissionError("product is outside this work item's subject")
        row = db.connection.execute(
            "SELECT record FROM products WHERE sku=?", (args.sku,)
        ).fetchone()
        if row is None:
            raise KeyError(args.sku)
        return {
            "supplier": "lucy-local",
            "sku": args.sku,
            "unit_cost_pence": json.loads(row["record"])["unit_cost_cents"],
            "currency": "GBP",
        }

    def draft(args: DraftArguments) -> dict[str, Any]:
        stock = next((row for row in list_stock(NoArguments()) if row["sku"] == args.sku), None)
        if stock is None or args.quantity != stock["needed"]:
            raise ValueError("draft quantity must equal the current positive replenishment need")
        quote = supplier(StockArguments(sku=args.sku))
        return {
            **quote,
            "quantity": args.quantity,
            "total_pence": args.quantity * quote["unit_cost_pence"],
            "status": "DRAFT",
        }

    tools = [
        ExecutableTool(
            "list_stock",
            "Read stock, incoming orders and deterministic needed quantity for each product.",
            NoArguments,
            list_stock,
        ),
        ExecutableTool(
            "supplier",
            "Look up a product's supplier and unit cost in GBP pence.",
            StockArguments,
            supplier,
        ),
        ExecutableTool(
            "draft_order",
            "Create a draft with quantity equal to needed from list_stock. Never purchases.",
            DraftArguments,
            draft,
        ),
    ]
    return Dispatcher(tools, allowed=frozenset(tool.name for tool in tools))


def draft_report(messages: list[Message]) -> str | None:
    """Render latest successful draft estimates; model narration is not arithmetic."""
    names = {
        call["id"]: call["function"]["name"]
        for message in messages
        for call in message.get("tool_calls", [])
    }
    latest: dict[str, tuple[int, int]] = {}
    for message in messages:
        if message["role"] != "tool" or names.get(message["tool_call_id"]) != "draft_order":
            continue
        observation = json.loads(message["content"])
        if observation.get("ok") is not True:
            continue
        value = observation["value"]
        sku, quantity, amount = value.get("sku"), value.get("quantity"), value.get("total_pence")
        if (
            not isinstance(sku, str)
            or not 1 <= len(sku) <= 100
            or type(quantity) is not int
            or quantity <= 0
            or type(amount) is not int
            or amount < 0
            or value.get("currency") != "GBP"
        ):
            raise ValueError("draft observation lacks validated quantity or GBP amount")
        # Recalculating a draft is not creating another purchase. Display only
        # the latest estimate for each SKU; supplier workflows render their ledger.
        latest[sku] = (quantity, amount)
    if not latest:
        return None
    lines = ["Draft estimates:"]
    for sku, (quantity, amount) in sorted(latest.items()):
        label = json.dumps(sku, ensure_ascii=False)
        lines.append(f"- {label}: {quantity} tubs, £{amount // 100}.{amount % 100:02d} GBP.")
    total = sum(amount for _, amount in latest.values())
    lines.append(f"Total: £{total // 100}.{total % 100:02d} GBP.")
    return "\n".join(lines)


class OfflineShopModel:
    """A reproducible model replacement, not a claim of language understanding.

    Its policy is inspectable: query stock, draft shortages, explain observations.
    The same dispatcher and loop serve this fixture and the live HTTP model.
    """

    def complete(
        self,
        messages: list[Message],
        tools: list[Message],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn:
        # Only observations after the newest request belong to this turn.
        start = max((i for i, m in enumerate(messages) if m["role"] == "user"), default=0)
        observations = [json.loads(m["content"]) for m in messages[start:] if m["role"] == "tool"]
        if not observations:
            return ModelTurn(calls=(ToolCall(id="stock", name="list_stock", arguments={}),))
        if len(observations) == 1 and observations[0].get("ok"):
            stock = observations[0]["value"]
            calls = tuple(
                ToolCall(
                    id=f"draft-{i}",
                    name="draft_order",
                    arguments={
                        "sku": row["sku"],
                        "quantity": row["reorder_point"]
                        - row["on_hand"]
                        + row["reserved"]
                        - row["on_order"],
                    },
                )
                for i, row in enumerate(stock)
                if row["on_hand"] - row["reserved"] + row["on_order"] < row["reorder_point"]
            )
            if calls:
                return ModelTurn(calls=calls)
            return ModelTurn(
                "Stock plus pending replenishment covers each threshold; "
                "no additional draft is needed."
            )
        drafts = [o["value"] for o in observations[1:] if o.get("ok")]
        if not drafts:
            return ModelTurn("I could not prepare the draft; inspect the tool errors.")
        lines = [f"{d['sku']}: {d['quantity']} units, {d['total_pence']} pence GBP" for d in drafts]
        return ModelTurn("Replenishment draft:\n" + "\n".join(lines) + "\nNo purchases made.")
