"""Code reviewer scenario. Offline, deterministic.

Run:

    python -m examples.code_reviewer.run
"""

from __future__ import annotations

import asyncio
import json
import re
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
from sovereign_agent.tools.builtin import make_builtin_registry
from sovereign_agent.tools.registry import ToolResult, _RegisteredTool

# Sample file the agent "reviews". In a real scenario it'd be read from disk.
_SAMPLE_FILE = """\
from os import *
import sys, json

def do_everything_in_one_function(a, b, c, d, e, f):
    print("starting...")
    x = a + b
    y = c * d
    z = e - f
    print("midway:", x, y, z)
    for i in range(100):
        print(i)
        if i == 42:
            print("got it!")
    print("done.")
    return (x, y, z)
"""


# Dataflow integrity log. Every check_python_file call appends one
# entry. After the run, the post-run audit cross-checks the written
# review against this log — if the review cites findings that
# check_python_file never returned, the model fabricated.
_TOOL_CALL_LOG: list[dict] = []


def _check_python(source: str) -> ToolResult:
    """Deterministic Python smell check. Returns a list of findings."""
    findings: list[dict] = []

    if re.search(r"^\s*from\s+\S+\s+import\s+\*", source, re.MULTILINE):
        findings.append(
            {
                "severity": "warning",
                "issue": "wildcard_import",
                "note": "avoid `from x import *`; explicit imports are clearer",
            }
        )
    print_count = len(re.findall(r"\bprint\(", source))
    if print_count >= 3:
        findings.append(
            {
                "severity": "info",
                "issue": "many_prints",
                "note": f"{print_count} print() calls — consider logging or returning values instead",
            }
        )
    for m in re.finditer(r"def\s+(\w+)\s*\(([^)]*)\)", source):
        name = m.group(1)
        params = [p for p in m.group(2).split(",") if p.strip()]
        if len(params) > 4:
            findings.append(
                {
                    "severity": "warning",
                    "issue": "too_many_params",
                    "note": f"{name}() has {len(params)} parameters; consider grouping into a dataclass",
                }
            )
    lines = source.splitlines()
    for _i, fn_match in enumerate(re.finditer(r"^def\s+(\w+)", source, re.MULTILINE)):
        # Count lines of the function body (crude).
        start_line = source[: fn_match.start()].count("\n")
        body = "\n".join(lines[start_line + 1 : start_line + 200])
        body_lines = [
            ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("def ")
        ]
        if len(body_lines) > 10:
            findings.append(
                {
                    "severity": "info",
                    "issue": "long_function",
                    "note": f"{fn_match.group(1)}() body has ~{len(body_lines)} non-blank lines; consider splitting",
                }
            )
            break  # report once to keep the output focused

    return ToolResult(
        success=True,
        output={"findings": findings, "line_count": len(lines)},
        summary=f"check_python: {len(findings)} finding(s) across {len(lines)} line(s)",
    )


def _build_tool_registry(session) -> object:
    reg = make_builtin_registry(session)

    def check_python_file(source: str) -> ToolResult:
        """Check a Python source file for common smells and style issues."""
        result = _check_python(source)
        # Dataflow integrity log — capture what the tool actually saw
        # and what it returned. The post-run audit cross-checks this
        # against the written review.
        _TOOL_CALL_LOG.append(
            {
                "tool": "check_python_file",
                "source_preview": source[:80],
                "source_matches_sample": source.strip() == _SAMPLE_FILE.strip(),
                "findings": result.output["findings"],
                "finding_issues": [f["issue"] for f in result.output["findings"]],
                "line_count": result.output["line_count"],
            }
        )
        return result

    reg.register(
        _RegisteredTool(
            name="check_python_file",
            description="Scan a Python source string for common smells. Returns structured findings.",
            fn=check_python_file,
            parameters_schema={
                "type": "object",
                "properties": {"source": {"type": "string"}},
                "required": ["source"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=[],
            examples=[
                {
                    "input": {"source": "print('hi')\nprint('hi')\nprint('hi')\n"},
                    "output": {
                        "findings": [{"severity": "info", "issue": "many_prints", "note": "..."}],
                        "line_count": 3,
                    },
                }
            ],
        )
    )
    return reg


def _render_review_md(findings: list[dict], line_count: int) -> str:
    lines = ["# Code review", "", f"Scanned {line_count} line(s).", ""]
    if not findings:
        lines.append("No issues found.")
    else:
        lines.append(f"Found {len(findings)} issue(s):")
        lines.append("")
        for f in findings:
            sev = f["severity"].upper()
            lines.append(f"- **{sev}** · `{f['issue']}` — {f['note']}")
    return "\n".join(lines) + "\n"


def _build_fake_client() -> FakeLLMClient:
    # Pre-compute the review text so the scripted model "knows" the findings.
    findings_result = _check_python(_SAMPLE_FILE)
    review_md = _render_review_md(
        findings_result.output["findings"], findings_result.output["line_count"]
    )

    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "run check_python_file on the sample source and write review.md",
                "success_criterion": "review.md exists in workspace",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    check_call = ToolCall(
        id="c1",
        name="check_python_file",
        arguments={"source": _SAMPLE_FILE},
    )
    write_call = ToolCall(
        id="c2",
        name="write_file",
        arguments={"path": "review.md", "content": review_md},
    )
    complete_call = ToolCall(
        id="c3",
        name="complete_task",
        arguments={"result": {"review": "workspace/review.md"}},
    )
    return FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[check_call]),
            ScriptedResponse(tool_calls=[write_call]),
            ScriptedResponse(tool_calls=[complete_call]),
            ScriptedResponse(content="Review written."),
        ]
    )


async def run_scenario(real: bool) -> None:
    with example_sessions_dir("code_reviewer", persist=real) as sessions_root:
        session = create_session(
            scenario="code-reviewer",
            task="Review the attached Python file and write findings to workspace/review.md.",
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id} in {session.directory}")

        if real:
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
            client = _build_fake_client()
            planner_model = executor_model = "fake"

        tools = _build_tool_registry(session)
        half = LoopHalf(
            planner=DefaultPlanner(model=planner_model, client=client),
            executor=DefaultExecutor(model=executor_model, client=client, tools=tools),  # type: ignore[arg-type]
        )
        result = await half.run(session, {"task": "review the sample file"})
        print(f"outcome: {result.next_action}")

        review = session.workspace_dir / "review.md"
        review_text = review.read_text() if review.exists() else ""
        if review.exists():
            print()
            print("=== review.md ===")
            print(review_text)

        # ── Dataflow integrity audit ────────────────────────────────
        _print_dataflow_audit(review_text)

        if real:
            print(f"\nArtifacts persist at: {session.directory}")
            print(f'Inspect with: ls -R "{session.directory}"')


def _print_dataflow_audit(review_text: str) -> None:
    """Verify the written review cites only findings check_python_file returned.

    Catches three failure modes:
      1. Review written but check_python_file never called → pure fabrication
      2. Review cites findings (by issue-keyword) that weren't in the
         tool's output → model invented issues from training data
      3. Tool was called but with source ≠ the sample → model passed
         made-up source to the tool (class slides §04.6)
    """
    print("\n=== Dataflow integrity audit ===")
    if not _TOOL_CALL_LOG:
        print("  ✗  check_python_file was never called")
        if review_text:
            print("     → a review was written without any analysis; pure fabrication")
        return

    # Did the model pass real source to the tool?
    real_source_calls = [c for c in _TOOL_CALL_LOG if c["source_matches_sample"]]
    fake_source_calls = [c for c in _TOOL_CALL_LOG if not c["source_matches_sample"]]
    if fake_source_calls:
        print(f"  ✗  {len(fake_source_calls)} call(s) analysed FABRICATED source (not the sample)")
        for c in fake_source_calls[:3]:
            print(f"     passed: {c['source_preview']!r}...")
    if real_source_calls:
        print(f"  ✓  {len(real_source_calls)} call(s) analysed the real sample file")

    if not review_text:
        print("  (no review to audit)")
        return

    # Collect real findings across all calls that saw the real sample.
    real_issues = set()
    for c in real_source_calls:
        real_issues.update(c["finding_issues"])

    review_lower = review_text.lower()
    # How many of the real findings does the review mention?
    mentioned = [
        iss for iss in real_issues if iss.replace("_", " ") in review_lower or iss in review_lower
    ]
    if real_issues:
        print(f"  findings from tool referenced in review: {len(mentioned)}/{len(real_issues)}")
        missing = real_issues - set(mentioned)
        if missing:
            print(f"  ⚠  real findings not mentioned in review: {sorted(missing)}")

    # Heuristic fabrication check — if the review mentions functions
    # that don't exist in the sample (add, multiply, divide are the
    # class-slide example of this failure mode).
    sample_funcs = set(re.findall(r"def\s+(\w+)", _SAMPLE_FILE))
    # Match `word(` patterns in the review, excluding the sample's own.
    cited_funcs = set(re.findall(r"`(\w+)\(`|(\w+)\(\)", review_text))
    cited_funcs = {c[0] or c[1] for c in cited_funcs if (c[0] or c[1])}
    fabricated_funcs = cited_funcs - sample_funcs - {"print", "range"}
    if fabricated_funcs:
        print(f"  ✗  review mentions functions not in the sample: {sorted(fabricated_funcs)}")
        print(f"     sample only has: {sorted(sample_funcs)}")


def main() -> None:
    asyncio.run(run_scenario(real="--real" in sys.argv))


if __name__ == "__main__":
    main()
