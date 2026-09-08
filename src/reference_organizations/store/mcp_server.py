"""A single read-only MCP tool for the book; stdout contains protocol only."""

from __future__ import annotations

import json
import sys
from typing import Any

from reference_organizations.store.agent import CATALOG


def main() -> None:
    initialized = False
    negotiated = False
    for raw in iter(lambda: sys.stdin.buffer.readline(16_385), b""):
        if len(raw) > 16_384:
            return
        request = json.loads(raw)
        method = request.get("method")
        if method == "notifications/initialized":
            initialized = negotiated
            continue
        result: dict[str, Any] | None = None
        if (
            method == "initialize"
            and request.get("params", {}).get("protocolVersion") == "2025-06-18"
        ):
            negotiated = True
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "lucy-catalog", "version": "1"},
            }
        elif initialized and method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "catalog",
                        "description": "Read the teaching catalog, not live inventory.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    }
                ]
            }
        elif (
            initialized
            and method == "tools/call"
            and request.get("params") == {"name": "catalog", "arguments": {}}
        ):
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps([{"sku": row[0], "name": row[1]} for row in CATALOG]),
                    }
                ],
                "isError": False,
            }
        response = {"jsonrpc": "2.0", "id": request.get("id")}
        if result is None:
            response["error"] = {"code": -32602, "message": "Unsupported or invalid request"}
        else:
            response["result"] = result
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
