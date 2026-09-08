"""The distributed follow-on notebook keeps enforcement outside model prose."""

import ast
import contextlib
import copy
import io
import json
import socket
from pathlib import Path

import pytest

NOTEBOOK = Path(__file__).resolve().parents[1] / (
    "book/always_on/educator/ch01-prompts-and-harness-class-v1.ipynb"
)


@pytest.fixture
def lesson(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Offline lesson attempted network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setenv("CLASS_API_KEY", "synthetic-notebook-secret")
    scope = {}
    for _ in range(2):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            for cell in json.loads(NOTEBOOK.read_text())["cells"]:
                if cell["cell_type"] == "code":
                    source = "".join(cell["source"])
                    ast.parse(source, feature_version=(3, 11))
                    exec(compile(source, str(NOTEBOOK), "exec"), scope)
        assert "synthetic-notebook-secret" not in output.getvalue()
        assert len(scope["SHOP"]["products"]) == 3
        assert scope["answer"]["estimated_total_pence"] == 3400
        assert len(scope["rows"]) == 6
        assert all(row["mode"] == "authored_fixture" for row in scope["rows"])
    return scope


def test_prompt_comparison_changes_instruction_location_with_fixed_data(lesson):
    system = lesson["make_messages"]("grounded_system", lesson["SHOP"])
    user = lesson["make_messages"]("grounded_user", lesson["SHOP"])
    assert [m["role"] for m in user] == ["system", "user"]
    rule = lesson["GROUNDING_RULE"]
    assert rule in system[0]["content"] and rule not in user[0]["content"]
    assert rule in user[1]["content"]
    assert system[1]["content"] == user[1]["content"].split("\n", 1)[1]


@pytest.mark.parametrize("enabled", [False, True])
def test_opt_in_and_fixed_generation_settings(lesson, enabled):
    calls = []

    def transport(body, **kwargs):
        calls.append(body)
        return lesson["envelope"](lesson["GOOD"])

    rows, count = lesson["compare_prompts"](
        run_live=enabled,
        base="https://example.invalid",
        model="fixture",
        key="secret",
        transport=transport,
    )
    assert len(calls) == (6 if enabled else 0)
    assert count == 6
    assert all(row["mode"] == ("live_attempt" if enabled else "authored_fixture") for row in rows)
    assert all(
        (p["model"], p["temperature"], p["max_tokens"], p["stream"]) == ("fixture", 0, 384, False)
        for p in calls
    )


def test_failed_live_attempts_are_not_replaced_by_successful_fixtures(lesson):
    def failed(*args, **kwargs):
        raise RuntimeError("private-endpoint-secret")

    rows, count = lesson["compare_prompts"](
        run_live=True,
        base="https://example.invalid",
        model="fixture",
        transport=failed,
    )
    assert count == 6
    assert all(
        row["mode"] == "live_attempt" and row["outcome"] == "FAILED_OR_REFUSED" for row in rows
    )
    assert "private-endpoint-secret" not in json.dumps(rows)


def test_independent_quantities_boolean_and_duplicate_rejections(lesson):
    good = copy.deepcopy(lesson["GOOD"])
    for quantity in (True, 0, 5, 7):
        bad = copy.deepcopy(good)
        bad["drafts"][0]["quantity"] = quantity
        with pytest.raises(lesson["RefusedError"]):
            lesson["validate_draft"](bad, lesson["SHOP"], lesson["PRICES"], **lesson["POLICY"])
    bad = copy.deepcopy(good)
    bad["drafts"].append(copy.deepcopy(bad["drafts"][0]))
    with pytest.raises(lesson["RefusedError"]):
        lesson["validate_draft"](bad, lesson["SHOP"], lesson["PRICES"], **lesson["POLICY"])


def test_capability_removed_and_empty_catalog(lesson):
    closed = {**lesson["POLICY"], "allowed_actions": frozenset()}
    with pytest.raises(lesson["RefusedError"]):
        lesson["validate_draft"](lesson["GOOD"], lesson["SHOP"], lesson["PRICES"], **closed)
    result = lesson["validate_draft"](
        {"action": "draft_order", "drafts": [], "explanation": ""},
        {"products": []},
        {},
        **lesson["POLICY"],
    )
    assert result["estimated_total_pence"] == result["purchases"] == 0
