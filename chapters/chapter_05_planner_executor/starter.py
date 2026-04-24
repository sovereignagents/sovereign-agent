"""Chapter 5 starter — the working agent.

Build, in order:

  1. parse_subgoals(raw_llm_output) — defensive JSON extraction that
     strips markdown fences, finds the first '[' and last ']', parses,
     and raises ValidationError on empty or non-array output.

  2. A DefaultExecutor.react_loop that:
       - sends a chat message to the LLM each turn
       - if the response has tool_calls, invokes each tool and appends
         the results back into the conversation
       - if a handoff_to_structured tool call is made, exits the loop
         with handoff_requested=True
       - stops when the response has no tool calls, or max_turns is hit

The real work — ticket discipline around each call, trace events, etc —
is already in the solution's re-exported DefaultPlanner/DefaultExecutor.
This starter focuses on the two bits most worth writing yourself.

Run `pytest chapters/chapter_05_planner_executor/tests.py -v`.
"""

from __future__ import annotations

from sovereign_agent.planner import Subgoal


def parse_subgoals(raw: str) -> list[Subgoal]:
    """Defensive JSON extraction from an LLM response.

    Handle all of:
      - plain JSON array
      - array wrapped in ```json ... ``` fences
      - array embedded in a preamble: "Sure! Here you go: [...]"

    Raise sovereign_agent.errors.ValidationError with code
    SA_VAL_INVALID_PLANNER_OUTPUT on malformed input.
    """
    raise NotImplementedError


async def react_loop_step(
    messages: list,
    llm_client,
    tools,
    max_turns: int = 8,
):
    """One step of a ReAct loop. Not required for this chapter — the
    solution's DefaultExecutor has the full implementation. Provided as
    a stub for students who want to try writing it themselves.
    """
    raise NotImplementedError
