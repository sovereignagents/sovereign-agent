# Quickstart

## Install

```bash
pip install sovereign-agent            # core
pip install sovereign-agent[dev]       # core + test/lint/docs tooling
```

Requires Python 3.12+.

## Preflight

```bash
export NEBIUS_KEY="your-nebius-api-key"
sovereign-agent doctor
```

Doctor checks your Python version, API key, disk space, mount allowlist, and (unless you pass `--skip-llm`) makes one real LLM call. If everything reads ✓, you're ready.

## Minimal agent

```python
from sovereign_agent import run_task, register_tool, Config

@register_tool
def get_weather(city: str) -> dict:
    """Get the current weather for a city."""
    return {"city": city, "temperature": 18, "condition": "rainy"}

config = Config.from_env()
result = run_task("What's the weather in Edinburgh?", config=config)
print(result.summary)
```

Under the hood this creates a session directory at `sessions/sess_<id>/`, runs a planner, runs an executor with your tool registered, and returns a summary. The executor makes one or more tool calls; each one is an audit-traceable ticket.

## Inspect what happened

```bash
sovereign-agent sessions list
sovereign-agent sessions show <session_id>
sovereign-agent report <session_id>
```

The report command renders the complete session trace as markdown — timeline, tickets, handoffs, final result.

## Next steps

- Walk through the [chapters](chapters/index.md) to see how the framework is built from scratch.
- Read the [architecture doc](architecture.md) for the full rationale.
- Look at `examples/research_assistant/`, `examples/code_reviewer/`, `examples/pub_booking/` in the repo for end-to-end scenarios you can clone and modify.

## Swapping providers

Any OpenAI-compatible endpoint works:

```python
from sovereign_agent import Config

config = Config(
    llm_base_url="https://api.openai.com/v1/",
    llm_api_key_env="OPENAI_API_KEY",
    llm_planner_model="gpt-4",
    llm_executor_model="gpt-4o-mini",
)
```

## Offline testing

```python
from sovereign_agent._internal.llm_client import FakeLLMClient, ScriptedResponse
from sovereign_agent.planner import DefaultPlanner

client = FakeLLMClient([
    ScriptedResponse(content='[{"id": "sg_1", ...}]'),
    # ...
])
planner = DefaultPlanner(model="fake", client=client)
```

This is how every sovereign-agent test runs — deterministic, offline, fast.
