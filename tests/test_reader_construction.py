"""Cold-start build: only the printed definitions, Pydantic and Python are available."""

import ast
import builtins
import contextlib
import io
import json
import re
import runpy
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def saved_definitions(chapter, assignments):
    """Apply the exact save instructions printed in Chapters 2 and 3."""
    text = (ROOT / f"book/always_on/{chapter}/README.md").read_text()
    nodes = []
    for code in re.findall(r"^```python\n(.*?)^```", text, re.M | re.S):
        for node in ast.parse(code).body:
            if isinstance(node, ast.FunctionDef) and node.name in {"authored_http", "refuse_write"}:
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)) or (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id in assignments for t in node.targets)
            ):
                nodes.append(node)
    return ast.unparse(ast.Module(body=nodes, type_ignores=[]))


@pytest.fixture
def reader(tmp_path, monkeypatch):
    learner = tmp_path / "book/always_on/learner"
    learner.mkdir(parents=True)
    checkpoints = learner.parent / "checkpoints"
    checkpoints.mkdir()
    shutil.copy(ROOT / "book/always_on/checkpoints/ch01.py", checkpoints / "ch01.py")
    shutil.copy(ROOT / "book/always_on/checkpoints/ch03.py", checkpoints / "ch03.py")
    for number, chapter, assignments in (
        (2, "ch02_shop_tools", {"SHOP", "PRICES", "products", "tools"}),
        (3, "ch03_agent_loop", {"shop_tools", "ToolCall", "first", "messages"}),
    ):
        (learner / f"ch{number:02}.py").write_text(saved_definitions(chapter, assignments))
    monkeypatch.chdir(tmp_path)
    original_import = builtins.__import__

    def no_runtime(name, *args, **kwargs):
        if name.startswith(("sovereign_agent", "reference_organizations")):
            raise AssertionError("reader logic imported the installed runtime: " + name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_runtime)
    return runpy.run_path(str(learner / "ch03.py")), learner


def test_printed_definitions_alone_construct_grounded_drafts(reader):
    code, _ = reader
    result = code["run_loop"](
        code["ReplayModel"](code["opening_turns"]()),
        code["shop_tools"]["build_tools"](code["shop_tools"]["SHOP"]),
        code["messages"],
    )
    assert (result.status, result.model_calls, result.tool_calls) == ("COMPLETED", 3, 3)
    assert code["draft_evidence"](result)


@pytest.mark.parametrize("failure", [None, "arguments", "length", "shape"])
def test_reader_http_parser_and_reader_loop_form_one_path(reader, failure):
    code, _ = reader
    envelopes = []
    for turn in code["opening_turns"]():
        envelopes.append(
            {
                "choices": [
                    {
                        "message": turn.message(),
                        "finish_reason": "tool_calls" if turn.calls else "stop",
                    }
                ],
                "usage": {"completion_tokens": 12},
            }
        )
    if failure == "arguments":
        envelopes[0]["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "not JSON"
    elif failure == "length":
        envelopes[0]["choices"][0]["finish_reason"] = "length"
    elif failure == "shape":
        envelopes[0]["choices"][0]["message"] = []
    responses = iter(envelopes)
    payloads = []

    def transport(url, *, data, headers, timeout):
        payloads.append(json.loads(data))
        return SimpleNamespace(status=200, body=json.dumps(next(responses)).encode())

    result = code["run_loop"](
        code["HTTPModel"](request=transport),
        code["shop_tools"]["build_tools"](code["shop_tools"]["SHOP"]),
        code["messages"],
    )
    if failure:
        assert (result.status, result.tool_calls) == ("MODEL_FAILED", 0)
    else:
        assert result.status == "COMPLETED" and code["draft_evidence"](result)
        assert len(payloads[-1]["messages"]) == 7
    assert len(payloads[0]["tools"]) == 3


def test_checkpoint_observes_a_deliberate_reader_loop_edit(reader, monkeypatch):
    _, learner = reader
    path = learner / "ch03.py"
    text = path.read_text()
    assert text.count("'COMPLETED'") == 1
    path.write_text(text.replace("'COMPLETED'", "'READER_EDIT'"))
    monkeypatch.setattr(sys, "argv", ["ch03.py"])
    checkpoint = runpy.run_path(str(learner.parent / "checkpoints/ch03.py"))
    with contextlib.redirect_stdout(io.StringIO()) as output:
        assert checkpoint["main"]() == 1
    assert "READER_EDIT 3 3" in output.getvalue()


def test_checked_in_reader_definitions_match_printed_construction():
    for number, chapter, assignments in (
        (2, "ch02_shop_tools", {"SHOP", "PRICES", "products", "tools"}),
        (3, "ch03_agent_loop", {"shop_tools", "ToolCall", "first", "messages"}),
    ):
        printed = ast.parse(saved_definitions(chapter, assignments))
        checked_in = ast.parse((ROOT / f"book/always_on/learner/ch{number:02}.py").read_text())

        def definitions(tree):
            return {
                n.name: ast.dump(n, include_attributes=False)
                for n in tree.body
                if isinstance(n, (ast.ClassDef, ast.FunctionDef))
            }

        assert definitions(checked_in) == definitions(printed)
