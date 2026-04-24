"""Tools: dumb deterministic functions the agent can call.

Following the MCP philosophy (and departing from some older QuackVerse
thinking): tools in sovereign-agent have no LLM calls inside. The
intelligence lives in the agent, not in the tool.

See docs/architecture.md §2.14.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sovereign_agent.discovery import DiscoverySchema, validate_schema
from sovereign_agent.errors import SovereignError, ToolError, ValidationError


@dataclass
class ToolResult:
    """What every tool returns.

    Fields:
      success, output, summary, error: the core result contract.
      requires_human_approval: if True, the executor will pause after this
        call, write ipc/awaiting_approval/<ticket_id>.json, and exit. A
        human (via sa-approve or an external UI) must write
        ipc/approval_granted/<ticket_id>.json for the session to resume.
        See docs/human_in_the_loop.md.
    """

    success: bool
    output: dict
    summary: str
    error: SovereignError | None = None
    requires_human_approval: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "summary": self.summary,
            "error": self.error.to_dict() if self.error else None,
            "requires_human_approval": self.requires_human_approval,
        }


@dataclass
class _RegisteredTool:
    """Internal record. Wraps a plain Python function as a Tool.

    Fields beyond the core metadata:
      parallel_safe: if True (the default), the executor MAY invoke this
        tool concurrently with other parallel_safe tool calls from the
        same assistant turn. Read-only tools (web_lookup, read_file,
        arithmetic) should leave this True. Write tools (write_file,
        send_email, complete_task, handoff_*) should set it False so
        the executor serialises them. See executor/__init__.py.
      verify_args: optional hook that runs before execute(). Given the
        proposed arguments, it returns (ok, reason). If ok=False, the
        call is rejected before the tool runs — the LLM sees the reason
        and can retry with different arguments. See
        docs/tool_verification.md.
    """

    name: str
    description: str
    fn: Callable[..., Any]
    parameters_schema: dict
    returns_schema: dict
    is_async: bool
    version: str = "0.1.0"
    error_codes: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)
    parallel_safe: bool = True
    verify_args: Callable[[dict], tuple[bool, str]] | None = None

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "tool",
            "description": self.description,
            "parameters": self.parameters_schema,
            "returns": self.returns_schema,
            "error_codes": self.error_codes,
            "examples": self.examples
            or [
                # If no examples were declared, auto-generate a minimal one
                # so discovery validation doesn't reject the tool. Authors
                # are strongly encouraged to provide real ones.
                {"input": {}, "output": {"note": "no example declared"}}
            ],
            "version": self.version,
            "metadata": {},
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        # v0.2: run verify_args hook before the tool function itself.
        # Lets scenarios reject nonsensical arguments (missing files,
        # out-of-range values, stale references) without consuming a
        # tool-call slot on a doomed execution. The LLM sees `reason`
        # and can retry.
        if self.verify_args is not None:
            try:
                ok, reason = self.verify_args(kwargs)
            except Exception as exc:  # noqa: BLE001
                err = ToolError(
                    code="SA_TOOL_VERIFY_FAILED",
                    message=f"verify_args for {self.name} raised: {exc}",
                    context={"tool": self.name},
                    cause=exc,
                )
                return ToolResult(success=False, output={}, summary=str(err), error=err)
            if not ok:
                err = ValidationError(
                    code="SA_VAL_ARG_REJECTED",
                    message=f"arguments rejected by verify_args: {reason}",
                    context={"tool": self.name, "args": list(kwargs.keys())},
                )
                return ToolResult(
                    success=False,
                    output={"rejected_reason": reason},
                    summary=f"{self.name}: args rejected — {reason}",
                    error=err,
                )

        try:
            if self.is_async:
                result = await self.fn(**kwargs)
            else:
                result = self.fn(**kwargs)
        except SovereignError as exc:
            return ToolResult(success=False, output={}, summary=f"tool failed: {exc}", error=exc)
        except TypeError as exc:
            # Usually a bad-arguments mistake.
            err = ToolError(
                code="SA_TOOL_INVALID_INPUT",
                message=f"invalid arguments to tool {self.name}: {exc}",
                context={"kwargs": list(kwargs.keys())},
                cause=exc,
            )
            return ToolResult(success=False, output={}, summary=str(err), error=err)
        except Exception as exc:  # noqa: BLE001
            err = ToolError(
                code="SA_TOOL_EXECUTION_FAILED",
                message=f"tool {self.name} raised {type(exc).__name__}: {exc}",
                context={"tool": self.name},
                cause=exc,
            )
            return ToolResult(success=False, output={}, summary=str(err), error=err)

        if isinstance(result, ToolResult):
            return result
        if isinstance(result, dict):
            # Auto-wrap plain dict returns in a ToolResult with a
            # trivial summary. Tool authors should prefer to return
            # ToolResult explicitly so they control the summary.
            preview = ", ".join(f"{k}={_short(v)}" for k, v in list(result.items())[:3])
            summary = f"{self.name} returned: {preview}" if preview else f"{self.name} returned"
            return ToolResult(success=True, output=result, summary=summary)
        # Non-dict returns are wrapped too, preserving the raw value.
        return ToolResult(
            success=True,
            output={"value": result},
            summary=f"{self.name} returned {type(result).__name__}",
        )


def _short(v: Any, maxlen: int = 40) -> str:
    s = repr(v)
    return s if len(s) <= maxlen else s[: maxlen - 1] + "…"


class ToolRegistry:
    """Registry of tools available to agents."""

    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}

    def register(self, tool: _RegisteredTool) -> None:
        if tool.name in self._tools:
            raise ValidationError(
                code="SA_VAL_BAD_TYPE",
                message=f"tool {tool.name!r} is already registered",
            )
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> _RegisteredTool:
        if name not in self._tools:
            raise ToolError(
                code="SA_TOOL_NOT_FOUND",
                message=f"tool {name!r} is not registered",
                context={"available": sorted(self._tools)},
            )
        return self._tools[name]

    def list(self) -> list[_RegisteredTool]:
        return list(self._tools.values())

    def discover_all(self) -> list[DiscoverySchema]:
        return [validate_schema(t.discover()) for t in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


# A single process-global registry for the decorator form.
_GLOBAL_REGISTRY = ToolRegistry()


def global_registry() -> ToolRegistry:
    return _GLOBAL_REGISTRY


def register_tool(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    examples: list[dict] | None = None,
    error_codes: list[str] | None = None,
    version: str = "0.1.0",
    registry: ToolRegistry | None = None,
    parallel_safe: bool = True,
    verify_args: Callable[[dict], tuple[bool, str]] | None = None,
) -> Callable[..., Any]:
    """Decorator that turns a plain Python function into a registered Tool.

    The function's docstring becomes the description. Type hints become the
    (shallow) parameters and returns schema. The tool is registered into the
    target registry (default: the process-global one).

    v0.2 additions:
      parallel_safe: if True (default), the executor may invoke this tool
        concurrently with other parallel_safe calls from the same turn.
        Read-only tools should keep the default; tools that write to the
        session (write_file, complete_task, handoff_*, send_email) should
        pass False.
      verify_args: optional hook called with the proposed kwargs before
        execute(). Returns (ok, reason). If ok=False, the call is rejected
        without running the tool and the LLM sees the reason.

    Can be used bare:

        @register_tool
        def get_weather(city: str) -> dict: ...

    or with arguments:

        @register_tool(name="weather", parallel_safe=True,
                       examples=[{"input": {"city": "E"}, "output": {...}}])
        def get_weather(city: str) -> dict: ...
    """

    def _wrap(target_fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or target_fn.__name__
        tool_desc = description or (inspect.getdoc(target_fn) or f"Tool {tool_name}").strip()
        params_schema = _build_params_schema(target_fn)
        returns_schema = _build_returns_schema(target_fn)
        reg = _RegisteredTool(
            name=tool_name,
            description=tool_desc,
            fn=target_fn,
            parameters_schema=params_schema,
            returns_schema=returns_schema,
            is_async=inspect.iscoroutinefunction(target_fn),
            version=version,
            error_codes=list(error_codes) if error_codes else [],
            examples=list(examples) if examples else [],
            parallel_safe=parallel_safe,
            verify_args=verify_args,
        )
        target_registry = registry if registry is not None else _GLOBAL_REGISTRY
        target_registry.register(reg)
        # Expose the registration on the returned function for introspection.
        target_fn.__sovereign_tool__ = reg  # type: ignore[attr-defined]
        return target_fn

    if fn is None:
        return _wrap
    return _wrap(fn)


# ---------------------------------------------------------------------------
# Type-hint-to-JSON-Schema translation (shallow)
# ---------------------------------------------------------------------------

_PRIMITIVE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _build_params_schema(fn: Callable[..., Any]) -> dict:
    sig = inspect.signature(fn)
    props: dict[str, dict] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        ann = param.annotation if param.annotation is not inspect.Parameter.empty else str
        entry = _ann_to_schema(ann)
        if param.default is inspect.Parameter.empty:
            required.append(pname)
        else:
            entry["default"] = param.default if _json_safe(param.default) else repr(param.default)
        props[pname] = entry
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def _build_returns_schema(fn: Callable[..., Any]) -> dict:
    sig = inspect.signature(fn)
    ann = sig.return_annotation
    if ann is inspect.Signature.empty:
        return {"type": "object"}
    return _ann_to_schema(ann)


def _ann_to_schema(ann: Any) -> dict:
    if ann in _PRIMITIVE_MAP:
        return {"type": _PRIMITIVE_MAP[ann]}
    # `from __future__ import annotations` makes annotations strings.
    # Support the common primitive names explicitly so tools authored with
    # future annotations produce correct schemas.
    if isinstance(ann, str):
        stringy_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
        }
        if ann in stringy_map:
            return {"type": stringy_map[ann]}
    # typing.Any or anything exotic: fall back to "object" (tolerant).
    return {"type": "object"}


def _json_safe(v: Any) -> bool:
    try:
        import json

        json.dumps(v)
        return True
    except (TypeError, ValueError):
        return False


__all__ = [
    "ToolResult",
    "ToolRegistry",
    "register_tool",
    "global_registry",
]
