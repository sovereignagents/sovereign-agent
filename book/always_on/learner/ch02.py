"""Definitions constructed in Chapter 2; experiments remain in the chapter."""

import copy
import json
import runpy
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SHOP = runpy.run_path("book/always_on/checkpoints/ch01.py")["SHOP"]


PRICES = {"SKU-VANILLA": 250, "SKU-CHOCOLATE": 300, "SKU-STRAWBERRY": 275}


products = {row["sku"]: copy.deepcopy(row) for row in SHOP["products"]}


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProductArguments(NoArguments):
    sku: str = Field(min_length=1, max_length=100)


class DraftArguments(ProductArguments):
    quantity: int = Field(gt=0, le=1000)


def list_stock(_):
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


def draft_order(args):
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


@dataclass(frozen=True)
class ExecutableTool:
    name: str
    description: str
    arguments: type[BaseModel]
    handler: Callable[[Any], Any]
    consequential: bool = False

    def schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments.model_json_schema(),
            },
        }


tools = [
    ExecutableTool(
        "list_stock", "Read stock and calculated replenishment need.", NoArguments, list_stock
    ),
    ExecutableTool("supplier", "Read a supplier quote in GBP pence.", ProductArguments, supplier),
    ExecutableTool(
        "draft_order", "Calculate a draft; never purchases.", DraftArguments, draft_order
    ),
]


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    arguments: dict[str, Any]


class Dispatcher:
    def __init__(self, tools, *, allowed, before_write=None, max_result_bytes=16_384):
        self.tools = MappingProxyType({tool.name: tool for tool in tools})
        if len(self.tools) != len(tools):
            raise ValueError("tool names must be unique")
        if not 128 <= max_result_bytes <= 1_048_576:
            raise ValueError("invalid tool result byte limit")
        self.allowed, self.before_write = allowed, before_write
        self.max_result_bytes = max_result_bytes

    def schemas(self):
        return [tool.schema() for name, tool in sorted(self.tools.items()) if name in self.allowed]

    def invoke(self, call):
        tool = self.tools.get(call.name)
        if tool is None or call.name not in self.allowed:
            return {"ok": False, "error": "tool_not_allowed"}
        try:
            arguments = tool.arguments.model_validate(call.arguments, strict=True)
        except ValidationError:
            return {"ok": False, "error": "invalid_arguments"}
        if tool.consequential and self.before_write is None:
            return {"ok": False, "error": "write_authority_required"}
        try:
            if tool.consequential:
                self.before_write(call)
            value = tool.handler(arguments)
            encoded = json.dumps(value, allow_nan=False)
            if len(encoded.encode()) > self.max_result_bytes:
                return {"ok": False, "error": "result_too_large"}
            return {"ok": True, "value": value}
        except ValueError, TypeError, KeyError, PermissionError, TimeoutError, OSError:
            return {"ok": False, "error": "tool_failed"}


def build_tools(shop):
    rows = {row["sku"]: copy.deepcopy(row) for row in shop["products"]}
    if len(rows) != len(shop["products"]):
        raise ValueError("duplicate product identity")

    def stock(_):
        return [
            {**row, "needed": max(0, row["reorder_point"] - row["on_hand"])}
            for _, row in sorted(rows.items())
        ]

    def quote(args):
        if args.sku not in rows:
            raise KeyError("unknown product")
        return {
            "sku": args.sku,
            "supplier": "lucy-local",
            "currency": "GBP",
            "unit_cost_pence": PRICES[args.sku],
        }

    def draft(args):
        row = rows[args.sku]
        needed = max(0, row["reorder_point"] - row["on_hand"])
        if args.quantity != needed:
            raise ValueError("quantity differs from the replenishment need")
        price = quote(ProductArguments(sku=args.sku))
        return {
            **price,
            "quantity": args.quantity,
            "total_pence": args.quantity * price["unit_cost_pence"],
            "status": "DRAFT",
        }

    registered = [
        ExecutableTool("list_stock", "Read stock and calculated need.", NoArguments, stock),
        ExecutableTool("supplier", "Read supplier price in GBP pence.", ProductArguments, quote),
        ExecutableTool("draft_order", "Calculate a draft; never purchases.", DraftArguments, draft),
    ]
    return Dispatcher(registered, allowed=frozenset(tool.name for tool in registered))
