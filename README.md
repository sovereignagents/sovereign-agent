# Sovereign Agent

**Build Your Always-On AI Agent From Scratch — in Python.**

[![CI](https://github.com/profrodai/sovereign-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/profrodai/sovereign-agent/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sovereign-agent.svg)](https://pypi.org/project/sovereign-agent/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Sovereign Agent is a self-contained teaching implementation for Lucy's ice cream
shop. The reader builds the model/tool loop, memory, local skills, messaging,
scheduling, permissions, recovery and operating report. Python 3.14, SQLite and
one direct runtime dependency keep the implementation inspectable. Zeocore is an
optional tool integration; the teaching agent does not require it.

The new [sixteen-chapter manuscript](book/always_on/README.md) is an **unreleased
construction draft** with executable checkpoints. It is not yet publication-ready
or available through the published PyPI version. The retained 1.x curriculum and
release commands below remain available while the new edition is reviewed.

## Run the constructed agent from this checkout

After the development install below, run the final accelerated day:

```bash
uv run --python 3.14 python book/always_on/checkpoints/ch16.py
```

It runs a separate simulated supplier, loses replies, kills a worker and verifies
two purchases totaling GBP 26.00 without a duplicate order. The phone transport
and model are deterministic fixtures in this checkpoint; no credentials or live
purchases are needed. The command removes its temporary state after checking it.
Use the checkpoint's `--output` option with a new directory to retain evidence.

For an initialized shop directory, `sovereign-agent agent report --root PATH`
prints the current ledger-derived report. Amounts come from structured records,
with uncertain outcomes and accounting disagreements made explicit. Current
retained totals are distinct from current-UTC-day model estimates and from a
provider invoice. See [Chapter 16](book/always_on/ch16_acceptance/README.md).

Always-on means unattended work and explicit restart/recovery behavior while the
host and dependencies are available. The [Linux deployment chapter](book/always_on/ch15_operation/README.md)
provides the one-host recipe. Maintained production organizations can graduate to
[Zeocore](https://github.com/profrodai/zeocore).

## Install and run with uv

[`uv`](https://docs.astral.sh/uv/) is the supported way to install and run
sovereign-agent. Try it without installing anything permanent:

```bash
uvx sovereign-agent@latest doctor
uvx sovereign-agent@latest demo store --mode simulated --root /tmp/first-shift
```

(`@latest` makes uv refresh its cached tool environment, so you always get
the current release.)

Or install the CLI onto your PATH:

```bash
uv tool install sovereign-agent
sovereign-agent doctor
```

(Plain `pip install sovereign-agent` still works in any Python 3.14
environment if you prefer it.)

The 1.x API intentionally replaces the v0.7 fleet framework. To keep using that
framework: `uvx "sovereign-agent<1"`.

## Educational development install

Python 3.14 is required; `uv` provides it automatically.

```bash
uv sync
uv run sovereign-agent doctor
```

Expected result:

```text
Sovereign Agent doctor
  Python:   3.14.x OK
  Pydantic: 2.x OK
  Network:  not required
  Tokens:   not required
  Providers:
    scripted available (streaming)
    claude   missing executable
    ...
Ready for the offline curriculum. Live providers are optional.
```

Chapter 0 is runnable as a **manually dispatched** store shift (no Pulse):

```bash
uv run sovereign-agent demo store --mode simulated
```

After the core book, run the six advanced mechanisms with no provider,
credential, or network:

```bash
uv run sovereign-agent mechanisms --root /tmp/sovereign-agent-mechanisms
```

This demonstrates four-plane isolation policy, durable condition scheduling,
recoverable context compaction, session-incarnation fencing, bounded tool
discovery, and provenance-bearing hybrid memory. See
[`book/ADVANCED_MECHANISMS.md`](book/ADVANCED_MECHANISMS.md).

See [`book/ch00_first_shift`](book/ch00_first_shift/README.md) and
[`book/ch03_actor_is_not_a_model`](book/ch03_actor_is_not_a_model/README.md).

## Product vocabulary

| Thing | Canonical word |
| --- | --- |
| Package and CLI | `sovereign-agent` |
| Control loop | `supervisor` |
| Installed OS hosting | `service` |
| Proactive wake | `pulse` |
| Liveness proof | `heartbeat` (records the runtime was alive; never creates work) |
| Intelligence CLI | `provider` |
| Governed identity | `actor` |

An actor is not a model. Every provider receives the same governed assignment
envelope and must emit a valid terminal event and write the exact
`ActorReport`. A zero exit without both is a failed receipt. Cursor's
`--workspace` is directory selection, not sandboxing; isolation belongs to
Sovereign Agent's disposable workspace.

Provider subprocesses receive only base process variables plus documented
credential allowlists: Claude (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
`CLAUDE_CODE_OAUTH_TOKEN`), Codex (`CODEX_API_KEY`), and Cursor
(`CURSOR_API_KEY`). Other parent secrets are not forwarded.

## Unit 1 gates

```bash
uv run python -m pytest -q
uv run python scripts/verify_runtime_dependencies.py
uv run python scripts/verify_source_budget_v2.py
uv run sovereign-agent --help
uv run sovereign-agent doctor
```

See the [educational reset ruling](docs/rulings/2026-08-25-educational-reset.md)
and [v0.7 migration guide](docs/migration-v0.7-to-v1.md).

## Project resources

- [Book and runnable exercises](book/README.md)
- [Architecture](docs/architecture.md) and [API reference](docs/api_reference.md)
- [Contributing guide](CONTRIBUTING.md)
- [Support](SUPPORT.md) and [security policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)
