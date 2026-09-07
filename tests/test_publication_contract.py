"""Refuse a superficially complete edition that loses paths or overclaims readiness."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("failure", ["duplicate", "missing", "escape", "ready", "figures"])
def test_publication_contract_refuses_invalid_edition(tmp_path: Path, failure: str) -> None:
    spec = importlib.util.spec_from_file_location(
        "publication", ROOT / "scripts" / "verify_publication_v1.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = ROOT / "book" / "always_on"
    book = tmp_path / "book"
    shutil.copytree(source, book)
    module.verify(book)
    path = book / "PUBLICATION.json"
    manifest = json.loads(path.read_text())
    if failure == "duplicate":
        manifest["parts"][0]["chapters"][-1] = 2
    elif failure == "missing":
        (book / manifest["frontMatter"][0]["path"]).unlink()
    elif failure == "escape":
        manifest["frontMatter"][0]["path"] = "../book/PREFACE.md"
    elif failure == "ready":
        manifest["status"] = "READY"
    else:
        manifest["expectedFigures"] = 51
    path.write_text(json.dumps(manifest))
    with pytest.raises(AssertionError):
        module.verify(book)
