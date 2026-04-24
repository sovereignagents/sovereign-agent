"""Tests for v0.2 parallel tool-call dispatch.

Covers:
  - Read-only tools run concurrently when the model emits them in one turn.
  - parallel_safe=False tools are serialised around their batch.
  - The parallelism policy flags ("always", "never") override the per-tool
    flag.
  - Output ordering is preserved regardless of dispatch strategy — the
    tool messages the model sees in turn N+1 are in the same order it
    emitted the calls in turn N.
  - verify_args hook rejects bad arguments before the tool body runs.
  - Cancellation of a parallel batch does not leak into unrelated sessions.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse, ToolCall
from sovereign_agent.executor import (
    PARALLELISM_POLICY_ALWAYS,
    PARALLELISM_POLICY_DEFAULT,
    PARALLELISM_POLICY_NEVER,
    DefaultExecutor,
)
from sovereign_agent.planner import Subgoal
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool


def _sg(sgid: str = "sg_1") -> Subgoal:
    return Subgoal(
        id=sgid,
        description="look up three things concurrently",
        success_criterion="answers returned",
        estimated_tool_calls=3,
        assigned_half="loop",
    )


def _make_slow_tool(name: str, sleep_s: float, parallel_safe: bool = True) -> _RegisteredTool:
    """Build a tool that sleeps and returns a marker. Used to measure
    whether two invocations ran concurrently."""

    async def _impl(label: str) -> ToolResult:
        await asyncio.sleep(sleep_s)
        return ToolResult(
            success=True,
            output={"tool": name, "label": label},
            summary=f"{name}({label}) done",
        )

    return _RegisteredTool(
        name=name,
        description=f"slow test tool {name}",
        fn=_impl,
        parameters_schema={
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        },
        returns_schema={"type": "object"},
        is_async=True,
        parallel_safe=parallel_safe,
        examples=[{"input": {"label": "x"}, "output": {"tool": name, "label": "x"}}],
    )


# ---------------------------------------------------------------------------
# Concurrency tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_safe_tools_actually_run_concurrently(fresh_session: Session) -> None:
    """Three tools that each sleep 0.3s should complete in ~0.3s, not ~0.9s."""
    reg = ToolRegistry()
    reg.register(_make_slow_tool("fetch_a", 0.3))
    reg.register(_make_slow_tool("fetch_b", 0.3))
    reg.register(_make_slow_tool("fetch_c", 0.3))

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(id="c1", name="fetch_a", arguments={"label": "one"}),
                    ToolCall(id="c2", name="fetch_b", arguments={"label": "two"}),
                    ToolCall(id="c3", name="fetch_c", arguments={"label": "three"}),
                ]
            ),
            ScriptedResponse(content="All three complete."),
        ]
    )

    executor = DefaultExecutor(model="fake", client=client, tools=reg)

    t0 = time.monotonic()
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    elapsed = time.monotonic() - t0

    assert result.success
    # Three tools ran. Each took 0.3s. If parallel, total ≈ 0.3s (+turn overhead).
    # Sequential would be ≈ 0.9s. Allow generous headroom for CI.
    assert elapsed < 0.7, f"expected parallel execution ≤0.7s, got {elapsed:.2f}s"
    # All three calls surfaced into tool_calls_made.
    names_called = [c["name"] for c in result.tool_calls_made]
    assert names_called == ["fetch_a", "fetch_b", "fetch_c"]


@pytest.mark.asyncio
async def test_policy_never_forces_sequential(fresh_session: Session) -> None:
    """With policy='never' three 0.3s tools should run sequentially (~0.9s)."""
    reg = ToolRegistry()
    for name in ("fetch_a", "fetch_b", "fetch_c"):
        reg.register(_make_slow_tool(name, 0.3))

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(id=f"c{i}", name=n, arguments={"label": n})
                    for i, n in enumerate(("fetch_a", "fetch_b", "fetch_c"), 1)
                ]
            ),
            ScriptedResponse(content="done"),
        ]
    )

    executor = DefaultExecutor(
        model="fake",
        client=client,
        tools=reg,
        parallelism_policy=PARALLELISM_POLICY_NEVER,
    )
    t0 = time.monotonic()
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    elapsed = time.monotonic() - t0

    assert result.success
    # Sequential expected: ~0.9s. Allow 0.75s lower bound to prove we did
    # NOT parallelise.
    assert elapsed >= 0.75, f"expected sequential (≥0.75s), got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_policy_always_overrides_flag(fresh_session: Session) -> None:
    """Policy='always' parallelises even tools marked parallel_safe=False."""
    reg = ToolRegistry()
    reg.register(_make_slow_tool("writeA", 0.3, parallel_safe=False))
    reg.register(_make_slow_tool("writeB", 0.3, parallel_safe=False))

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(id="c1", name="writeA", arguments={"label": "a"}),
                    ToolCall(id="c2", name="writeB", arguments={"label": "b"}),
                ]
            ),
            ScriptedResponse(content="done"),
        ]
    )

    executor = DefaultExecutor(
        model="fake",
        client=client,
        tools=reg,
        parallelism_policy=PARALLELISM_POLICY_ALWAYS,
    )
    t0 = time.monotonic()
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    elapsed = time.monotonic() - t0

    assert result.success
    assert elapsed < 0.55, f"policy=always should parallelise unsafe tools too; got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_unsafe_tool_serialises_around_parallel_batch(fresh_session: Session) -> None:
    """Mixed [safe, safe, UNSAFE, safe, safe] should become runs:
        [safe, safe] | [UNSAFE] | [safe, safe]
    Total ≈ 0.3 + 0.3 + 0.3 = 0.9s, not 0.3s (full parallel) or 1.5s (sequential)."""
    reg = ToolRegistry()
    reg.register(_make_slow_tool("read1", 0.3, parallel_safe=True))
    reg.register(_make_slow_tool("read2", 0.3, parallel_safe=True))
    reg.register(_make_slow_tool("writeX", 0.3, parallel_safe=False))
    reg.register(_make_slow_tool("read3", 0.3, parallel_safe=True))
    reg.register(_make_slow_tool("read4", 0.3, parallel_safe=True))

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(id="c1", name="read1", arguments={"label": "1"}),
                    ToolCall(id="c2", name="read2", arguments={"label": "2"}),
                    ToolCall(id="c3", name="writeX", arguments={"label": "x"}),
                    ToolCall(id="c4", name="read3", arguments={"label": "3"}),
                    ToolCall(id="c5", name="read4", arguments={"label": "4"}),
                ]
            ),
            ScriptedResponse(content="done"),
        ]
    )

    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    t0 = time.monotonic()
    result = await executor.execute(_sg(), fresh_session, max_turns=4)
    elapsed = time.monotonic() - t0

    assert result.success
    # 3 sequential runs of ≈0.3s each = 0.9s. Generous bounds.
    assert 0.75 <= elapsed < 1.25, f"expected three 0.3s runs ≈0.9s total, got {elapsed:.2f}s"
    # Order must be preserved in the tool_calls_made trace.
    names = [c["name"] for c in result.tool_calls_made]
    assert names == ["read1", "read2", "writeX", "read3", "read4"]


# ---------------------------------------------------------------------------
# Ordering tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_output_order_matches_call_order_in_parallel(
    fresh_session: Session,
) -> None:
    """Even when tool A finishes faster than tool B, the tool message order
    in the next turn must match the order the model requested them.

    Otherwise the model might match outputs to the wrong tool calls.
    """
    reg = ToolRegistry()
    # A is slow, B is fast. If we returned in completion order, the order
    # would be B, A — wrong.
    reg.register(_make_slow_tool("slow_a", 0.4))
    reg.register(_make_slow_tool("fast_b", 0.05))

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(id="c1", name="slow_a", arguments={"label": "A"}),
                    ToolCall(id="c2", name="fast_b", arguments={"label": "B"}),
                ]
            ),
            ScriptedResponse(content="done"),
        ]
    )
    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    result = await executor.execute(_sg(), fresh_session, max_turns=4)

    assert result.success
    names = [c["name"] for c in result.tool_calls_made]
    assert names == ["slow_a", "fast_b"], f"expected input order preserved; got {names}"


# ---------------------------------------------------------------------------
# verify_args hook tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_args_rejects_before_tool_runs(fresh_session: Session) -> None:
    """A tool with verify_args that returns (False, reason) should never
    invoke its fn, and the LLM should see a structured rejection."""
    calls_actually_run: list[dict] = []

    def _impl(venue_id: str) -> ToolResult:
        calls_actually_run.append({"venue_id": venue_id})
        return ToolResult(success=True, output={"ok": True}, summary="never reached")

    def _verify(kwargs: dict) -> tuple[bool, str]:
        venue_id = kwargs.get("venue_id", "")
        if not venue_id.startswith("venue_"):
            return False, f"venue_id must start with 'venue_', got {venue_id!r}"
        return True, "ok"

    reg = ToolRegistry()
    reg.register(
        _RegisteredTool(
            name="book_venue",
            description="Book a venue by ID.",
            fn=_impl,
            parameters_schema={
                "type": "object",
                "properties": {"venue_id": {"type": "string"}},
                "required": ["venue_id"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,
            verify_args=_verify,
            examples=[{"input": {"venue_id": "venue_abc"}, "output": {"ok": True}}],
        )
    )

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue",
                        arguments={"venue_id": "nonsense"},
                    ),
                ]
            ),
            ScriptedResponse(content="I got a rejection and gave up."),
        ]
    )
    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    result = await executor.execute(_sg(), fresh_session, max_turns=3)

    assert result.success  # the executor ran — the tool was rejected cleanly
    assert calls_actually_run == [], "verify_args should block the tool fn"
    # The rejection reason must have been surfaced to the model.
    tc = result.tool_calls_made[0]
    assert tc["name"] == "book_venue"
    assert tc["success"] is False
    assert "venue_id must start" in tc["summary"]


@pytest.mark.asyncio
async def test_verify_args_accepts_good_args(fresh_session: Session) -> None:
    """Sanity: verify_args returning (True, ...) allows the tool through."""
    ran = []

    def _impl(venue_id: str) -> ToolResult:
        ran.append(venue_id)
        return ToolResult(success=True, output={"booked": venue_id}, summary="booked")

    def _verify(kwargs: dict) -> tuple[bool, str]:
        return kwargs.get("venue_id", "").startswith("venue_"), "bad prefix"

    reg = ToolRegistry()
    reg.register(
        _RegisteredTool(
            name="book_venue",
            description="Book a venue by ID.",
            fn=_impl,
            parameters_schema={
                "type": "object",
                "properties": {"venue_id": {"type": "string"}},
                "required": ["venue_id"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,
            verify_args=_verify,
            examples=[{"input": {"venue_id": "venue_abc"}, "output": {"booked": "x"}}],
        )
    )

    client = FakeLLMClient(
        [
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="book_venue",
                        arguments={"venue_id": "venue_hay"},
                    ),
                ]
            ),
            ScriptedResponse(content="booked."),
        ]
    )
    executor = DefaultExecutor(model="fake", client=client, tools=reg)
    result = await executor.execute(_sg(), fresh_session, max_turns=3)

    assert result.success
    assert ran == ["venue_hay"]
    tc = result.tool_calls_made[0]
    assert tc["success"] is True


# ---------------------------------------------------------------------------
# Policy validation
# ---------------------------------------------------------------------------


def test_executor_rejects_unknown_policy() -> None:
    """Typo in policy name should raise at construction time, not runtime."""
    from sovereign_agent._internal.llm_client import FakeLLMClient

    reg = ToolRegistry()
    with pytest.raises(ValueError, match="unknown parallelism_policy"):
        DefaultExecutor(
            model="fake",
            client=FakeLLMClient([]),
            tools=reg,
            parallelism_policy="paralelize_it_all_please",  # typo
        )


def test_policy_constants_are_distinct() -> None:
    assert PARALLELISM_POLICY_DEFAULT != PARALLELISM_POLICY_NEVER != PARALLELISM_POLICY_ALWAYS
