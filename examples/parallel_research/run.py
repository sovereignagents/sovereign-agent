"""Parallel research — Module 1 (`parallel_safe=True`) in action.

## What this shows

A research agent looks up details for five arXiv papers in a single
ReAct turn. Each lookup takes 0.3s to simulate a real network call.

Sequentially: 5 × 0.3s = 1.5s of wall-clock time.
In parallel:  max(0.3s) ≈ 0.3s of wall-clock time.

Run both and compare.

## Why this matters

Students in class asked: "why does the research agent do one arXiv call
at a time when it could do twenty at once?" v0.2 answers: it doesn't
have to. Mark the lookup tool `parallel_safe=True` and the executor
batches contiguous parallel-safe calls into an `asyncio.gather`.

## Run

    python -m examples.parallel_research.run              # offline, fake LLM
    python -m examples.parallel_research.run --sequential # force sequential
    python -m examples.parallel_research.run --real       # real LLM
"""

from __future__ import annotations

import asyncio
import sys
import time

from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    OpenAICompatibleClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.executor import (
    PARALLELISM_POLICY_DEFAULT,
    PARALLELISM_POLICY_NEVER,
    DefaultExecutor,
)
from sovereign_agent.planner import Subgoal
from sovereign_agent.session.directory import create_session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

# ---------------------------------------------------------------------------
# Tool: a fake arXiv lookup that sleeps to simulate a real network call
# ---------------------------------------------------------------------------

_FAKE_ARXIV: dict[str, dict] = {
    "2401.00001": {"title": "Attention is (still) all you need", "year": 2024},
    "2402.00002": {"title": "Scaling laws at the frontier", "year": 2024},
    "2403.00003": {"title": "Structured retrieval for long-context LLMs", "year": 2024},
    "2404.00004": {"title": "Verifier-guided decoding", "year": 2024},
    "2405.00005": {"title": "Agents as filesystems", "year": 2024},
}


# Dataflow integrity log. Every fetch_arxiv_paper call records whether
# the paper ID was a hit or a miss. The post-run audit flags the class
# of failure where the LLM fabricates arXiv IDs (seen in the 2026-04-23
# real-LLM run: model made up IDs like 2305.12345, all missed, no
# signal that the run was useless).
_TOOL_CALL_LOG: list[dict] = []


async def _fetch_arxiv_paper(paper_id: str) -> ToolResult:
    """Simulate a remote arXiv API call. Sleeps 0.3s to model network latency."""
    await asyncio.sleep(0.3)
    if paper_id not in _FAKE_ARXIV:
        _TOOL_CALL_LOG.append({"paper_id": paper_id, "hit": False})
        return ToolResult(
            success=False,
            output={"paper_id": paper_id},
            summary=f"arxiv lookup failed: {paper_id} not found",
        )
    meta = _FAKE_ARXIV[paper_id]
    _TOOL_CALL_LOG.append({"paper_id": paper_id, "hit": True, "title": meta["title"]})
    return ToolResult(
        success=True,
        output={"paper_id": paper_id, **meta},
        summary=f"arxiv {paper_id}: {meta['title']!r}",
    )


def _build_tool_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        _RegisteredTool(
            name="fetch_arxiv_paper",
            description=(
                "Look up metadata for one arXiv paper by its ID. "
                "Read-only HTTP. Safe to call concurrently with other lookups."
            ),
            fn=_fetch_arxiv_paper,
            parameters_schema={
                "type": "object",
                "properties": {"paper_id": {"type": "string"}},
                "required": ["paper_id"],
            },
            returns_schema={"type": "object"},
            is_async=True,
            # *** THE KEY LINE ***
            # Without this, the executor runs the calls sequentially.
            # With this, contiguous parallel_safe calls are batched via
            # asyncio.gather in a single ReAct turn.
            parallel_safe=True,
            examples=[
                {
                    "input": {"paper_id": "2401.00001"},
                    "output": {"paper_id": "2401.00001", "title": "..."},
                }
            ],
        )
    )
    return reg


# ---------------------------------------------------------------------------
# Scripted LLM: asks for all five lookups in ONE turn, then summarises.
# ---------------------------------------------------------------------------


def _build_fake_client() -> FakeLLMClient:
    paper_ids = list(_FAKE_ARXIV.keys())
    return FakeLLMClient(
        [
            # Turn 1: emit all five tool calls in a single assistant message.
            # This is the shape the v0.2 system prompt encourages: multiple
            # independent reads in one turn.
            ScriptedResponse(
                tool_calls=[
                    ToolCall(
                        id=f"call_{i}",
                        name="fetch_arxiv_paper",
                        arguments={"paper_id": pid},
                    )
                    for i, pid in enumerate(paper_ids, start=1)
                ]
            ),
            # Turn 2: assemble and return the summary.
            ScriptedResponse(
                content=("Retrieved metadata for all five papers: " + "; ".join(_FAKE_ARXIV.keys()))
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_scenario(*, real: bool, force_sequential: bool) -> None:
    with example_sessions_dir("parallel_research", persist=real) as sessions_root:
        session = create_session(
            scenario="parallel-research",
            task="Look up details for five arXiv papers.",
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id}")
        print(f"  dir: {session.directory}")

        if real:
            from sovereign_agent.config import Config

            cfg = Config.from_env()
            print(f"  LLM: {cfg.llm_base_url} (live)")
            print(f"  executor: {cfg.llm_executor_model}")
            client = OpenAICompatibleClient(
                base_url=cfg.llm_base_url,
                api_key_env=cfg.llm_api_key_env,
            )
            executor_model = cfg.llm_executor_model
        else:
            client = _build_fake_client()
            executor_model = "fake"

        tools = _build_tool_registry()

        policy = PARALLELISM_POLICY_NEVER if force_sequential else PARALLELISM_POLICY_DEFAULT
        executor = DefaultExecutor(
            model=executor_model,
            client=client,  # type: ignore[arg-type]
            tools=tools,
            parallelism_policy=policy,
        )
        print(f"  parallelism_policy: {policy}")

        subgoal = Subgoal(
            id="sg_1",
            description="Look up metadata for five arXiv papers.",
            success_criterion="Metadata fetched for every paper ID.",
            estimated_tool_calls=5,
            assigned_half="loop",
        )

        t0 = time.monotonic()
        result = await executor.execute(subgoal, session, max_turns=4)
        elapsed = time.monotonic() - t0

        print(f"\nExecutor finished in {elapsed:.2f}s wall clock")
        print(f"  success: {result.success}")
        print(f"  turns_used: {result.turns_used}")
        print(f"  tool calls made: {len(result.tool_calls_made)}")
        for tc in result.tool_calls_made:
            print(f"    - {tc['name']}({tc['arguments']}) -> {tc['summary']}")

        # Quick pedagogical hint: 5 calls × 0.3s = 1.5s sequential; parallel
        # finishes in roughly the slowest single call (≈0.3s + overhead).
        if force_sequential:
            expected = 5 * 0.3
            print(
                f"\nExpected (sequential, {len(result.tool_calls_made)} × 0.3s): ≥{expected:.1f}s"
            )
        else:
            print("\nExpected (parallel, max(0.3s each) + overhead): ≤0.7s")

        # ── Dataflow integrity audit ────────────────────────────────
        _print_dataflow_audit()

        if real:
            print(f"\nArtifacts persist at: {session.directory}")
            print(f'Inspect with: ls -R "{session.directory}"')


def _print_dataflow_audit() -> None:
    """Flag runs where the LLM fabricated arXiv IDs (observed on 2026-04-23).

    fetch_arxiv_paper returns success=False when the paper ID isn't in
    the fixture. The framework records each call as "made" regardless.
    Without this audit, a run where every call missed still reports
    `success: True, turns_used: 2` — the framework's definition of
    success is "the loop exited cleanly," not "the work was useful."
    """
    print("\n=== Dataflow integrity audit ===")
    if not _TOOL_CALL_LOG:
        print("  ✗  fetch_arxiv_paper was never called")
        return

    hits = [c for c in _TOOL_CALL_LOG if c["hit"]]
    misses = [c for c in _TOOL_CALL_LOG if not c["hit"]]
    hit_rate = len(hits) / len(_TOOL_CALL_LOG)

    print(
        f"  fetch_arxiv_paper calls: {len(_TOOL_CALL_LOG)}, "
        f"hits: {len(hits)}, misses: {len(misses)} "
        f"(hit rate: {hit_rate:.0%})"
    )

    if hit_rate == 0:
        print("  ✗  every arXiv ID the model requested was fabricated (0 hits)")
        print(f"     fixture only knows: {sorted(_FAKE_ARXIV.keys())}")
        print(f"     model requested:    {sorted(c['paper_id'] for c in misses)}")
        print("     → this run produced no grounded output; the LLM made up IDs")
    elif hit_rate < 0.5:
        print(f"  ⚠  low hit rate ({hit_rate:.0%}) — model fabricated {len(misses)} IDs")
        print(f"     fabricated IDs: {sorted(c['paper_id'] for c in misses)}")
    else:
        print(f"  ✓  {len(hits)}/{len(_TOOL_CALL_LOG)} IDs came from the fixture")


def main() -> None:
    real = "--real" in sys.argv
    force_sequential = "--sequential" in sys.argv
    asyncio.run(run_scenario(real=real, force_sequential=force_sequential))


if __name__ == "__main__":
    main()
