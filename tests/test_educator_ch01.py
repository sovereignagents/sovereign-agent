"""Chapter 1 classroom evidence: replay, counterexamples and explicit live fallback."""

import ast
import contextlib
import copy
import io
import json
import runpy
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

BOOK = Path(__file__).resolve().parents[1] / "book/always_on"
NOTEBOOK = BOOK / "educator/ch01-first-model-call-class-v1.ipynb"


def cells():
    return [
        "".join(cell["source"])
        for cell in json.loads(NOTEBOOK.read_text())["cells"]
        if cell["cell_type"] == "code"
    ]


@pytest.fixture
def lesson(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Offline lesson attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setenv("CLASS_API_KEY", "synthetic-private-key")
    scope = {}
    for _ in range(2):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            for source in cells():
                ast.parse(source, feature_version=(3, 11))
                exec(compile(source, str(NOTEBOOK), "exec"), scope)
        assert "synthetic-private-key" not in output.getvalue()
        assert len(scope["SHOP"]["products"]) == 3
        assert len(scope["expanded_shop"]["products"]) == 4
        assert scope["trial"]["mode"] == "fixture"
    return scope


def test_offline_replay_and_business_counterexamples(lesson):
    assert lesson["check_brief"](lesson["MISSED_LIE"], lesson["SHOP"]) == []
    assert lesson["stock_facts"](lesson["SHOP"])[-1] == ("SKU-VANILLA", 2, 6)
    assert lesson["check_brief"](lesson["NEGATED_ACTION"], lesson["SHOP"])
    assert (
        lesson["review_brief"](
            lesson["build"](lesson["SHOP"]), lesson["OFFLINE_RESPONSE"], lesson["SHOP"]
        )["status"]
        == "NEEDS_FACTUAL_REVIEW"
    )


@pytest.mark.parametrize("document", [None, [], {}, {"choices": [17]}, {"choices": [None]}])
def test_malformed_envelopes_have_a_bounded_rejection(lesson, document):
    with pytest.raises(ValueError):
        lesson["read_brief"](document)


def test_chocolate_snapshot_and_content_hash_limit(lesson):
    shop = copy.deepcopy(lesson["SHOP"])
    built = lesson["build"](shop)
    shop["products"][1]["on_hand"] = 5
    with pytest.raises(ValueError, match="shop changed"):
        lesson["review_brief"](built, lesson["OFFLINE_RESPONSE"], shop)
    shop["products"][1]["on_hand"] = 12
    assert lesson["snapshot_id"](shop) == built["snapshot"]  # content hash cannot detect ABA


def test_live_success_and_offline_opt_in_are_distinct(lesson):
    calls = []

    def transport(*args, **kwargs):
        calls.append(args)
        return lesson["OFFLINE_RESPONSE"]

    trial = lesson["run_trial"](
        enabled=False,
        base="https://example.invalid/v1",
        model="fixture",
        key="secret",
        call=transport,
    )
    assert trial["mode"] == "fixture" and calls == []
    trial = lesson["run_trial"](
        enabled=True, base="https://example.invalid/v1", model="fixture", call=transport
    )
    assert trial["mode"] == "live" and len(calls) == 1  # authored transport, not a provider run


@pytest.mark.parametrize("failure", ["http", "connection", "bytes", "truncated"])
def test_live_failure_is_sanitized_and_explicitly_falls_back(lesson, failure):
    def transport(*args, **kwargs):
        if failure == "truncated":
            return {"choices": [{"finish_reason": "length"}]}
        error = OSError if failure == "connection" else RuntimeError
        raise error("private-endpoint-secret")

    with contextlib.redirect_stdout(io.StringIO()) as output:
        trial = lesson["run_trial"](
            enabled=True, base="https://example.invalid/v1", model="fixture", call=transport
        )
    assert trial["mode"] == "fixture"
    assert "LIVE ATTEMPT FAILED" in output.getvalue()
    assert "OFFLINE RESPONSE FIXTURE" in output.getvalue()
    assert "private-endpoint-secret" not in output.getvalue()


@pytest.mark.parametrize("failure", ["http", "connection", "oversize"])
def test_transport_withholds_errors_and_enforces_byte_ceiling(lesson, failure):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, amount):
            assert amount == 17
            return b"x" * amount

    def urlopen(*args, **kwargs):
        assert kwargs["timeout"] == 30
        if failure == "http":
            raise HTTPError("https://private.invalid/secret", 429, "secret", {}, None)
        if failure == "connection":
            raise URLError("private-endpoint-secret")
        return Response()

    lesson["urlopen"] = urlopen
    with pytest.raises((RuntimeError, ValueError)) as error:
        lesson["live_call"]({}, base="https://example.invalid/v1", max_bytes=16)
    assert "private" not in str(error.value) and "secret" not in str(error.value)


def test_notebook_parser_matches_chapter_checkpoint():
    namespace = runpy.run_path(str(BOOK / "checkpoints/ch01.py"))
    assert (
        namespace["read_brief"](
            {"choices": [{"finish_reason": "stop", "message": {"content": "x"}}]}
        )
        == "x"
    )
    definitions = {}
    for source in cells():
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef):
                definitions[node.name] = ast.dump(node, include_attributes=False)
    checkpoint = ast.parse((BOOK / "checkpoints/ch01.py").read_text())
    for name in (
        "read_brief",
        "stock_facts",
        "check_brief",
        "snapshot_id",
        "build",
        "review_brief",
    ):
        function = next(
            n for n in checkpoint.body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        assert definitions[name] == ast.dump(function, include_attributes=False)
