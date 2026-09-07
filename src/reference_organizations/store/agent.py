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


def shop_dispatcher(db: Database) -> Dispatcher:
    def list_stock(_: NoArguments) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in db.connection.execute(
                "SELECT sku,on_hand,reserved,reorder_point FROM inventory ORDER BY sku"
            )
        ]

    def supplier(args: StockArguments) -> dict[str, Any]:
        row = db.connection.execute(
            "SELECT record FROM products WHERE sku=?", (args.sku,)
        ).fetchone()
        if row is None:
            raise KeyError(args.sku)
        return {
            "supplier": "lucy-local",
            "sku": args.sku,
            "unit_cost_cents": json.loads(row["record"])["unit_cost_cents"],
        }

    def draft(args: DraftArguments) -> dict[str, Any]:
        quote = supplier(StockArguments(sku=args.sku))
        return {
            **quote,
            "quantity": args.quantity,
            "total_cents": args.quantity * quote["unit_cost_cents"],
            "status": "DRAFT",
        }

    tools = [
        ExecutableTool(
            "list_stock", "Read current stock and product thresholds.", NoArguments, list_stock
        ),
        ExecutableTool(
            "supplier",
            "Look up a product's supplier and unit cost in cents.",
            StockArguments,
            supplier,
        ),
        ExecutableTool(
            "draft_order", "Calculate a draft. Does not buy or change stock.", DraftArguments, draft
        ),
    ]
    return Dispatcher(tools, allowed=frozenset(tool.name for tool in tools))


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
                        "quantity": row["reorder_point"] - row["on_hand"] + row["reserved"],
                    },
                )
                for i, row in enumerate(stock)
                if row["on_hand"] - row["reserved"] < row["reorder_point"]
            )
            if calls:
                return ModelTurn(calls=calls)
            return ModelTurn("All products are at or above their thresholds.")
        drafts = [o["value"] for o in observations[1:] if o.get("ok")]
        if not drafts:
            return ModelTurn("I could not prepare the draft; inspect the tool errors.")
        lines = [f"{d['sku']}: {d['quantity']} units, {d['total_cents']} cents" for d in drafts]
        return ModelTurn("Replenishment draft:\n" + "\n".join(lines) + "\nNo purchases made.")
