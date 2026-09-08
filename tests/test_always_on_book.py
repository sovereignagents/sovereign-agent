"""Draft construction cannot be confused with a complete sixteen-chapter book."""

import copy
import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_always_on_v1 import verify  # noqa: E402


def test_new_edition_contract_refuses_unwritten_or_missing_chapters(tmp_path):
    manifest = json.loads((ROOT / "book/always_on/BOOK.json").read_text())
    manifest["chapters"][1]["status"] = "PLANNED"
    (tmp_path / "BOOK.json").write_text(json.dumps(manifest))
    errors = verify(tmp_path, complete=True)
    assert errors
    assert any("missing" in error for error in errors)
    assert any("planned" in error for error in errors)


def test_first_call_parser_checks_shape_without_claiming_semantic_truth():
    spec = importlib.util.spec_from_file_location(
        "chapter_one", ROOT / "book/always_on/checkpoints/ch01.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for document in (None, [], {}, {"choices": []}, {"choices": [None]}):
        with pytest.raises(ValueError):
            module.read_brief(document)
    fabricated = copy.deepcopy(module.OFFLINE_RESPONSE)
    fabricated["choices"][0]["message"]["content"] = "I placed the supplier order."
    # Its success proves exactly why envelope validity is not business acceptance.
    assert module.read_brief(fabricated) == "I placed the supplier order."
    incomplete = copy.deepcopy(module.OFFLINE_RESPONSE)
    incomplete["choices"][0]["finish_reason"] = "length"
    with pytest.raises(ValueError):
        module.read_brief(incomplete)


def test_opening_checkpoint_rejects_completion_without_required_draft_evidence():
    checkpoint = runpy.run_path(str(ROOT / "book/always_on/checkpoints/ch03.py"))
    dispatcher = checkpoint["SHOP_TOOLS"]["build_tools"](checkpoint["SHOP_TOOLS"]["SHOP"])
    result = checkpoint["run_loop"](
        checkpoint["ReplayModel"](checkpoint["opening_turns"]()),
        dispatcher,
        checkpoint["MESSAGES"],
    )
    assert checkpoint["draft_evidence"](result) is True
    # Preserve correct stock and fluent final prose, but omit actual draft calls.
    turns = checkpoint["opening_turns"]()
    missing = checkpoint["run_loop"](
        checkpoint["ReplayModel"]([turns[0], turns[-1]]),
        dispatcher,
        checkpoint["MESSAGES"],
    )
    assert missing.status == "COMPLETED"
    assert checkpoint["draft_evidence"](missing) is False
    # The second product matters too: a correct vanilla draft alone cannot pass.
    damaged = copy.deepcopy(result)
    for message in damaged.messages:
        if message.get("tool_call_id") == "draft-s":
            observation = json.loads(message["content"])
            observation["value"]["quantity"] = 5
            message["content"] = json.dumps(observation)
    assert checkpoint["draft_evidence"](damaged) is False
