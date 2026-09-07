"""Draft construction cannot be confused with a complete sixteen-chapter book."""

import copy
import importlib.util
import json
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
