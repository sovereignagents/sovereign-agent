#!/usr/bin/env python3
"""Check the source-owned sixteen-chapter publication contract, not editorial quality."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def verify(book: Path) -> None:
    index = json.loads((book / "BOOK.json").read_text())
    manifest = json.loads((book / "PUBLICATION.json").read_text())
    assert manifest["schemaVersion"] == 1 and manifest["edition"] == "always-on-2026"
    assert manifest["status"] in {"DRAFT", "READY"}
    assert manifest["title"] == index["title"] and manifest["subtitle"] == index["subtitle"]
    assert [p["number"] for p in manifest["parts"]] == [1, 2, 3, 4]
    assert [n for p in manifest["parts"] for n in p["chapters"]] == list(range(1, 17))
    assert [c["number"] for c in index["chapters"]] == list(range(1, 17))
    if manifest["status"] == "READY":
        assert all(c["status"] == "READY" for c in index["chapters"])
    surfaces = [
        item
        for kind in ("frontMatter", "parts", "appendices", "resources")
        for item in manifest[kind]
    ]
    paths: set[str] = set()
    slugs: set[str] = set()
    for item in [*index["chapters"], *surfaces]:
        relative = item["path"]
        assert re.fullmatch(r"[A-Za-z0-9_./-]+", relative)
        assert not relative.startswith("/") and not {"", ".", ".."} & set(relative.split("/"))
        source = book / relative
        assert source.is_file() and not source.is_symlink(), relative
        assert source.resolve().is_relative_to(book.resolve()), relative
        assert relative not in paths, relative
        paths.add(relative)
        slug = item.get("slug", relative.split("/")[0].replace("_", "-"))
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) and slug not in slugs, slug
        slugs.add(slug)
        assert re.search(r"^# .+", source.read_text(), re.M), relative
    text = "\n".join((book / c["path"]).read_text() for c in index["chapters"])
    assert text.count("**Figure:**") == manifest["expectedFigures"] == 52
    assert text.count("**Listing:**") == manifest["expectedListings"] == 97


if __name__ == "__main__":
    verify(ROOT / "book" / "always_on")
    print("PUBLICATION CONTRACT: 16 chapters, 4 parts, declared surfaces and furniture checked.")
    print("DRAFT remains draft; this is not editorial acceptance.")
