"""Chapter 2: typed shop tools over the same in-memory fixture."""

import copy
import json
import runpy
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from sovereign_agent.model_turn import ToolCall
from sovereign_agent.tool_dispatch import Dispatcher, ExecutableTool

SHOP = runpy.run_path(str(Path(__file__).with_name("ch01.py")))["SHOP"]
PRICES = {"SKU-VANILLA": 250, "SKU-CHOCOLATE": 300, "SKU-STRAWBERRY": 275}


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProductArguments(NoArguments):
    sku: str = Field(min_length=1, max_length=100)


class DraftArguments(ProductArguments):
    quantity: int = Field(gt=0, le=1000)


def build_tools(shop):
    products = {row["sku"]: copy.deepcopy(row) for row in shop["products"]}
    if len(products) != len(shop["products"]):
        raise ValueError("duplicate product identity")

    def stock(_):
        return [
            {**row, "needed": max(0, row["reorder_point"] - row["on_hand"])}
            for _, row in sorted(products.items())
        ]

    def supplier(args):
        if args.sku not in products:
            raise KeyError("unknown product")
        return {
            "sku": args.sku,
            "supplier": "lucy-local",
            "currency": "GBP",
            "unit_cost_pence": PRICES[args.sku],
        }

    def draft(args):
        row = products[args.sku]
        needed = max(0, row["reorder_point"] - row["on_hand"])
        if args.quantity != needed:
            raise ValueError("quantity differs from the replenishment need")
        quote = supplier(ProductArguments(sku=args.sku))
        return {
            **quote,
            "quantity": args.quantity,
            "total_pence": args.quantity * quote["unit_cost_pence"],
            "status": "DRAFT",
        }

    tools = [
        ExecutableTool(
            "list_stock",
            "Read the fixture and deterministic needed quantities.",
            NoArguments,
            stock,
        ),
        ExecutableTool(
            "supplier",
            "Read a product's supplier and unit price in GBP pence.",
            ProductArguments,
            supplier,
        ),
        ExecutableTool(
            "draft_order",
            "Calculate a draft with quantity equal to needed. Never purchases.",
            DraftArguments,
            draft,
        ),
    ]
    return Dispatcher(tools, allowed=frozenset(tool.name for tool in tools))


def main():
    tools = build_tools(SHOP)
    stock = tools.invoke(ToolCall(id="stock", name="list_stock", arguments={}))
    print([(row["sku"], row["needed"]) for row in stock["value"]])
    good = tools.invoke(
        ToolCall(id="draft", name="draft_order", arguments={"sku": "SKU-VANILLA", "quantity": 6})
    )
    print(json.dumps(good, sort_keys=True))
    bad = tools.invoke(
        ToolCall(id="bad", name="draft_order", arguments={"sku": "SKU-VANILLA", "quantity": True})
    )
    print(json.dumps(bad, sort_keys=True))


if __name__ == "__main__":
    main()
