"""Typed tool execution: discovery is data, authorization precedes invocation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ValidationError

from sovereign_agent.model_turn import ToolCall


@dataclass(frozen=True)
class ExecutableTool:
    name: str
    description: str
    arguments: type[BaseModel]
    handler: Callable[[Any], Any]
    consequential: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments.model_json_schema(),
            },
        }


class Dispatcher:
    def __init__(
        self,
        tools: list[ExecutableTool],
        *,
        allowed: frozenset[str],
        before_write: Callable[[ToolCall], None] | None = None,
        max_result_bytes: int = 16_384,
    ) -> None:
        self.tools = MappingProxyType({tool.name: tool for tool in tools})
        if len(self.tools) != len(tools):
            raise ValueError("tool names must be unique")
        if not 128 <= max_result_bytes <= 1_048_576:
            raise ValueError("invalid tool result byte limit")
        self.allowed, self.before_write = allowed, before_write
        self.max_result_bytes = max_result_bytes

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for name, tool in sorted(self.tools.items()) if name in self.allowed]

    def invoke(self, call: ToolCall) -> dict[str, Any]:
        tool = self.tools.get(call.name)
        if tool is None or call.name not in self.allowed:
            return {"ok": False, "error": "tool_not_allowed"}
        try:
            arguments = tool.arguments.model_validate(call.arguments, strict=True)
        except ValidationError:
            # ValidationError strings can contain raw arguments and secrets.
            return {"ok": False, "error": "invalid_arguments"}
        if tool.consequential and self.before_write is None:
            return {"ok": False, "error": "write_authority_required"}
        try:
            if tool.consequential:
                assert self.before_write is not None
                self.before_write(call)
            value = tool.handler(arguments)
            encoded = json.dumps(value, allow_nan=False)
            if len(encoded.encode()) > self.max_result_bytes:
                return {"ok": False, "error": "result_too_large"}
            return {"ok": True, "value": value}
        except ValueError, TypeError, KeyError, PermissionError, TimeoutError, OSError:
            return {"ok": False, "error": "tool_failed"}
