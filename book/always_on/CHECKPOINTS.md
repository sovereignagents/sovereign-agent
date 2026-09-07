# Runnable chapter checkpoints

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

Every checkpoint is available from the same source checkout as the manuscript. Run it from the repository root with the frozen environment described in [the conventions](CONVENTIONS.md). Ordinary checkpoint runs use fixtures; live flags are explicit and chapter-specific. They never require live purchasing.

| Chapter | Manuscript | Executable checkpoint |
| --- | --- | --- |
| 1 | [Make the first model call for Lucy](ch01_first_model_call/README.md) | [ch01.py](checkpoints/ch01.py) |
| 2 | [Give the agent reliable shop tools](ch02_shop_tools/README.md) | [ch02.py](checkpoints/ch02.py) |
| 3 | [Build the model and tool loop](ch03_agent_loop/README.md) | [ch03.py](checkpoints/ch03.py) |
| 4 | [Remember across conversations](ch04_memory/README.md) | [ch04.py](checkpoints/ch04.py) |
| 5 | [Reuse a tested opening procedure](ch05_skills/README.md) | [ch05.py](checkpoints/ch05.py) |
| 6 | [Talk to the agent from your phone](ch06_messaging/README.md) | [ch06.py](checkpoints/ch06.py) |
| 7 | [Wake up for schedules and stock events](ch07_scheduling/README.md) | [ch07.py](checkpoints/ch07.py) |
| 8 | [Ask permission before spending](ch08_approval/README.md) | [ch08.py](checkpoints/ch08.py) |
| 9 | [Survive the ambiguous supplier order](ch09_ambiguous_order/README.md) | [ch09.py](checkpoints/ch09.py) |
| 10 | [Recover work after a process crash](ch10_worker_recovery/README.md) | [ch10.py](checkpoints/ch10.py) |
| 11 | [Isolate tools and untrusted content](ch11_isolation/README.md) | [ch11.py](checkpoints/ch11.py) |
| 12 | [Measure whether the agent helps](ch12_evaluation/README.md) | [ch12.py](checkpoints/ch12.py) |
| 13 | [Improve behavior with evaluated changes](ch13_improvement/README.md) | [ch13.py](checkpoints/ch13.py) |
| 14 | [Delegate one bounded task](ch14_delegation/README.md) | [ch14.py](checkpoints/ch14.py) |
| 15 | [Deploy and maintain the agent](ch15_operation/README.md) | [ch15.py](checkpoints/ch15.py) |
| 16 | [Lucy leaves the shop for a day](ch16_acceptance/README.md) | [ch16.py](checkpoints/ch16.py) |

The final checkpoint supports a new output directory for the two databases, readable report and JSON evidence:

```bash
uv run --python 3.14 python book/always_on/checkpoints/ch16.py --output /tmp/lucy-day-first-run
```

Choose a different path for a second retained run; the checkpoint refuses to overwrite the first. Its separate supplier database is essential evidence. The expected two accepted orders total 2600 pence. Physical vanilla stock ends at eight tubs after one receiving event, strawberry has one physical tub plus four pending, and chocolate remains at twelve. These are authored expectations for the fixture, not a business forecast.

The original thirteen chapters and adversarial labs remain in the [original curriculum](../README.md). Their paths and lesson identities have not been repurposed as new chapter numbers. Use the checkpoint matching the edition you are reading.
