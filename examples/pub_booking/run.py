"""Pub booking scenario — the reference two-half trajectory.

Offline, deterministic. LoopHalf does the research; StructuredHalf does
the booking commit under explicit rules.

Run:

    python -m examples.pub_booking.run
"""

from __future__ import annotations

import asyncio
import json
import sys

from sovereign_agent._internal.atomic import atomic_write_text
from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    OpenAICompatibleClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.halves.structured import Rule, StructuredHalf
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import create_session
from sovereign_agent.tickets.ticket import list_tickets
from sovereign_agent.tools.builtin import make_builtin_registry
from sovereign_agent.tools.registry import ToolResult, _RegisteredTool

# ---------------------------------------------------------------------------
# Fixture: a small curated list of Edinburgh pubs
# ---------------------------------------------------------------------------

_PUBS = [
    {
        "id": "haymarket_tap",
        "name": "Haymarket Tap",
        "area": "Haymarket",
        "open_now": True,
        "seats_available_evening": 12,
    },
    {
        "id": "royal_oak",
        "name": "The Royal Oak",
        "area": "Old Town",
        "open_now": True,
        "seats_available_evening": 4,
    },
    {
        "id": "sheep_heid",
        "name": "The Sheep Heid Inn",
        "area": "Duddingston",
        "open_now": False,
        "seats_available_evening": 0,
    },
]


# Dataflow integrity log. Wrapped tools record their args + results
# here. Post-run audit verifies any committed booking matches a pub
# that pub_search returned and was confirmed available by pub_availability.
_TOOL_CALL_LOG: list[dict] = []


def _pub_search(city: str, near: str = "", open_now: bool = True) -> ToolResult:
    """Search pubs matching the given constraints (scripted fixture)."""
    if city.lower() != "edinburgh":
        return ToolResult(
            success=True,
            output={"city": city, "results": []},
            summary=f"pub_search: no fixture for city {city!r}",
        )
    hits = [
        p
        for p in _PUBS
        if (not near or near.lower() in p["area"].lower()) and (not open_now or p["open_now"])
    ]
    return ToolResult(
        success=True,
        output={"city": city, "near": near, "results": hits, "count": len(hits)},
        summary=f"pub_search({city}, near={near!r}): {len(hits)} open result(s)",
    )


def _pub_availability(pub_id: str, party: int, time: str) -> ToolResult:
    """Check whether a pub has capacity for a party at a time (scripted)."""
    pub = next((p for p in _PUBS if p["id"] == pub_id), None)
    if pub is None:
        return ToolResult(
            success=False,
            output={"pub_id": pub_id},
            summary=f"pub_availability: unknown pub_id {pub_id!r}",
        )
    available = pub["open_now"] and pub["seats_available_evening"] >= party
    return ToolResult(
        success=True,
        output={
            "pub_id": pub_id,
            "name": pub["name"],
            "party": party,
            "time": time,
            "available": available,
            "seats_reported": pub["seats_available_evening"],
        },
        summary=(
            f"pub_availability({pub['name']}, party={party}, {time}): "
            f"{'AVAILABLE' if available else 'UNAVAILABLE'}"
        ),
    )


def _build_tool_registry(session) -> object:
    reg = make_builtin_registry(session)

    def pub_search(city: str, near: str = "", open_now: bool = True) -> ToolResult:
        """Search pubs by city, optionally filtered by area and open-now status."""
        result = _pub_search(city, near, open_now)
        _TOOL_CALL_LOG.append(
            {
                "tool": "pub_search",
                "args": {"city": city, "near": near, "open_now": open_now},
                "pub_ids": [p["id"] for p in result.output.get("results", [])],
                "pub_names": [p["name"] for p in result.output.get("results", [])],
            }
        )
        return result

    def pub_availability(pub_id: str, party: int, time: str) -> ToolResult:
        """Check whether a pub can seat a party at a given time."""
        result = _pub_availability(pub_id, party, time)
        _TOOL_CALL_LOG.append(
            {
                "tool": "pub_availability",
                "args": {"pub_id": pub_id, "party": party, "time": time},
                "available": result.output.get("available", False),
                "pub_name": result.output.get("pub_name"),
            }
        )
        return result

    reg.register(
        _RegisteredTool(
            name="pub_search",
            description="Search pubs by city, area, open-now status.",
            fn=pub_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "near": {"type": "string", "default": ""},
                    "open_now": {"type": "boolean", "default": True},
                },
                "required": ["city"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=[],
            examples=[
                {
                    "input": {"city": "Edinburgh", "near": "Haymarket", "open_now": True},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )
    reg.register(
        _RegisteredTool(
            name="pub_availability",
            description="Check whether a specific pub can seat a party at a time.",
            fn=pub_availability,
            parameters_schema={
                "type": "object",
                "properties": {
                    "pub_id": {"type": "string"},
                    "party": {"type": "integer"},
                    "time": {"type": "string"},
                },
                "required": ["pub_id", "party", "time"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=[],
            examples=[
                {
                    "input": {"pub_id": "haymarket_tap", "party": 4, "time": "19:30"},
                    "output": {"available": True, "seats_reported": 12},
                }
            ],
        )
    )
    return reg


# ---------------------------------------------------------------------------
# StructuredHalf rules for the booking step
# ---------------------------------------------------------------------------

_PARTY_SIZE_CAP = 8


def _build_structured_half(session) -> StructuredHalf:
    """Two rules. The first fires on a confirm payload and writes the booking.
    The second escalates when the party is too large for automated booking."""

    def _confirm_matches(d: dict) -> bool:
        return d.get("action") == "confirm_booking" and int(d.get("party", 0)) <= _PARTY_SIZE_CAP

    def _confirm_action(d: dict) -> dict:
        booking_md = (
            "# Booking confirmed\n\n"
            f"- **Pub:** {d.get('pub_name', d.get('pub_id', '?'))}\n"
            f"- **Time:** {d.get('time', '?')}\n"
            f"- **Party size:** {d.get('party', '?')}\n"
            "- **Status:** confirmed by the structured half under party-size rule\n"
        )
        atomic_write_text(session.workspace_dir / "booking.md", booking_md)
        return {"wrote": "workspace/booking.md", "pub": d.get("pub_id"), "party": d.get("party")}

    def _escalate_if_party_too_big(d: dict) -> bool:
        return int(d.get("party", 0)) > _PARTY_SIZE_CAP

    return StructuredHalf(
        rules=[
            Rule(
                name="confirm_under_cap",
                condition=_confirm_matches,
                action=_confirm_action,
                escalate_if=_escalate_if_party_too_big,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Scripted LLM trajectory
# ---------------------------------------------------------------------------


def _build_fake_client(party: int = 4) -> FakeLLMClient:
    plan_json = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "find an open Edinburgh pub near Haymarket with capacity for 4",
                "success_criterion": "availability confirmed for a specific pub",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            },
            {
                "id": "sg_2",
                "description": "confirm the booking via the structured half",
                "success_criterion": "booking.md written",
                "estimated_tool_calls": 0,
                "depends_on": ["sg_1"],
                "assigned_half": "structured",
            },
        ]
    )
    search_call = ToolCall(
        id="c1",
        name="pub_search",
        arguments={"city": "Edinburgh", "near": "Haymarket", "open_now": True},
    )
    availability_call = ToolCall(
        id="c2",
        name="pub_availability",
        arguments={"pub_id": "haymarket_tap", "party": party, "time": "19:30"},
    )
    # Executor responds with plain text at the end of sg_1 (since sg_2 goes to
    # the structured half, the loop half exits on its own after sg_1).
    return FakeLLMClient(
        [
            ScriptedResponse(content=plan_json),
            ScriptedResponse(tool_calls=[search_call]),
            ScriptedResponse(tool_calls=[availability_call]),
            ScriptedResponse(
                content="Haymarket Tap has 12 seats available; handing off to structured half for booking."
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_scenario(real: bool, party: int = 4) -> None:
    with example_sessions_dir("pub_booking", persist=real) as sessions_root:
        task = (
            f"Book a pub table in EDINBURGH (not London, not any other city) "
            f"near Haymarket Station for a party of {party} at 19:30 tonight.\n\n"
            "Use these tools in ORDER:\n"
            "  1. pub_search(city='Edinburgh', near='Haymarket', open_now=True) — "
            "find candidate pubs.\n"
            "  2. pub_availability(pub_id=..., party=..., time='19:30') — "
            "check each candidate until one confirms availability.\n"
            "  3. handoff_to_structured with the chosen pub_id — the structured "
            "half will commit the booking under policy rules.\n\n"
            "IMPORTANT: the city MUST be 'Edinburgh' (lowercase 'e' is fine too, "
            "the fixture is case-insensitive). Do NOT search London or any other "
            "city; the fixture only contains Edinburgh pubs and other queries "
            "return zero results."
        )
        session = create_session(
            scenario="pub-booking",
            task=task,
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id}")
        print(f"  dir: {session.directory}")

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
            client = _build_fake_client(party=party)
            planner_model = executor_model = "fake"

        # ---- Loop half (research) ---------------------------------------
        tools = _build_tool_registry(session)
        loop_half = LoopHalf(
            planner=DefaultPlanner(model=planner_model, client=client),
            executor=DefaultExecutor(model=executor_model, client=client, tools=tools),  # type: ignore[arg-type]
        )
        loop_result = await loop_half.run(
            session, {"task": "find and confirm an Edinburgh pub near Haymarket"}
        )
        print(f"\nLoop half outcome: {loop_result.next_action}")
        print(f"  summary: {loop_result.summary}")

        # ---- Structured half (booking commit) ---------------------------
        if loop_result.next_action == "handoff_to_structured":
            structured = _build_structured_half(session)
            structured_input = {
                "action": "confirm_booking",
                "pub_id": "haymarket_tap",
                "pub_name": "Haymarket Tap",
                "party": party,
                "time": "19:30",
            }
            struct_result = await structured.run(session, structured_input)
            print(f"\nStructured half outcome: {struct_result.next_action}")
            print(f"  summary: {struct_result.summary}")

        # ---- Inspect -----------------------------------------------------
        booking = session.workspace_dir / "booking.md"
        booking_text = booking.read_text() if booking.exists() else ""
        if booking.exists():
            print()
            print("=== booking.md ===")
            print(booking_text)

        print("Tickets produced:")
        for t in list_tickets(session):
            r = t.read_result()
            print(f"  {t.ticket_id}  {t.operation:42s}  {r.state.value}")

        # ── Dataflow integrity audit ────────────────────────────────
        _print_dataflow_audit(booking_text, party=party)

        if real:
            print(f"\nArtifacts persist at: {session.directory}")
            print(f'Inspect with: ls -R "{session.directory}"')


def _print_dataflow_audit(booking_text: str, party: int) -> None:
    """Verify a committed booking was grounded in pub_search + pub_availability.

    Catches:
      1. Booking cites a pub that pub_search never returned
      2. Booking committed for a pub that pub_availability marked unavailable
      3. Booking party size doesn't match what pub_availability was checked with
    """
    print("\n=== Dataflow integrity audit ===")
    search_calls = [c for c in _TOOL_CALL_LOG if c["tool"] == "pub_search"]
    avail_calls = [c for c in _TOOL_CALL_LOG if c["tool"] == "pub_availability"]
    print(f"  pub_search calls: {len(search_calls)}, pub_availability calls: {len(avail_calls)}")

    if not booking_text:
        if not _TOOL_CALL_LOG:
            print("  (no booking, no tool calls — structured half escalated without work)")
        elif search_calls and not any(c["pub_names"] for c in search_calls):
            # Called pub_search repeatedly but every call returned empty.
            # This is usually wrong-city or wrong-area arguments.
            print(
                f"  ✗  no booking written: {len(search_calls)} pub_search call(s) "
                "all returned empty results"
            )
            print("     queries the model tried:")
            for c in search_calls[:6]:
                args = c["args"]
                print(
                    f"       pub_search(city={args['city']!r}, "
                    f"near={args['near']!r}, open_now={args['open_now']})"
                )
            print(
                "     → the fixture only knows Edinburgh pubs; real runs of this "
                "scenario require the task prompt to enforce city='Edinburgh' "
                "explicitly. If the model searched elsewhere, the scenario's task "
                "text needs tightening."
            )
        else:
            print(f"  ✗  no booking written despite {len(_TOOL_CALL_LOG)} tool call(s)")
            print("     → the loop half completed without handing off to the structured half")
        return

    # Pubs the model actually saw via pub_search
    seen_pub_names = {pn for c in search_calls for pn in c["pub_names"]}

    booking_lower = booking_text.lower()

    # Find which seen pub the booking references
    referenced = [name for name in seen_pub_names if name.lower() in booking_lower]
    if referenced:
        print(f"  ✓  booking references pub(s) returned by pub_search: {referenced}")
    elif seen_pub_names:
        print("  ✗  booking mentions no pub from pub_search results")
        print(f"     pub_search returned: {sorted(seen_pub_names)}")
    elif "confirmed" in booking_lower or "booked" in booking_lower:
        print("  ✗  booking claims confirmation but pub_search was never called")

    # Availability ground truth
    for c in avail_calls:
        if c["pub_name"] and c["pub_name"].lower() in booking_lower:
            if c["available"]:
                print(f"  ✓  pub_availability confirmed {c['pub_name']!r} is available")
            else:
                print(
                    f"  ✗  booking proceeds for {c['pub_name']!r} but pub_availability said unavailable"
                )

    # Party-size consistency — the booking text should not contradict
    # what we asked pub_availability about.
    for c in avail_calls:
        if c["args"]["party"] != party:
            print(
                f"  ⚠  pub_availability checked party={c['args']['party']} "
                f"but scenario ran with party={party}"
            )


def main() -> None:
    oversize = "--oversize" in sys.argv
    party = 12 if oversize else 4
    asyncio.run(run_scenario(real="--real" in sys.argv, party=party))


if __name__ == "__main__":
    main()
