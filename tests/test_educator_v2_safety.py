"""Real loopback redirect probes for the corrected portable classroom helpers."""

import contextlib
import copy
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

EDUCATOR = Path(__file__).resolve().parents[1] / "book/always_on/educator"


@pytest.fixture(
    params=["ch01-first-model-call-class-v2.ipynb", "ch01-prompts-and-harness-class-v2.ipynb"]
)
def lesson(request):
    scope = {}
    with contextlib.redirect_stdout(io.StringIO()):
        for cell in json.loads((EDUCATOR / request.param).read_text())["cells"]:
            if cell["cell_type"] == "code":
                exec(compile("".join(cell["source"]), request.param, "exec"), scope)
    return scope


@contextlib.contextmanager
def server(handler):
    http = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}"
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_never_contacts_the_second_origin(lesson, status):
    arrivals = []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            arrivals.append((self.command, self.headers.get("Authorization")))
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            self.do_GET()

        def log_message(self, *args):
            pass

    with server(Destination) as destination:

        class Origin(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                assert self.headers.get("Authorization") == "Bearer SYNTHETIC_CLASS_KEY"
                self.send_response(status)
                self.send_header("Location", destination + "/private-target")
                self.end_headers()

            def log_message(self, *args):
                pass

        with server(Origin) as origin:
            with pytest.raises(RuntimeError) as error:
                lesson["live_call"]({}, base=origin, key="SYNTHETIC_CLASS_KEY", timeout=2)
            assert "SYNTHETIC_CLASS_KEY" not in str(error.value)
            assert "private-target" not in str(error.value)
    assert arrivals == []


def test_direct_request_still_succeeds(lesson):
    class Direct(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Length", "16")
            self.end_headers()
            self.wfile.write(b'{"direct": true}')

        def log_message(self, *args):
            pass

    with server(Direct) as origin:
        assert lesson["live_call"]({}, base=origin, timeout=2) == {"direct": True}


@pytest.mark.parametrize("role", [None, "user", "tool", "missing"])
def test_only_assistant_completion_role_is_admitted(lesson, role):
    document = {
        "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "brief"}}]
    }
    assert lesson["read_brief"](document) == "brief"
    bad = copy.deepcopy(document)
    if role == "missing":
        del bad["choices"][0]["message"]["role"]
    else:
        bad["choices"][0]["message"]["role"] = role
    with pytest.raises(ValueError, match="assistant"):
        lesson["read_brief"](bad)
