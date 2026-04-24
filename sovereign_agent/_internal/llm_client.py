"""LLM client abstraction used by planner and executor.

Two implementations:

  OpenAICompatibleClient — thin wrapper over the `openai` SDK, pointed at
    any OpenAI-compatible endpoint (Nebius Token Factory by default). Used
    in production and in network-gated integration tests.

  FakeLLMClient — scripted responses for unit tests. Lets the planner and
    executor test suites run offline and deterministically.

The ChatMessage / ChatResponse / ToolCall types are intentionally the subset
we actually use. We do not try to mirror the whole OpenAI schema.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sovereign_agent.errors import ExternalError


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_openai(self) -> dict:
        out: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            out["content"] = self.content
        if self.tool_calls:
            out["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]
        if self.tool_call_id is not None:
            out["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            out["name"] = self.name
        return out


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

    def to_openai(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
        }

    @classmethod
    def from_openai(cls, tc: Any) -> ToolCall:
        try:
            args_raw = tc.function.arguments
        except AttributeError:
            args_raw = tc["function"]["arguments"]
        try:
            args = json.loads(args_raw) if args_raw else {}
        except (TypeError, json.JSONDecodeError):
            # Some models emit malformed JSON here. Surface as empty dict and
            # let the caller decide; don't crash the whole agent.
            args = {"_raw_arguments": str(args_raw)}
        return cls(
            id=getattr(tc, "id", None) or tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            name=tc.function.name if hasattr(tc, "function") else tc["function"]["name"],
            arguments=args,
        )


@dataclass
class ChatResponse:
    """What the client returns from a chat completion call."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class LLMClient(Protocol):
    async def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse: ...


# ---------------------------------------------------------------------------
# Real OpenAI-compatible client
# ---------------------------------------------------------------------------


class OpenAICompatibleClient:
    """Thin wrapper around the `openai` SDK."""

    def __init__(
        self,
        base_url: str,
        api_key_env: str = "NEBIUS_KEY",
        api_key: str | None = None,
    ) -> None:
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise ExternalError(
                code="SA_EXT_AUTH_EXPIRED",
                message=(
                    f"LLM API key not available. Set env var {api_key_env!r} "
                    "or pass api_key= explicitly."
                ),
                retriable=False,
            )
        try:
            from openai import AsyncOpenAI  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openai package is required. Run: pip install openai>=1.40") from exc
        self._client = AsyncOpenAI(api_key=key, base_url=base_url)
        self.base_url = base_url

    async def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage] | list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        # Accept raw dicts (`{"role": ..., "content": ...}`) as well as
        # ChatMessage instances. Downstream callers writing quick probes or
        # pasting OpenAI SDK examples should "just work" — the failure mode
        # where a dict reaches `m.to_openai()` and blows up with an AttributeError
        # is user-hostile. The library should handle the OpenAI wire format
        # that everyone is already copy-pasting from docs.
        normalized: list[ChatMessage] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                normalized.append(m)
            elif isinstance(m, dict):
                normalized.append(ChatMessage(**m))
            else:
                raise TypeError(
                    f"messages must be ChatMessage or dict; got {type(m).__name__}. "
                    'Example: ChatMessage(role="user", content="hi") or '
                    '{"role": "user", "content": "hi"}'
                )
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [m.to_openai() for m in normalized],
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            # Classify common failure modes.
            msg = str(exc)
            low = msg.lower()
            if "rate" in low and "limit" in low:
                raise ExternalError(
                    code="SA_EXT_RATE_LIMITED",
                    message=f"rate limited by LLM provider: {msg}",
                    retriable=True,
                    cause=exc,
                ) from exc
            if "timeout" in low or "timed out" in low:
                raise ExternalError(
                    code="SA_EXT_TIMEOUT",
                    message=f"LLM request timed out: {msg}",
                    retriable=True,
                    cause=exc,
                ) from exc
            if "auth" in low or "401" in low or "unauthor" in low:
                raise ExternalError(
                    code="SA_EXT_AUTH_EXPIRED",
                    message=f"LLM auth error: {msg}",
                    retriable=False,
                    cause=exc,
                ) from exc
            raise ExternalError(
                code="SA_EXT_UNEXPECTED_RESPONSE",
                message=f"LLM call failed: {msg}",
                retriable=False,
                cause=exc,
            ) from exc

        choice = resp.choices[0]
        message = choice.message
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        tool_calls = [ToolCall.from_openai(tc) for tc in raw_tool_calls]
        usage = getattr(resp, "usage", None)
        return ChatResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            model=model,
        )


# ---------------------------------------------------------------------------
# Fake client for tests
# ---------------------------------------------------------------------------


@dataclass
class ScriptedResponse:
    """One scripted response. Use `content` for text, `tool_calls` for calls."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


class FakeLLMClient:
    """Deterministic fake for unit tests. Returns scripted responses in order."""

    def __init__(self, responses: list[ScriptedResponse] | None = None) -> None:
        self.responses: list[ScriptedResponse] = list(responses or [])
        self.calls: list[dict] = []

    def extend(self, more: list[ScriptedResponse]) -> None:
        self.responses.extend(more)

    async def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.calls.append(
            {
                "model": model,
                "messages": [m.to_openai() for m in messages],
                "tools": tools,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise ExternalError(
                code="SA_EXT_UNEXPECTED_RESPONSE",
                message="FakeLLMClient ran out of scripted responses",
                retriable=False,
            )
        r = self.responses.pop(0)
        return ChatResponse(
            content=r.content,
            tool_calls=list(r.tool_calls),
            finish_reason=r.finish_reason,
            input_tokens=10,
            output_tokens=10,
            model=model,
        )


__all__ = [
    "ChatMessage",
    "ChatResponse",
    "ToolCall",
    "LLMClient",
    "OpenAICompatibleClient",
    "FakeLLMClient",
    "ScriptedResponse",
]
