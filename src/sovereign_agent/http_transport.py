"""A killable HTTP request: parent deadline includes DNS, headers and body reads.

The short-lived child uses only stdlib HTTP. Credentials cross stdin, never
argv, logs or a persisted request file. Killing the client cannot cancel a bill
or external effect already accepted by a remote service.
"""

from __future__ import annotations

import base64
import json
import math
import os
import signal
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise OSError("redirect refused")


@dataclass(frozen=True)
class HTTPResult:
    status: int
    body: bytes


def request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
    maximum_bytes: int = 262_144,
) -> HTTPResult:
    if not math.isfinite(timeout) or not 0 < timeout <= 120 or not 1 <= maximum_bytes <= 1_048_576:
        raise ValueError("bounded HTTP deadline and response required")
    payload = json.dumps(
        {
            "url": url,
            "data": None if data is None else base64.b64encode(data).decode(),
            "headers": headers or {},
            "timeout": timeout,
            "maximum": maximum_bytes,
        }
    )
    if len(payload.encode()) > 1_048_576:
        raise ValueError("HTTP request exceeds byte budget")
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in {"PATH", "SYSTEMROOT", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    }
    try:
        child = subprocess.run(
            [sys.executable, "-m", "sovereign_agent.http_transport"],
            input=payload.encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            env=environment,
            check=False,
        )
        if child.returncode:
            raise OSError("HTTP transport failed")
        result = json.loads(child.stdout)
        return HTTPResult(result["status"], base64.b64decode(result["body"], validate=True))
    except subprocess.TimeoutExpired:
        raise TimeoutError("HTTP deadline expired; remote outcome may be unknown") from None
    except ValueError, KeyError:
        raise OSError("invalid HTTP transport result") from None


def _main() -> int:
    try:
        spec = json.loads(sys.stdin.buffer.read(1_048_577))
        if hasattr(signal, "setitimer"):
            # A killed parent cannot enforce its deadline. POSIX children retain
            # their own default-terminating alarm, including during a slow body.
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
            signal.setitimer(signal.ITIMER_REAL, spec["timeout"])
        data = spec["data"]
        outgoing = urllib.request.Request(
            spec["url"],
            data=None if data is None else base64.b64decode(data),
            headers=spec["headers"],
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(
                outgoing, timeout=spec["timeout"]
            ) as response:
                body = response.read(spec["maximum"] + 1)
                if len(body) > spec["maximum"]:
                    return 2
                status = response.status
        except urllib.error.HTTPError as error:
            status, body = error.code, b""
        print(json.dumps({"status": status, "body": base64.b64encode(body).decode()}))
        return 0
    except OSError, ValueError, KeyError, TypeError:
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
