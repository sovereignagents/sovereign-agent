"""Optional real Zeocore process behind the reader-owned loop and MCP boundary."""

import json
import os
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, Field

from sovereign_agent.agent_loop import run_loop
from sovereign_agent.mcp_client import MCPClient
from sovereign_agent.model_turn import ModelTurn, ToolCall
from sovereign_agent.tool_dispatch import Dispatcher, ExecutableTool


@pytest.mark.live
def test_real_zeocore_tool_runs_through_the_agent_dispatcher():
    python = os.environ.get("SOVEREIGN_AGENT_ZEOCORE_PYTHON")
    if not python:
        pytest.skip("explicit separate Zeocore interpreter required")
    server = Path(__file__).resolve().parents[1] / "book/always_on/appendices/zeocore_server_v1.py"
    clients = []

    class Arguments(BaseModel):
        model_config = ConfigDict(extra="forbid", strict=True)
        text: str = Field(max_length=4096)

    def count_report(args):
        with MCPClient(
            [python, str(server)], allowed=frozenset({"word_count"}), environment={}, timeout=5
        ) as client:
            clients.append(client)
            return client.invoke("word_count", args.model_dump())

    class Model:
        def complete(self, messages, *args, **kwargs):
            if not any(message["role"] == "tool" for message in messages):
                return ModelTurn(
                    calls=(
                        ToolCall(
                            id="report-1",
                            name="count_report",
                            arguments={"text": "Lucy has six vanilla tubs"},
                        ),
                    )
                )
            return ModelTurn("The report contains five words.")

    dispatcher = Dispatcher(
        [
            ExecutableTool(
                "count_report", "Count a bounded report through Zeocore.", Arguments, count_report
            )
        ],
        allowed=frozenset({"count_report"}),
    )
    result = run_loop(Model(), dispatcher, [{"role": "user", "content": "Count the report."}])
    assert result.status == "COMPLETED" and result.tool_calls == 1
    observation = next(message for message in result.messages if message["role"] == "tool")
    wrapped = json.loads(observation["content"])
    assert wrapped["ok"] is True and wrapped["value"]["isError"] is False
    external = json.loads(wrapped["value"]["content"][0]["text"])
    assert external["success"] is True and external["data"]["status"] == "success"
    assert external["data"]["data"] == {"word_count": 5, "char_count": 25}
    assert clients[0].process.poll() is not None
