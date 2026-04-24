"""Research assistant example scenario.

Run offline (default, uses FakeLLMClient and a scripted web_lookup):

    python -m examples.research_assistant.run

Run live (requires NEBIUS_KEY):

    NEBIUS_KEY=... python -m examples.research_assistant.run --real
"""

from __future__ import annotations

import asyncio
import json
import sys

from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    OpenAICompatibleClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import create_session
from sovereign_agent.tickets.ticket import list_tickets
from sovereign_agent.tools.builtin import make_builtin_registry
from sovereign_agent.tools.registry import ToolResult, _RegisteredTool

# ---------------------------------------------------------------------------
# A mock web_lookup tool — scripted, deterministic, offline
# ---------------------------------------------------------------------------

_FIXTURE = {
    "retrieval augmented generation": [
        {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": "Lewis et al., 2020",
            "summary": (
                "Introduces RAG: combines a parametric seq2seq model with a "
                "non-parametric dense retrieval over Wikipedia."
            ),
            "arxiv": "2005.11401",
        },
        {
            "title": "From Local to Global: A Graph RAG Approach to Query-Focused Summarization",
            "authors": "Edge et al., 2024",
            "summary": (
                "GraphRAG: builds a knowledge graph over the corpus and uses "
                "community summaries for global question answering."
            ),
            "arxiv": "2404.16130",
        },
    ],
    "agent memory": [
        {
            "title": "MemGPT: Towards LLMs as Operating Systems",
            "authors": "Packer et al., 2023",
            "summary": (
                "Introduces hierarchical agent memory with explicit eviction "
                "policies; the model calls functions to page memory in and out."
            ),
            "arxiv": "2310.08560",
        },
    ],
}

# Keyword index for fuzzy fixture matching. A lookup like
# "RAG research papers" or "Retrieval-Augmented Generation" should hit
# the RAG entry even though neither is the literal key. Otherwise the
# model gets 0 results for legitimate variants and falls back to
# fabrication from training data (the failure mode from class §04.7).
_FIXTURE_KEYWORDS = {
    "retrieval augmented generation": ["rag", "retrieval", "augmented generation", "graphrag"],
    "agent memory": ["memory", "memgpt", "episodic", "working memory"],
}


def _match_fixture(query: str) -> list[dict]:
    """Return fixture hits for a query, with best-effort fuzzy matching.

    Strategy:
      1. Exact match on the canonical lowercase key (legacy behavior).
      2. If no exact hit, scan query tokens against _FIXTURE_KEYWORDS
         and return the first matching fixture entry.
      3. Otherwise return empty.

    This is intentionally simple — a real web_lookup would use an
    index. The point of the fixture is to give the model something
    to ground on for any reasonable variant of the query.
    """
    q = query.strip().lower()
    if q in _FIXTURE:
        return _FIXTURE[q]
    for fixture_key, keywords in _FIXTURE_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return _FIXTURE[fixture_key]
    return []


# Dataflow integrity log. Every _web_lookup call appends one entry
# here. After the run, the post-run audit cross-checks the written
# report against this log — if the report cites arXiv IDs or paper
# titles that never came back from _web_lookup, the model fabricated.
# This is the scenario-level check that catches failure #7 from class.
_TOOL_CALL_LOG: list[dict] = []


def _web_lookup(query: str) -> ToolResult:
    """Look up papers relevant to the query (scripted fixture for demo)."""
    hits = _match_fixture(query)
    _TOOL_CALL_LOG.append(
        {
            "query": query,
            "hit_count": len(hits),
            "arxiv_ids": [p["arxiv"] for p in hits],
            "titles": [p["title"] for p in hits],
        }
    )
    return ToolResult(
        success=True,
        output={"query": query, "results": hits, "count": len(hits)},
        summary=f"web_lookup({query!r}) → {len(hits)} result(s)",
    )


def _build_tool_registry(session) -> object:
    """Build a session-scoped tool registry that includes web_lookup on top of builtins."""
    reg = make_builtin_registry(session)
    reg.register(
        _RegisteredTool(
            name="web_lookup",
            description="Look up recent papers matching a topic query.",
            fn=_web_lookup,
            parameters_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=[],
            examples=[
                {
                    "input": {"query": "retrieval augmented generation"},
                    "output": {
                        "query": "retrieval augmented generation",
                        "results": [],
                        "count": 0,
                    },
                }
            ],
        )
    )
    return reg


# ---------------------------------------------------------------------------
# Scripted FakeLLMClient that drives the trajectory
# ---------------------------------------------------------------------------


def _build_fake_client(topic: str) -> FakeLLMClient:
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": f"look up papers on {topic} and write a short report",
                "success_criterion": "report.md exists in workspace",
                "estimated_tool_calls": 3,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    lookup_call = ToolCall(id="c1", name="web_lookup", arguments={"query": topic})
    # The "report" content is a function of the fixture; the scripted
    # model just has to claim it's writing the right thing.
    report_md = _render_report(topic)
    write_call = ToolCall(
        id="c2",
        name="write_file",
        arguments={"path": "report.md", "content": report_md},
    )
    complete_call = ToolCall(
        id="c3",
        name="complete_task",
        arguments={"result": {"report": "workspace/report.md"}},
    )
    return FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[lookup_call]),
            ScriptedResponse(tool_calls=[write_call]),
            ScriptedResponse(tool_calls=[complete_call]),
            ScriptedResponse(content="Report written to workspace/report.md."),
        ]
    )


def _render_report(topic: str) -> str:
    """Render a short markdown summary from the fixture for the scripted run."""
    papers = _match_fixture(topic)
    lines = [f"# Research summary: {topic}", ""]
    if not papers:
        lines.append("No results found in the fixture.")
    else:
        lines.append(f"Found {len(papers)} paper(s) on {topic}:")
        lines.append("")
        for p in papers:
            lines.append(f"## {p['title']}")
            lines.append(f"*{p['authors']}* — arXiv:{p['arxiv']}")
            lines.append("")
            lines.append(p["summary"])
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_scenario(topic: str, real: bool) -> None:
    with example_sessions_dir("research_assistant", persist=real) as sessions_root:
        task = (
            f"Research papers on: {topic}. Use ONLY the `web_lookup` tool "
            "to find papers — do not invent results from memory. "
            f"If web_lookup returns 0 results for a query, do NOT fabricate papers; "
            "try 1-2 variants of the query, and if still empty, say so in the report. "
            "When you have results, write a short report to workspace/report.md "
            "summarizing ONLY the papers web_lookup actually returned. Cite each "
            "paper's arXiv ID verbatim. Then call complete_task. "
            "Create exactly ONE subgoal for this task, assigned to the loop half."
        )
        session = create_session(
            scenario="research-assistant",
            task=task,
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id}")
        print(f"  dir: {session.directory}")

        if real:
            # Config.from_env() loads .env and reads SOVEREIGN_AGENT_LLM_*
            # overrides. This is how the user's configured models and API key
            # reach the example — instead of hardcoding them.
            from sovereign_agent.config import Config

            cfg = Config.from_env()
            print(f"  LLM: {cfg.llm_base_url} (live)")
            print(f"  planner:  {cfg.llm_planner_model}")
            print(f"  executor: {cfg.llm_executor_model}")
            client = OpenAICompatibleClient(
                base_url=cfg.llm_base_url,
                api_key_env=cfg.llm_api_key_env,
            )
            planner_model = cfg.llm_planner_model
            executor_model = cfg.llm_executor_model
        else:
            print("  LLM: FakeLLMClient (offline, scripted trajectory)")
            client = _build_fake_client(topic)
            planner_model = executor_model = "fake"

        tools = _build_tool_registry(session)
        planner = DefaultPlanner(model=planner_model, client=client)
        executor = DefaultExecutor(model=executor_model, client=client, tools=tools)  # type: ignore[arg-type]
        half = LoopHalf(planner=planner, executor=executor)

        result = await half.run(session, {"task": f"research papers on {topic}"})
        print(f"  outcome: {result.next_action}")
        print(f"  summary: {result.summary}\n")

        print("Tickets:")
        for t in list_tickets(session):
            r = t.read_result()
            print(f"  {t.ticket_id}  {t.operation:40s}  {r.state.value:8s}")
            print(f"      summary: {r.summary[:110]}")

        # Scan the whole workspace for any .md files the model wrote.
        # The task says workspace/report.md but the model doesn't always
        # comply with filenames (observed in real runs with MiniMax-M2.5).
        # For the integrity audit we care "was a report written?" — the
        # filename is a separate compliance concern.
        workspace_mds = sorted(session.workspace_dir.rglob("*.md"))
        report_path = session.workspace_dir / "report.md"
        if report_path.exists():
            print(f"\n=== {report_path.name} ===")
            print(report_path.read_text())
        elif workspace_mds:
            wrong_name = workspace_mds[0]
            print(f"\n⚠  report written to {wrong_name.name!r} (task asked for 'report.md')")
            print(f"=== {wrong_name.name} ===")
            print(wrong_name.read_text())
        else:
            print("\n(No report written.)")

        # ── Dataflow integrity audit ────────────────────────────────
        # Cross-check: every arXiv ID and paper title cited in the
        # written report must have come from a successful _web_lookup
        # call logged in _TOOL_CALL_LOG. If the report cites papers
        # that _web_lookup never returned, the model fabricated them
        # from training data — the exact failure class this scenario
        # exists to catch. See class slides §04.7 and §06.
        _print_dataflow_audit(workspace_mds)

        if real:
            print(f"\nArtifacts persist at: {session.directory}")
            print(f'Inspect with: ls -R "{session.directory}"')


def _print_dataflow_audit(workspace_mds: list) -> None:
    """Verify any written report cites only papers _web_lookup returned.

    Three failure modes caught here:
      1. Report cites an arXiv ID no _web_lookup call returned
         → fabricated from training data
      2. Report cites a paper title no _web_lookup call returned
         → likely fabricated (could be paraphrased, so treated as a
         warning not a hard fail)
      3. _web_lookup was never called but a report exists
         → pure fabrication with no retrieval at all

    The audit is informational — prints ✓ or ✗ and doesn't raise. The
    signal matters more than the failure; students and reviewers need
    to see which runs fabricated.
    """
    import re

    print("\n=== Dataflow integrity audit ===")
    if not _TOOL_CALL_LOG:
        print("  ✗  web_lookup was never called")
        if workspace_mds:
            print("     → a report was written without any retrieval; pure fabrication")
        return

    total_hits = sum(c["hit_count"] for c in _TOOL_CALL_LOG)
    real_arxiv_ids = {aid for c in _TOOL_CALL_LOG for aid in c["arxiv_ids"]}
    real_titles = {t for c in _TOOL_CALL_LOG for t in c["titles"]}
    print(
        f"  web_lookup calls: {len(_TOOL_CALL_LOG)}, "
        f"successful hits: {total_hits}, "
        f"unique papers returned: {len(real_arxiv_ids)}"
    )

    if not workspace_mds:
        print("  (no report to audit)")
        return

    # Concatenate all written markdown for the citation scan.
    report_text = "\n\n".join(p.read_text() for p in workspace_mds).lower()

    # arXiv IDs: strict check. Format NNNN.NNNNN (post-2007).
    cited_ids = set(re.findall(r"\b(\d{4}\.\d{4,5})\b", report_text))
    fabricated_ids = cited_ids - real_arxiv_ids
    if cited_ids:
        if fabricated_ids:
            print(f"  ✗  fabricated arXiv IDs: {sorted(fabricated_ids)}")
            print(f"     web_lookup only returned: {sorted(real_arxiv_ids) or '(none)'}")
        else:
            print(f"  ✓  all {len(cited_ids)} arXiv ID(s) came from web_lookup")
    elif real_arxiv_ids:
        print("  ⚠  report cites no arXiv IDs but web_lookup returned papers")

    # Titles: soft check. Titles can be paraphrased so a missing title
    # is a warning, not a fail.
    if real_titles:
        mentioned = sum(1 for t in real_titles if t.lower()[:30] in report_text)
        print(f"  titles from web_lookup referenced in report: {mentioned}/{len(real_titles)}")

    if total_hits == 0 and len(report_text) > 500:
        # Every web_lookup returned empty but a substantial report
        # was still written. This is the exact failure mode from the
        # Apr 23 2026 trace: 4 empty queries, then a 2500-char
        # fabricated summary of RAG papers from training data.
        print("  ✗  no web_lookup call returned results, but a report was still written")
        print("     → the model fabricated from training data; not grounded in tool output")


def main() -> None:
    real = "--real" in sys.argv
    # Pick a topic. The fixture recognizes two values; default to the first.
    # You can edit this to anything when running live.
    topic = "retrieval augmented generation"
    asyncio.run(run_scenario(topic, real=real))


if __name__ == "__main__":
    main()
