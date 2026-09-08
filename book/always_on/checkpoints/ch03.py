"""Chapter 3: the owned loop with replayable responses or a live local model."""

import argparse
import json
import runpy
from pathlib import Path

from sovereign_agent.agent_loop import Limits, run_loop
from sovereign_agent.model_turn import HTTPModel, ModelError, ModelTurn, ToolCall

SHOP_TOOLS = runpy.run_path(str(Path(__file__).with_name("ch02.py")))
MESSAGES = [
    {
        "role": "system",
        "content": "Help Lucy prepare replenishment drafts. First call list_stock. "
        "For each product with needed > 0, call draft_order with exactly that quantity. "
        "Do not draft products with needed = 0. Summarize the tool results in GBP pence. "
        "A verbal recommendation does not replace creating the draft through the tool. "
        "Drafts are proposals, never purchases.",
    },
    {
        "role": "user",
        "content": "Prepare replenishment drafts from current stock. State GBP amounts.",
    },
]


class ReplayModel:
    """Authored responses test control flow; they do not test model decisions."""

    def __init__(self, turns):
        self.turns = iter(turns)

    def complete(self, messages, tools, *, timeout, max_output_tokens):
        try:
            return next(self.turns)
        except StopIteration:
            raise ModelError("response fixture exhausted") from None


def opening_turns():
    return [
        ModelTurn(calls=(ToolCall(id="stock-1", name="list_stock", arguments={}),)),
        ModelTurn(
            calls=(
                ToolCall(
                    id="draft-v",
                    name="draft_order",
                    arguments={"sku": "SKU-VANILLA", "quantity": 6},
                ),
                ToolCall(
                    id="draft-s",
                    name="draft_order",
                    arguments={"sku": "SKU-STRAWBERRY", "quantity": 4},
                ),
            ),
        ),
        ModelTurn("Drafts: vanilla 6 tubs, strawberry 4 tubs; total 2600 pence GBP. No purchase."),
    ]


def draft_evidence(result):
    """Authored answers for this fixture; not a general explanation evaluator."""
    names = {
        call["id"]: call["function"]["name"]
        for message in result.messages
        for call in message.get("tool_calls", [])
    }
    observed = []
    for message in result.messages:
        if message["role"] != "tool":
            continue
        value = json.loads(message["content"])
        if value.get("ok") is not True:
            return False
        if names.get(message["tool_call_id"]) == "draft_order":
            draft = value["value"]
            observed.append(
                (draft["sku"], draft["quantity"], draft["total_pence"], draft["currency"])
            )
    return sorted(observed) == [
        ("SKU-STRAWBERRY", 4, 1100, "GBP"),
        ("SKU-VANILLA", 6, 1500, "GBP"),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--transcript", action="store_true")
    args = parser.parse_args()
    model = (
        HTTPModel(model=args.model, reasoning_effort="none")
        if args.live
        else ReplayModel(opening_turns())
    )
    dispatcher = SHOP_TOOLS["build_tools"](SHOP_TOOLS["SHOP"])
    result = run_loop(model, dispatcher, MESSAGES, limits=Limits())
    print(result.status, result.model_calls, result.tool_calls)
    print(result.answer)
    passed = draft_evidence(result)
    print("draft evidence", "PASS" if passed else "FAIL")
    if args.transcript:
        print(json.dumps(result.messages, indent=2))
    return 0 if result.status == "COMPLETED" and passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
