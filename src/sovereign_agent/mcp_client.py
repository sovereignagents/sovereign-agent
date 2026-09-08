"""A bounded POSIX stdio MCP client, pinned to protocol 2025-06-18.

Local operator-approved servers only. No HTTP, OAuth, sampling or subscriptions.
Starting a server grants that executable host access; MCP itself is not a sandbox.
"""

from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from types import TracebackType
from typing import Any


class MCPClient:
    def __init__(
        self,
        command: list[str],
        *,
        allowed: frozenset[str],
        environment: dict[str, str],
        timeout: float = 5,
    ) -> None:
        if os.name != "posix" or not command or not 0 < timeout <= 60:
            raise ValueError("POSIX, explicit server command and bounded timeout required")
        self.allowed, self.timeout = allowed, timeout
        self.sequence = 0
        self.buffer = b""
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
            start_new_session=True,
        )
        assert self.process.stdin and self.process.stdout
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            init = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "sovereign-agent-teaching", "version": "1"},
                },
            )
            if init.get("protocolVersion") != "2025-06-18" or "tools" not in init.get(
                "capabilities", {}
            ):
                raise ValueError("unsupported MCP version or missing tool capability")
            self._send(
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                time.monotonic() + timeout,
            )
            listing = self.request("tools/list", {})
            if listing.get("nextCursor"):
                raise ValueError("teaching client requires a bounded unpaginated tool set")
            tools = listing.get("tools")
            if (
                not isinstance(tools, list)
                or len(tools) > 32
                or any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("name"), str)
                    or not item["name"]
                    for item in tools
                )
            ):
                raise ValueError("invalid MCP tool list")
            self.discovered = {item["name"] for item in tools}
            if len(self.discovered) != len(tools):
                raise ValueError("duplicate MCP tool names")
        except BaseException:
            self.close()
            raise

    def _send(self, message: dict[str, Any], deadline: float) -> None:
        assert self.process.stdin
        raw = json.dumps(message, allow_nan=False).encode() + b"\n"
        if len(raw) > 16_384:
            raise ValueError("MCP request exceeds byte budget")
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            while raw:
                if not selector.select(max(0, deadline - time.monotonic())):
                    raise TimeoutError("MCP write timeout")
                written = os.write(self.process.stdin.fileno(), raw)
                raw = raw[written:]

    def _receive(self, deadline: float) -> dict[str, Any]:
        assert self.process.stdout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                if not selector.select(max(0, deadline - time.monotonic())):
                    raise TimeoutError("MCP response timeout")
                chunk = os.read(self.process.stdout.fileno(), 4096)
                if not chunk:
                    raise OSError("MCP server closed its response stream")
                self.buffer += chunk
                if len(self.buffer) > 65_536:
                    raise ValueError("MCP response exceeds byte budget")
        line, self.buffer = self.buffer.split(b"\n", 1)
        message = json.loads(line)
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ValueError("invalid MCP response envelope")
        return message

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.sequence += 1
        deadline = time.monotonic() + self.timeout
        self._send(
            {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}, deadline
        )
        for _ in range(16):
            message = self._receive(deadline)
            if "method" in message and "id" not in message:
                continue  # Bounded notifications; never execute server instructions.
            if (
                type(message.get("id")) is not int
                or message["id"] != self.sequence
                or "error" in message
            ):
                raise ValueError("MCP request failed or response identity mismatched")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ValueError("invalid MCP result")
            return result
        raise ValueError("MCP notification budget exhausted")

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self.allowed or name not in self.discovered:
            raise PermissionError("MCP discovery does not grant tool authority")
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        # The server may have forked children; end the isolated process group too.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=5)
        if self.process.stdin:
            self.process.stdin.close()
        if self.process.stdout:
            self.process.stdout.close()

    def __enter__(self) -> MCPClient:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
