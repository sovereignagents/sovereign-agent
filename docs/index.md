# sovereign-agent

**A framework for building always-on AI agents that you actually own.**

## What is it

Three things in one codebase:

1. A **production-ready Python framework** for always-on agents. `pip install sovereign-agent` and go.
2. A **build-from-scratch tutorial** that reconstructs the framework in five runnable chapters.
3. A **research vehicle** where new agent techniques from papers get implemented, compared against a baseline, and archived as dated lessons.

The core idea: the agent's **session directory is the unit of everything**. Memory, work queue, logs, tickets — all live as files under `sessions/sess_<id>/`. Nothing important lives in a database. This makes agents debuggable, recoverable from crashes, and portable between machines.

## Where to start

| If you want to... | Start here |
|---|---|
| Install and run a task in 5 minutes | [Quickstart](quickstart.md) |
| Understand the architecture | [Architecture](architecture.md) |
| Learn by building it from scratch | [Chapters](chapters/index.md) |
| Look up a class or function | [API Reference](api_reference.md) |
| Deploy it on a real machine | [Deployment](deployment.md) |

## Key properties

- **Offline-testable.** The framework ships with `FakeLLMClient` so you can write deterministic tests for your agent's trajectory without burning API credits.
- **Auditable by default.** Every action the agent takes produces a ticket with a verified manifest. `cat`ing the session directory tells you exactly what happened.
- **Provider-agnostic.** Any OpenAI-compatible endpoint works. Nebius Token Factory is the default.
- **Small surface area.** ~30 public names. Readable in an afternoon.

## Status

Alpha (v0.1.0). The spine is implemented and covered by 120 tests. Memory, voice, observability backends, and Rasa-based structured halves are skeletons with clear TODOs. See the [CHANGELOG](https://github.com/sovereignagents/sovereign-agent/blob/main/CHANGELOG.md) for the current status and the release readiness checklist in the [Architecture](architecture.md) doc §6.

## License

Apache 2.0.
