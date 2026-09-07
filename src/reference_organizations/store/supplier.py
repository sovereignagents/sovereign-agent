"""Independent supplier process and database for lost-response experiments.

Only loopback HTTP is supported. This deliberately cannot purchase real stock.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sqlite3
import time
import uuid
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

    def __init__(
        self, endpoint: str, *, timeout: float = 3, account: str = "", epoch: int = 0
    ) -> None:
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
        self._endpoint, self._timeout = endpoint.rstrip("/"), timeout
        if (
            (account and not re.fullmatch("[a-f0-9]{32}", account))
            or type(epoch) is not int
            or epoch < 0
        ):
            raise ValueError("invalid supplier account binding")
        self.account, self.epoch = account, epoch

    def account_call(
        self,
        path: str = "/account",
        *,
        data: dict[str, Any] | None = None,
        epoch: int | None = None,
    ) -> dict[str, Any]:
        if path not in {"/account", "/account/fence", "/account/snapshot"}:
            raise ValueError("invalid account operation")
        response = request(
            self.endpoint + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Sovereign-Account": self.account,
                "X-Sovereign-Epoch": str(self.epoch if epoch is None else epoch),
            },
            timeout=self.timeout,
            maximum_bytes=1_048_576,
        )
        if response.status != 200:
            raise OSError("supplier account discovery or fencing failed")
        result = json.loads(response.body)
        if not isinstance(result, dict):
            raise ValueError("invalid supplier account response")
        return result

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def identity(self) -> str:
        return "lucy-local@" + self._endpoint

    def _call(
        self, operation: str, proposal: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        if not re.fullmatch("[a-f0-9]{32}", operation):
            raise ValueError("invalid operation identity")
        response = request(
            self.endpoint + "/orders/" + operation,
            data=None if proposal is None else json.dumps(proposal).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Sovereign-Account": self.account,
                "X-Sovereign-Epoch": str(self.epoch),
            },
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
    path: Path,
    port: int,
    *,
    drop_first_response: bool = False,
    ready: Path | None = None,
    hold_response_seconds: float = 0,
    committed: Path | None = None,
    reject: bool = False,
) -> None:
    if not 0 <= hold_response_seconds <= 10:
        raise ValueError("supplier experiment delay must be between zero and ten seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS orders(operation TEXT PRIMARY KEY,"
        "proposal TEXT NOT NULL,receipt TEXT NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS account(id INTEGER PRIMARY KEY CHECK(id=1),"
        "identity TEXT NOT NULL,epoch INTEGER NOT NULL)"
    )
    connection.execute("INSERT OR IGNORE INTO account VALUES (1,?,0)", (uuid.uuid4().hex,))
    connection.execute(
        "CREATE TABLE IF NOT EXISTS rotations(id TEXT PRIMARY KEY,epoch INTEGER NOT NULL)"
    )
    connection.commit()

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format: str, *args: Any) -> None:
            pass  # No request or credentials in a teaching service log.

        def reply(self, code: int, data: dict[str, Any]) -> None:
            raw = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except BrokenPipeError, ConnectionResetError:
                pass  # A bounded client may already have stopped waiting.

        def operation(self) -> str | None:
            match = re.fullmatch(r"/orders/([a-f0-9]{32})", self.path)
            return match[1] if match else None

        def account(self) -> dict[str, Any]:
            row = connection.execute("SELECT identity,epoch FROM account WHERE id=1").fetchone()
            return {"account": row[0], "epoch": row[1]}

        def current_account(self, *, legacy: bool = False) -> bool:
            state = self.account()
            identity = self.headers.get("X-Sovereign-Account", "")
            epoch = self.headers.get("X-Sovereign-Epoch", "0")
            return epoch == str(state["epoch"]) and (
                identity == state["account"] or (legacy and not identity and state["epoch"] == 0)
            )

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/account":
                self.reply(200, self.account())
                return
            if self.path == "/account/snapshot":
                if not self.current_account():
                    self.reply(409, {"error": "account_fence_changed"})
                    return
                rows = connection.execute(
                    "SELECT receipt FROM orders ORDER BY operation LIMIT 1001"
                ).fetchall()
                if len(rows) > 1000:
                    self.reply(409, {"error": "account_export_too_large"})
                    return
                self.reply(
                    200,
                    {
                        **self.account(),
                        "complete": True,
                        "receipts": [json.loads(row[0]) for row in rows],
                    },
                )
                return
            operation = self.operation()
            identity = self.headers.get("X-Sovereign-Account", "")
            state = self.account()
            if identity != state["account"] and (identity or state["epoch"] != 0):
                self.reply(409, {"error": "account_identity_changed"})
                return
            row = connection.execute(
                "SELECT receipt FROM orders WHERE operation=?", (operation,)
            ).fetchone()
            self.reply(200, json.loads(row[0])) if row else self.reply(404, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/account/fence":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= 4096:
                        raise ValueError("bounded rotation required")
                    body = json.loads(self.rfile.read(length))
                    if (
                        not isinstance(body, dict)
                        or set(body) != {"account", "rotation"}
                        or body["account"] != self.account()["account"]
                        or not isinstance(body["rotation"], str)
                        or not re.fullmatch("[a-f0-9]{32}", body["rotation"])
                    ):
                        raise ValueError("invalid rotation")
                    with connection:
                        prior = connection.execute(
                            "SELECT epoch FROM rotations WHERE id=?", (body["rotation"],)
                        ).fetchone()
                        if prior is None:
                            connection.execute("UPDATE account SET epoch=epoch+1 WHERE id=1")
                            epoch = self.account()["epoch"]
                            connection.execute(
                                "INSERT INTO rotations VALUES (?,?)", (body["rotation"], epoch)
                            )
                        else:
                            epoch = prior[0]
                    self.reply(200, {"account": body["account"], "epoch": epoch})
                except ValueError:
                    self.reply(400, {"error": "invalid_rotation"})
                return
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
            if not self.current_account(legacy=True):
                self.reply(409, {"error": "account_fence_changed"})
                return
            row = connection.execute(
                "SELECT proposal,receipt FROM orders WHERE operation=?", (operation,)
            ).fetchone()
            if row:
                self.reply(200, json.loads(row[1])) if row[0] == encoded else self.reply(
                    409, {"error": "identity_conflict"}
                )
                return
            receipt = {
                "operation": operation,
                "proposal": proposal,
                "status": "REJECTED" if reject else "ACCEPTED",
            }
            with connection:
                connection.execute(
                    "INSERT INTO orders VALUES (?,?,?)", (operation, encoded, json.dumps(receipt))
                )
            if committed:
                committed.write_text(operation)
            time.sleep(hold_response_seconds)
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
    parser.add_argument("--hold-response-seconds", type=float, default=0)
    parser.add_argument("--committed", type=Path)
    parser.add_argument("--reject", action="store_true")
    args = parser.parse_args()
    serve(
        args.database,
        args.port,
        drop_first_response=args.drop_first_response,
        ready=args.ready,
        hold_response_seconds=args.hold_response_seconds,
        committed=args.committed,
        reject=args.reject,
    )


if __name__ == "__main__":
    main()
