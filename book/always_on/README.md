# Build Your Always-On AI Agent From Scratch

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

Tools, memory, permissions, and reliable operation in Python.

Lucy is the customer; you are the Python-capable builder. Implement the loop,
tool dispatch, persistent context, jobs, permissions and recovery yourself, using
model APIs, SQLite and operating-system services as infrastructure. A finished
agent framework or private Zeocore service is not required.

Use the [exercises companion](exercises/README.md) for the canonical practical units and generated notebooks. The earlier [educator companion](educator/educator-companion-v2.md) remains the classroom record while successor units are built chapter by chapter.

All sixteen construction drafts have runnable checkpoints. The old thirteen
chapters and their labs remain at their original paths. Source-to-site migration,
editorial review and real phone acceptance remain open; a passing construction
gate is not publication approval.

| Chapter | Construction outcome |
| --- | --- |
| 1 | [Make the first model call for Lucy](ch01_first_model_call/README.md) |
| 2 | [Give the agent reliable shop tools](ch02_shop_tools/README.md) |
| 3 | [Build the model and tool loop](ch03_agent_loop/README.md) |
| 4 | [Remember across conversations](ch04_memory/README.md) |
| 5 | [Reuse a tested opening procedure](ch05_skills/README.md) |
| 6 | [Talk to the agent from your phone](ch06_messaging/README.md) |
| 7 | [Wake up for schedules and stock events](ch07_scheduling/README.md) |
| 8 | [Ask permission before spending](ch08_approval/README.md) |
| 9 | [Survive the ambiguous supplier order](ch09_ambiguous_order/README.md) |
| 10 | [Recover work after a process crash](ch10_worker_recovery/README.md) |
| 11 | [Isolate tools and untrusted content](ch11_isolation/README.md) |
| 12 | [Measure whether the agent helps](ch12_evaluation/README.md) |
| 13 | [Improve behavior with evaluated changes](ch13_improvement/README.md) |
| 14 | [Delegate one bounded task](ch14_delegation/README.md) |
| 15 | [Deploy and maintain the agent](ch15_operation/README.md) |
| 16 | [Lucy leaves the shop for a day](ch16_acceptance/README.md) |

Run a checkpoint from the repository root with the frozen development environment:

```bash
uv sync --frozen
uv run --python 3.14 python book/always_on/checkpoints/ch16.py
```

The final checkpoint combines one morning routine, model failure and retry,
duplicate and unauthorized message delivery, corrected memory, scoped shortages,
exact approvals, lost supplier responses, a killed worker, receiving and bounded
research. Its independent supplier retains two orders totaling 2600 pence. The
readable report distinguishes physical stock, pending replenishment and purchase
expenditure. Telegram transport and models are fixtures in this accelerated run;
Linux service, live model and container evidence are separate pinned experiments.

Use `--output` with a new directory to keep both databases, report and evidence.
The same directory cannot be overwritten by another run. The complete gate is
`make verify`; the new edition's construction check is
`uv run python scripts/verify_always_on_v1.py`. Its `--complete` mode additionally
requires publication-ready chapter statuses, which these drafts do not claim.

The current implementation remains within a measured budget covering **all
installed teaching code**, including replaceable integrations. The budget is a
constraint on explainability, not a claim that every supported extension fits a
particular line count forever. See the root source-budget gate and versioned
construction receipts in `docs/evidence/always-on/`.
