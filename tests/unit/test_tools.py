"""Tests for tools registry, @register_tool, and builtins."""

from __future__ import annotations

import pytest

from sovereign_agent.discovery import validate_schema
from sovereign_agent.errors import ToolError
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.builtin import make_builtin_registry
from sovereign_agent.tools.registry import (
    ToolRegistry,
    ToolResult,
    register_tool,
)


def test_register_tool_generates_valid_schema() -> None:
    reg = ToolRegistry()

    @register_tool(registry=reg)
    def my_tool(city: str, n: int = 5) -> dict:
        """Fetch something for a city."""
        return {"city": city, "n": n}

    assert "my_tool" in reg
    schema = reg.get("my_tool").discover()
    validate_schema(schema)
    assert schema["name"] == "my_tool"
    assert "city" in schema["parameters"]["properties"]
    assert "n" in schema["parameters"]["properties"]
    assert schema["parameters"]["required"] == ["city"]
    # Description comes from docstring.
    assert "Fetch" in schema["description"]


def test_register_tool_extracts_types_from_signature() -> None:
    reg = ToolRegistry()

    @register_tool(registry=reg)
    def typed(s: str, i: int, f: float, b: bool) -> dict:
        """x"""
        return {}

    schema = reg.get("typed").discover()
    props = schema["parameters"]["properties"]
    assert props["s"]["type"] == "string"
    assert props["i"]["type"] == "integer"
    assert props["f"]["type"] == "number"
    assert props["b"]["type"] == "boolean"


def test_duplicate_registration_raises() -> None:
    from sovereign_agent.errors import ValidationError

    reg = ToolRegistry()

    @register_tool(registry=reg)
    def t1() -> dict:
        """x"""
        return {}

    with pytest.raises(ValidationError):

        @register_tool(registry=reg, name="t1")
        def t2() -> dict:
            """x"""
            return {}


@pytest.mark.asyncio
async def test_tool_result_auto_wraps_dict() -> None:
    reg = ToolRegistry()

    @register_tool(registry=reg)
    def plain(x: str) -> dict:
        """ok"""
        return {"echo": x}

    result = await reg.get("plain").execute(x="hello")
    assert result.success is True
    assert result.output == {"echo": "hello"}
    assert "plain" in result.summary


@pytest.mark.asyncio
async def test_tool_exception_becomes_tool_error() -> None:
    reg = ToolRegistry()

    @register_tool(registry=reg)
    def breaks() -> dict:
        """x"""
        raise RuntimeError("oops")

    result = await reg.get("breaks").execute()
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "SA_TOOL_EXECUTION_FAILED"


@pytest.mark.asyncio
async def test_tool_invalid_args_become_tool_error() -> None:
    reg = ToolRegistry()

    @register_tool(registry=reg)
    def needs_x(x: str) -> dict:
        """x"""
        return {}

    result = await reg.get("needs_x").execute(wrong_kwarg="y")
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "SA_TOOL_INVALID_INPUT"


def test_get_unknown_raises_tool_error() -> None:
    reg = ToolRegistry()
    with pytest.raises(ToolError) as exc_info:
        reg.get("nope")
    assert exc_info.value.code == "SA_TOOL_NOT_FOUND"


# ---------------------------------------------------------------------------
# Builtins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_builtin_read_write_roundtrip(fresh_session: Session) -> None:
    reg = make_builtin_registry(fresh_session)
    write_result = await reg.get("write_file").execute(path="notes.md", content="hi")
    assert write_result.success is True
    read_result = await reg.get("read_file").execute(path="notes.md")
    assert read_result.success is True
    assert read_result.output["content"] == "hi"


@pytest.mark.asyncio
async def test_builtin_read_rejects_traversal(fresh_session: Session) -> None:
    reg = make_builtin_registry(fresh_session)
    result = await reg.get("read_file").execute(path="../../etc/passwd")
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "SA_IO_SESSION_ESCAPE"


@pytest.mark.asyncio
async def test_builtin_list_files(fresh_session: Session) -> None:
    reg = make_builtin_registry(fresh_session)
    await reg.get("write_file").execute(path="a.md", content="a")
    await reg.get("write_file").execute(path="b.md", content="b")
    result = await reg.get("list_files").execute(path=".")
    assert result.success
    names = [e["name"] for e in result.output["entries"]]
    assert "a.md" in names
    assert "b.md" in names


@pytest.mark.asyncio
async def test_builtin_handoff_writes_ipc_file(fresh_session: Session) -> None:
    reg = make_builtin_registry(fresh_session)
    result = await reg.get("handoff_to_structured").execute(
        reason="test", context="testing", data={"x": 1}
    )
    assert result.success is True
    assert (fresh_session.ipc_dir / "handoff_to_structured.json").exists()


@pytest.mark.asyncio
async def test_builtin_complete_writes_session_complete(fresh_session: Session) -> None:
    reg = make_builtin_registry(fresh_session)
    result = await reg.get("complete_task").execute(result={"answer": 42})
    assert result.success is True
    assert (fresh_session.ipc_dir / "session_complete.json").exists()


def test_discover_all_validates_every_builtin(fresh_session: Session) -> None:
    reg = make_builtin_registry(fresh_session)
    schemas = reg.discover_all()
    # Every schema validates.
    for s in schemas:
        validate_schema(s)
    names = {s["name"] for s in schemas}
    # Sanity: the core builtins are all there.
    assert {
        "read_file",
        "write_file",
        "list_files",
        "handoff_to_structured",
        "complete_task",
    } <= names


def test_tool_result_to_dict_serializable() -> None:
    import json

    r = ToolResult(success=True, output={"a": 1}, summary="ok")
    json.dumps(r.to_dict())
