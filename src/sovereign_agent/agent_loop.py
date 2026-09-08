"""The reader-owned model/tool/observation loop. No agent framework inside."""

from __future__ import annotations

import copy
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sovereign_agent.model_turn import Message, Model, ModelError
from sovereign_agent.tool_dispatch import Dispatcher


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

    def __post_init__(self) -> None:
        if type(self.estimated_call_pence) is not int or self.estimated_call_pence < 0:
            raise ValueError("nonnegative integral model estimate required")
        if type(self.model_budget_pence) is not int or self.model_budget_pence < 1:
            raise ValueError("positive integral model budget required")
        if not math.isfinite(self.seconds):
            raise ValueError("finite loop duration required")
        integers = (
            self.model_calls,
            self.tool_calls,
            self.context_bytes,
            self.output_tokens,
            self.total_output_tokens,
        )
        if any(type(value) is not int for value in integers):
            raise ValueError("integral loop budgets required")
        if (
            min(
                self.model_calls,
                self.tool_calls,
                self.seconds,
                self.context_bytes,
                self.output_tokens,
                self.total_output_tokens,
            )
            <= 0
        ):
            raise ValueError("all loop limits must be positive")


@dataclass(frozen=True)
class LoopResult:
    status: str
    answer: str
    messages: list[Message]
    model_calls: int
    tool_calls: int
    output_tokens: int
    estimated_cost_pence: int


def run_loop(
    model: Model,
    dispatcher: Dispatcher,
    messages: list[Message],
    *,
    limits: Limits | None = None,
    clock: Callable[[], float] = time.monotonic,
    observe: Callable[[Message], None] | None = None,
    check_current: Callable[[], None] | None = None,
    reserve_call: Callable[[], None] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> LoopResult:
    """Keep effects behind dispatch; reject reused call identities before a batch.

    Trusted Python handlers must themselves be bounded. Arbitrary code belongs
    in a timeout-controlled subprocess, not a Python thread pretending to cancel
    it. The live model adapter receives the remaining wall-clock allowance.
    """
    limits = limits or Limits()
    transcript = copy.deepcopy(messages)
    deadline = clock() + limits.seconds
    model_count = tool_count = tokens = exposure = 0
    seen: set[str] = set()

    def finish(status: str, answer: str = "") -> LoopResult:
        return LoopResult(status, answer, transcript, model_count, tool_count, tokens, exposure)

    def append(message: dict[str, Any]) -> None:
        if observe:
            observe(copy.deepcopy(message))
        transcript.append(message)

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
            if check_current:
                check_current()
            if exposure + limits.estimated_call_pence > limits.model_budget_pence:
                return finish("MODEL_COST_LIMIT")
            if reserve_call:
                reserve_call()
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
        append(turn.message())
        if not turn.calls:
            return (
                finish("COMPLETED", turn.content) if turn.content.strip() else finish("EMPTY_REPLY")
            )
        for call in turn.calls:
            if should_stop():
                return finish("STOP_REQUESTED")
            if clock() >= deadline:
                return finish("TIME_LIMIT")
            if check_current:
                check_current()
            tool_count += 1
            result = dispatcher.invoke(call)
            append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, allow_nan=False),
                }
            )
    return finish("MODEL_CALL_LIMIT")
