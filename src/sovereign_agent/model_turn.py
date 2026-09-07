"""One model turn; deliberately distinct from a whole CLI-agent assignment."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from sovereign_agent.http_transport import request

Message = dict[str, Any]


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    content: str = ""
    calls: tuple[ToolCall, ...] = ()
    output_tokens: int = 0

    def message(self) -> Message:
        result: Message = {"role": "assistant", "content": self.content}
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


class Model(Protocol):
    def complete(
        self,
        messages: list[Message],
        tools: list[Message],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn: ...


class ModelError(RuntimeError):
    """A sanitized transport/protocol failure, safe to put in a transcript."""


class HTTPModel:
    """Bounded OpenAI-compatible HTTP, with Ollama as the local default.

    Endpoint/configuration is operator-owned. Redirects cannot forward a bearer
    credential to another host. Raw request bodies and exception URLs are never
    copied into errors. This adapter does not install or start a model server.
    """

    def __init__(
        self, base_url: str = "http://localhost:11434/v1", model: str = "qwen3", api_key: str = ""
    ) -> None:
        from urllib.parse import urlsplit

        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid model endpoint")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("remote model endpoints require HTTPS")
        self.base_url, self.model, self._key = base_url.rstrip("/"), model, api_key

    def complete(
        self,
        messages: list[Message],
        tools: list[Message],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn:
        if (
            not math.isfinite(timeout)
            or timeout <= 0
            or type(max_output_tokens) is not int
            or max_output_tokens < 1
        ):
            raise ValueError("positive model limits required")
        payload: Message = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_output_tokens,
            "temperature": 0,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        try:
            response = request(
                self.base_url + "/chat/completions",
                data=json.dumps(payload).encode(),
                headers=headers,
                timeout=timeout,
            )
            if response.status != 200:
                raise ModelError(f"model HTTP {response.status}")
            data = json.loads(response.body)
            choice = data["choices"][0]
            message = choice["message"]
            if choice.get("finish_reason") not in {"stop", "tool_calls"}:
                raise ModelError("model response incomplete or refused")
            if message.get("refusal"):
                raise ModelError("model refused the request")
            calls = tuple(
                ToolCall(
                    id=item["id"],
                    name=item["function"]["name"],
                    arguments=json.loads(item["function"]["arguments"]),
                )
                for item in message.get("tool_calls", [])
            )
            content = message.get("content") or ""
            tokens = data.get("usage", {}).get("completion_tokens")
            if not isinstance(content, str) or type(tokens) is not int or tokens < 0:
                raise ModelError("invalid model content or usage")
            if tokens > max_output_tokens or len(calls) > 32:
                raise ModelError("model exceeded requested limits")
            return ModelTurn(content, calls, tokens)
        except OSError, ValueError, KeyError, IndexError, TypeError:
            raise ModelError("model transport or response validation failed") from None
