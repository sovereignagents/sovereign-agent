"""Definitions constructed in Chapter 3; experiments remain in the chapter."""

import copy
import json
import math
import runpy
import time
from dataclasses import dataclass

shop_tools = runpy.run_path("book/always_on/learner/ch02.py")


ToolCall = shop_tools["ToolCall"]


class ModelError(RuntimeError):
    """A sanitized model transport or response failure."""


@dataclass(frozen=True)
class ModelTurn:
    content: str = ""
    calls: tuple[ToolCall, ...] = ()
    output_tokens: int = 0

    def message(self):
        result = {"role": "assistant", "content": self.content}
        if self.calls:
            result["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in self.calls
            ]
        return result


first = ModelTurn(calls=(ToolCall(id="stock-1", name="list_stock", arguments={}),))


messages = [
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


@dataclass(frozen=True)
class Limits:
    model_calls: int = 8
    tool_calls: int = 16
    seconds: float = 60
    context_bytes: int = 32_768
    output_tokens: int = 1_024
    total_output_tokens: int = 4_096
    estimated_call_pence: int = 0
    model_budget_pence: int = 100

    def __post_init__(self):
        integers = (
            self.model_calls,
            self.tool_calls,
            self.context_bytes,
            self.output_tokens,
            self.total_output_tokens,
            self.model_budget_pence,
        )
        if any(type(value) is not int or value <= 0 for value in integers):
            raise ValueError("positive integral limits required")
        if not math.isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError("positive finite duration required")
        if type(self.estimated_call_pence) is not int or self.estimated_call_pence < 0:
            raise ValueError("nonnegative integral model estimate required")


@dataclass(frozen=True)
class LoopResult:
    status: str
    answer: str
    messages: list
    model_calls: int
    tool_calls: int
    output_tokens: int
    estimated_cost_pence: int


def run_loop(
    model, dispatcher, messages, *, limits=None, clock=time.monotonic, should_stop=lambda: False
):
    limits = limits or Limits()
    transcript = copy.deepcopy(messages)
    deadline = clock() + limits.seconds
    model_count = tool_count = tokens = exposure = 0
    seen = set()

    def finish(status, answer=""):
        return LoopResult(status, answer, transcript, model_count, tool_count, tokens, exposure)

    while model_count < limits.model_calls:
        if should_stop():
            return finish("STOP_REQUESTED")
        if clock() >= deadline:
            return finish("TIME_LIMIT")
        schemas = dispatcher.schemas()
        if len(json.dumps([transcript, schemas]).encode()) > limits.context_bytes:
            return finish("CONTEXT_LIMIT")
        remaining = min(limits.output_tokens, limits.total_output_tokens - tokens)
        if remaining <= 0:
            return finish("TOKEN_LIMIT")
        try:
            if exposure + limits.estimated_call_pence > limits.model_budget_pence:
                return finish("MODEL_COST_LIMIT")
            exposure += limits.estimated_call_pence
            model_count += 1
            turn = model.complete(
                copy.deepcopy(transcript),
                schemas,
                timeout=deadline - clock(),
                max_output_tokens=remaining,
            )
        except ModelError, TimeoutError, OSError:
            return finish("MODEL_FAILED")
        if clock() >= deadline:
            return finish("TIME_LIMIT")
        if type(turn.output_tokens) is not int or not 0 <= turn.output_tokens <= remaining:
            return finish("INVALID_USAGE")
        tokens += turn.output_tokens
        ids = [call.id for call in turn.calls]
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            return finish("REPEATED_CALL_ID")
        if tool_count + len(ids) > limits.tool_calls:
            return finish("TOOL_LIMIT")
        seen.update(ids)
        transcript.append(turn.message())
        if not turn.calls:
            return (
                finish("COMPLETED", turn.content) if turn.content.strip() else finish("EMPTY_REPLY")
            )
        for call in turn.calls:
            if should_stop():
                return finish("STOP_REQUESTED")
            if clock() >= deadline:
                return finish("TIME_LIMIT")
            tool_count += 1
            result = dispatcher.invoke(call)
            transcript.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, allow_nan=False),
                }
            )
    return finish("MODEL_CALL_LIMIT")


class ReplayModel:
    def __init__(self, turns):
        self.turns = iter(turns)

    def complete(self, messages, tools, *, timeout, max_output_tokens):
        try:
            return next(self.turns)
        except StopIteration:
            raise ModelError("response fixture exhausted") from None


def opening_turns():
    return [
        first,
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
            )
        ),
        ModelTurn("Drafts: vanilla 6 tubs, strawberry 4 tubs; total 2600 pence GBP. No purchase."),
    ]


class HTTPModel:
    """One local Ollama response; never executes tools itself."""

    def __init__(self, model="qwen3", request=None):
        self.model, self.request = model, request

    def complete(self, messages, tools, *, timeout, max_output_tokens):
        transport = self.request
        if transport is None:
            from sovereign_agent.http_transport import request

            transport = request
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "max_tokens": max_output_tokens,
            "temperature": 0,
            "reasoning_effort": "none",
        }
        try:
            response = transport(
                "http://localhost:11434/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            if response.status != 200:
                raise ModelError("model HTTP request failed")
            envelope = json.loads(response.body)
            choices, usage = envelope["choices"], envelope["usage"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ModelError("one complete choice required")
            choice = choices[0]
            message = choice["message"]
            if choice["finish_reason"] not in {"stop", "tool_calls"} or message.get("refusal"):
                raise ModelError("incomplete or refused response")
            requested = message.get("tool_calls", [])
            if not isinstance(requested, list) or len(requested) > 32:
                raise ModelError("bounded tool-call array required")
            calls = tuple(
                ToolCall(
                    id=item["id"],
                    name=item["function"]["name"],
                    arguments=json.loads(item["function"]["arguments"]),
                )
                for item in requested
            )
            content = message.get("content")
            content = "" if content is None else content
            tokens = usage["completion_tokens"]
            if (
                not isinstance(content, str)
                or type(tokens) is not int
                or not 0 <= tokens <= max_output_tokens
            ):
                raise ModelError("invalid content or usage")
            return ModelTurn(content, calls, tokens)
        except OSError, ValueError, KeyError, IndexError, TypeError, AttributeError:
            raise ModelError("model transport or response validation failed") from None


def draft_evidence(result):
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
