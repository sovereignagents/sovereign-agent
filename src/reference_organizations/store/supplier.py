"""Independent supplier process and database for lost-response experiments.

Only loopback HTTP is supported. This deliberately cannot purchase real stock.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from sovereign_agent.http_transport import request


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sku: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=1000)
    unit_cost_pence: int = Field(gt=0, le=100_000)
    supplier: str = Field(pattern="^lucy-local$")
    currency: str = Field(pattern="^GBP$")


class SupplierClient:
    idempotent = True

    def __init__(self, endpoint: str, *, timeout: float = 3) -> None:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("simulated supplier requires a loopback HTTP endpoint")
        self.endpoint, self.timeout = endpoint.rstrip("/"), timeout

    def _call(
        self, operation: str, proposal: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        if not re.fullmatch("[a-f0-9]{32}", operation):
            raise ValueError("invalid operation identity")
        response = request(
            self.endpoint + "/orders/" + operation,
            data=None if proposal is None else json.dumps(proposal).encode(),
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
            maximum_bytes=16_384,
        )
        if proposal is None and response.status == 404:
            return None
        if response.status != 200:
            raise OSError("supplier request failed")
        result = json.loads(response.body)
        if not isinstance(result, dict):
            raise ValueError("invalid supplier receipt")
        return result

    def lookup(self, operation: str) -> dict[str, Any] | None:
        return self._call(operation)

    def order(self, operation: str, proposal: dict[str, Any]) -> dict[str, Any]:
        result = self._call(operation, proposal)
        if result is None:
            raise ValueError("supplier omitted receipt")
        return result


def serve(
    path: Path, port: int, *, drop_first_response: bool = False, ready: Path | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS orders(operation TEXT PRIMARY KEY,"
        "proposal TEXT NOT NULL,receipt TEXT NOT NULL)"
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # No request or credentials in a teaching service log.

        def reply(self, code: int, data: dict[str, Any]) -> None:
            raw = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def operation(self) -> str | None:
            match = re.fullmatch(r"/orders/([a-f0-9]{32})", self.path)
            return match[1] if match else None

        def do_GET(self) -> None:  # noqa: N802
            operation = self.operation()
            row = connection.execute(
                "SELECT receipt FROM orders WHERE operation=?", (operation,)
            ).fetchone()
            self.reply(200, json.loads(row[0])) if row else self.reply(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            operation = self.operation()
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if operation is None or not 1 <= length <= 4096:
                    raise ValueError("invalid request")
                proposal = Proposal.model_validate_json(
                    self.rfile.read(length), strict=True
                ).model_dump()
                encoded = json.dumps(proposal, sort_keys=True)
            except ValueError:
                self.reply(400, {"error": "invalid_proposal"})
                return
            row = connection.execute(
                "SELECT proposal,receipt FROM orders WHERE operation=?", (operation,)
            ).fetchone()
            if row:
                self.reply(200, json.loads(row[1])) if row[0] == encoded else self.reply(
                    409, {"error": "identity_conflict"}
                )
                return
            receipt = {"operation": operation, "proposal": proposal, "status": "ACCEPTED"}
            with connection:
                connection.execute(
                    "INSERT INTO orders VALUES (?,?,?)", (operation, encoded, json.dumps(receipt))
                )
            if drop_first_response:
                # The supplier has committed. Only its reply disappears.
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.reply(200, receipt)

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 5
    if ready:
        ready.write_text(str(server.server_port))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--drop-first-response", action="store_true")
    args = parser.parse_args()
    serve(args.database, args.port, drop_first_response=args.drop_first_response, ready=args.ready)


if __name__ == "__main__":
    main()
