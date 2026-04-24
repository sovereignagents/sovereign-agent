# Pub booking — the reference Edinburgh scenario

This is the reference scenario from the Nebius Academy course (SOW §5). The task: find a pub in Edinburgh matching some constraints, check its availability, and either confirm a booking or escalate to a structured half for confirmation.

## What it demonstrates

Every piece of sovereign-agent that matters:

- **Planner produces subgoals** where one is assigned to the loop half (research) and one to the structured half (confirmation).
- **The loop half runs to completion on its subgoal** (finds candidate pubs, picks one, checks availability).
- **Handoff to the structured half** for the booking confirmation (because "commit to a reservation" is high-stakes and belongs under explicit rules, not free-form LLM reasoning).
- **Structured half rules** — one fires on "confirm" input and writes the booking, another escalates if the party size exceeds a cap.

## Run

```bash
python -m examples.pub_booking.run
```

Offline, deterministic. Uses scripted LLM responses and a fixture of Edinburgh pubs.

## The shape of the trajectory

1. Planner: 2 subgoals. sg_1 (loop) = "find pub matching constraints"; sg_2 (structured) = "confirm booking".
2. Loop executor, turn 1: `pub_search(city="Edinburgh", near="Haymarket", open_now=True)` → 3 candidates.
3. Loop executor, turn 2: `pub_availability(pub_id="haymarket_tap", party=4, time="19:30")` → slot available.
4. Loop executor, turn 3: exits the loop (subgoal done, next subgoal is structured).
5. LoopHalf returns `handoff_to_structured`.
6. StructuredHalf evaluates rules: `party_under_cap` matches → action: write the booking to `workspace/booking.md` and return `complete`.

## Why a structured half for this

Because a scripted rule is correct and testable, while "an LLM reads a confirmation prompt and decides whether to book" is neither. The loop half does the research (open-ended, creative). The structured half commits to the reservation (deterministic, auditable). That's the whole point of two halves.
