# Build sovereign-agent from scratch

> **Why chapters live alongside the library code (not in a separate repo).**
>
> Two dominant teaching patterns exist for ML/agent libraries:
>
> - **Raschka pattern** (*"Build a Large Language Model From Scratch"*, `rasbt/LLMs-from-scratch`).
>   Chapters and production code live in one tree. The tutorial code **is** the
>   library, viewed from a pedagogical angle. Students learn by re-implementing
>   pieces of the real thing.
> - **Howard pattern** (`fastai/fastai` library + `fastai/course22` course).
>   Library and course are **separate repos**. The course *uses* the library; it
>   does not rebuild it.
>
> sovereign-agent's chapters follow the **Raschka pattern**. Each chapter's
> `solution.py` re-exports from `sovereign_agent/` directly, and
> `tools/verify_chapter_drift.py` enforces that they stay in sync. You're not
> learning a toy copy — you're learning the framework itself.
>
> The Week-5 homework that lives in a separate repo (`homework-*`) is the
> Howard pattern: a scenario built *on top of* `pip install sovereign-agent`.
> Different pedagogy, different tree.

Five chapters that reconstruct the spine of sovereign-agent in sequence. Each chapter builds one architectural idea, ends with a runnable demo, and its solution file is byte-for-byte the same code as the corresponding module in `sovereign_agent/`. A CI check (`tools/verify_chapter_drift.py`) enforces this so the tutorial cannot drift from the framework.

This is the minitorch trick applied to agent systems: the tutorial *is* the production code, just viewed from a different angle.

## The sequence

1. **[Chapter 1 — Session directory](chapter_01_session/)** — Decision 1. The unit of everything.
2. **[Chapter 2 — SessionQueue](chapter_02_queue/)** — Decisions 2, 4, 8. Per-session serialization, global cap, retry, idle preemption, graceful shutdown.
3. **[Chapter 3 — IPC and Tickets](chapter_03_ipc/)** — Decisions 3, 9. Filesystem IPC, ticket state machine, manifest discipline.
4. **[Chapter 4 — Scheduler](chapter_04_scheduler/)** — Decision 6. Drift-corrected recurring tasks.
5. **[Chapter 5 — Planner, Executor, Tools, Halves](chapter_05_planner_executor/)** — The full working agent. Decisions 5 and 7 sneak in here as production-readiness concerns.

## How to work through a chapter

Each chapter directory contains:

- `README.md` — the narrative. Read this first.
- `starter.py` — skeleton with `raise NotImplementedError` bodies. Your job is to fill it in.
- `solution.py` — the completed code. Mirrors the corresponding `sovereign_agent/` module.
- `tests.py` — pytest tests. Run `pytest chapters/chapter_N_*/tests.py` to check your work.
- `demo.py` — runnable demo at the end. `python chapters/chapter_N_*/demo.py`.

Expected flow: read the README, copy `starter.py` to a scratch file, fill in the NotImplementedError bodies, run the tests until they pass, check your code against `solution.py`, then run `demo.py` and see it work. The whole sequence is designed to take 5–8 hours of focused work for someone comfortable with Python 3.12 and asyncio.

## Why five chapters and not eight

The eight architectural decisions don't map 1:1 to chapters. A decision on its own doesn't make a runnable demo — a session directory without a queue isn't interesting, and a queue without a session isn't interesting. Chapters are the unit of "something you can run and see working." Five chapters, five runnable demos, one working agent at the end.

This is the same trade-off Sasha Rush makes in minitorch (four modules) and Karpathy makes in nanoGPT (two files). The unit is "demo," not "concept."

## Where to go after the chapters

When you've finished the chapters, the homework repos (`homework-*`) are the next step: build a new scenario on the framework you've now understood from the inside. The first one is [`homework-pub-booking`](https://github.com/sovereignagents/homework-pub-booking) — extend sovereign-agent into a full hybrid pub-booking system with a real LLM, Rasa CALM callbacks, and a voice pipeline. See that repo's README for the current assignment.
