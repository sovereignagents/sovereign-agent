# Chapter 5 — The working agent

**Architectural decisions built:** 5 (credential gateway), 7 (mount allowlist). Plus the two-stage planner/executor split, tools with `discover()` (Pattern A), loop + structured halves, handoff protocol, and a minimal orchestrator that ties them together.

**Time to complete:** about 3 hours.

**Prerequisites:** Chapters 1–4. Python 3.12+, a basic understanding of tool-calling LLMs, and either a Nebius API key or willingness to run the `FakeLLMClient` that the demo defaults to.

## What this chapter is

The first four chapters gave you a substrate, a queue, IPC + tickets, and a scheduler. None of them reasoned. This chapter adds the two pieces that actually make the system *intelligent*: a **planner** that turns a raw task into an ordered list of subgoals, and an **executor** that runs each subgoal through a ReAct-style tool-call loop.

Plus a `LoopHalf` that composes the planner and executor, a `Handoff` protocol that lets the loop half pass control to a structured half for rule-following work, and a minimal orchestrator that reads `session.json` and decides what to do next.

At the end of this chapter you have a working always-on agent. You give it a task, it plans, it executes, it writes files in the workspace, it can call `complete_task` or hand off to a structured half, and everything it did is auditable in the session directory.

## Why two stages (planner + executor)

The empirical finding is that thinking-mode models (large reasoning models like `Qwen/Qwen3-Next-80B-A3B-Thinking`) plan multi-step tasks better but are wasteful for tool execution because they spend several seconds thinking before each tool call. Fast tool-calling models (dense 32B-class) execute efficiently but are less good at multi-step planning.

Splitting the roles lets each model play to its strengths. In practice, this pattern lifts task success rate by 15–30% on multi-step tasks *while reducing* total latency, because the executor moves much faster than a thinking model would. Claude Code, OpenHands, SWE-agent, and Devin all converge on this split.

## Why the ticket discipline matters even more here

Every planner call is a ticket. Every executor call is a ticket. Every tool call inside the executor is nested inside the executor's ticket. This is not accidental: it means you can point at any action the agent took and inspect exactly what it did, what the inputs were, what the output was, how long it took, and whether the manifest still verifies.

Without this, debugging an agent trajectory is archaeology. With it, it's reading a directory.

## Why we use `FakeLLMClient` in the demo

The demo ships with a `FakeLLMClient` that returns scripted responses. This is deliberate. It means:

- The demo runs offline.
- The demo is deterministic (temperature=0 plus scripted responses = byte-identical session directories across runs).
- The demo shows the architecture without the reader needing to understand the LLM call.

Swap in `OpenAICompatibleClient(base_url=..., api_key_env="NEBIUS_KEY")` for the real thing — the rest of the code is unchanged. This is the whole point of the `LLMClient` protocol.

## What the demo does

Give the agent this task: *"Write 'hello' to greet.md in the workspace, then mark the task complete."*

The scripted planner returns one subgoal assigned to the loop half. The scripted executor runs two tool calls: `write_file(path="greet.md", content="hello")` and `complete_task(result={"wrote": "greet.md"})`. The third executor turn is a short final answer.

When the demo is done, you can inspect the session directory:

```
sessions/sess_<id>/
├── session.json            state: completed
├── SESSION.md              task description
├── workspace/
│   └── greet.md            "hello"
├── logs/
│   ├── trace.jsonl         every event the agent emitted
│   └── tickets/
│       ├── tk_<planner>/   planner.plan — SUCCESS, manifest verifies
│       └── tk_<executor>/  executor.run_subgoal/sg_1 — SUCCESS, 2 tool calls
└── ipc/
    └── session_complete.json   <-- written by the complete_task tool
```

Every ticket has a `summary.md` you can read, a `manifest.json` whose checksums still verify, and a `raw_output.json` with the full trace data.

## Where to find what

This chapter's `solution.py` re-exports the production classes from `sovereign_agent.planner`, `sovereign_agent.executor`, `sovereign_agent.halves.loop`, `sovereign_agent.halves.structured`, `sovereign_agent.handoff`, and `sovereign_agent.orchestrator`. The minitorch trick: the solution **is** the framework.

## Status

The solution is complete. The demo runs end-to-end. `tests/integration/test_end_to_end.py` exercises this exact trajectory with assertions on every side effect. A `starter.py` (skeleton with `NotImplementedError` bodies for the planner and executor ReAct loop) is a natural next exercise; it's tracked on the v1.0 release checklist.

## Run the demo

```bash
python -m chapters.chapter_05_planner_executor.demo
```

For the network-gated version that calls a real LLM, set `NEBIUS_KEY` and pass `--real`:

```bash
NEBIUS_KEY=... python -m chapters.chapter_05_planner_executor.demo --real
```
