"""Two explicitly enabled edges using the same typed dispatcher as stock work."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from reference_organizations.store.agent import NoArguments, shop_dispatcher
from sovereign_agent.database import Database
from sovereign_agent.mcp_client import MCPClient
from sovereign_agent.model_turn import ToolCall
from sovereign_agent.sandbox_tool import run_python
from sovereign_agent.tool_dispatch import ExecutableTool


class ReportArguments(NoArguments):
    source: str = Field(min_length=1, max_length=16_384)


@dataclass(frozen=True)
class Sandbox:
    image: str
    scratch: Path
    docker_host: str | None = None


def optional_tools(
    db: Database, *, mcp_catalog: bool = False, sandbox: Sandbox | None = None
) -> list[ExecutableTool]:
    tools = []
    if mcp_catalog:

        def catalog(_: NoArguments):
            with MCPClient(
                [sys.executable, "-m", "reference_organizations.store.mcp_server"],
                allowed=frozenset({"catalog"}),
                environment={},
            ) as client:
                return client.invoke("catalog", {})

        tools.append(
            ExecutableTool(
                "catalog_mcp",
                "Read product names through the local MCP catalog; not live stock.",
                NoArguments,
                catalog,
            )
        )
    if sandbox:

        def report(args: ReportArguments):
            assert sandbox is not None
            stock = shop_dispatcher(db).invoke(
                ToolCall(id="snapshot", name="list_stock", arguments={})
            )
            if not stock["ok"]:
                raise ValueError("cannot assemble report data")
            try:
                return run_python(
                    args.source,
                    {"stock": stock["value"]},
                    image=sandbox.image,
                    scratch=sandbox.scratch,
                    docker_host=sandbox.docker_host,
                )
            except subprocess.TimeoutExpired:
                raise TimeoutError("container control deadline expired") from None

        tools.append(
            ExecutableTool(
                "python_report",
                "Run bounded Python in the configured isolated container. "
                "Read stock JSON from /input/data.json and print the report; "
                "no network or purchases.",
                ReportArguments,
                report,
            )
        )
    return tools
