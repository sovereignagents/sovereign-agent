"""Validate the source-owned book, part, front-matter, and resource manifest.

PROVES: BOOK.json names one existing path per surface and partitions chapters 0-12 once.
PAID-FAILURE: front matter and appendices existed upstream but were invisible to consumers.
proven-at: profrodai/sovereign-agent@ab7028465d4eccf2809b24c238de8578ab96c498
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "book"
MANIFEST = BOOK / "BOOK.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"verify_book_structure_v1: {message}")


def records(value: Any, field: str) -> list[dict[str, Any]]:
    require(isinstance(value, list), f"{field} must be a list")
    require(all(isinstance(item, dict) for item in value), f"{field} entries must be objects")
    return value


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    require(data.get("schemaVersion") == 1, "schemaVersion must be 1")
    require(data.get("title") == "Building Zero Employee Organizations", "title drifted")
    require(data.get("author", {}).get("name") == "Rod Rivera", "author is missing")

    surfaces: list[tuple[str, dict[str, Any]]] = []
    for field in ("frontMatter", "parts", "appendices", "resources"):
        surfaces.extend((field, item) for item in records(data.get(field), field))

    slugs: set[str] = set()
    paths: set[str] = set()
    for field, item in surfaces:
        slug = item.get("slug")
        relative = item.get("path")
        require(isinstance(slug, str) and slug, f"{field} entry has no slug")
        require(isinstance(relative, str) and relative, f"{field}/{slug} has no path")
        require(slug not in slugs, f"duplicate surface slug {slug}")
        require(relative not in paths, f"duplicate surface path {relative}")
        slugs.add(slug)
        paths.add(relative)
        target = BOOK / relative
        require(target.is_file(), f"{field}/{slug} path does not exist: {relative}")
        require(target.read_text(encoding="utf-8").startswith("# "), f"{relative} needs one H1")

    part_chapters = [
        chapter
        for part in records(data.get("parts"), "parts")
        for chapter in part.get("chapters", [])
    ]
    require(part_chapters == list(range(13)), "parts must partition chapters 0 through 12 in order")

    source_chapters = sorted(
        int(path.parent.name[2:4]) for path in BOOK.glob("ch[0-9][0-9]_*/README.md")
    )
    require(source_chapters == list(range(13)), "source chapter directories must be 0 through 12")

    captions: list[str] = []
    listing_titles: list[str] = []
    diagram_count = 0
    for chapter_path in sorted(BOOK.glob("ch[0-9][0-9]_*/README.md")):
        chapter = chapter_path.read_text(encoding="utf-8")
        diagrams = re.findall(
            r"^```mermaid\n.*?^```\n\n\*\*Figure:\*\* ([^\n]+)$",
            chapter,
            flags=re.MULTILINE | re.DOTALL,
        )
        raw_count = len(re.findall(r"^```mermaid$", chapter, flags=re.MULTILINE))
        require(
            len(diagrams) == raw_count,
            f"{chapter_path.relative_to(ROOT)} has {raw_count} diagrams but "
            f"{len(diagrams)} immediate captions",
        )
        require(
            all(len(caption) >= 60 for caption in diagrams),
            f"{chapter_path.relative_to(ROOT)} has a caption shorter than 60 characters",
        )
        captions.extend(diagrams)
        diagram_count += raw_count

        listings = re.findall(
            r"^\*\*Listing:\*\* ([^\n]+)\n\n```(?:python|bash)\n",
            chapter,
            flags=re.MULTILINE,
        )
        require(
            len(listings) >= 1,
            f"{chapter_path.relative_to(ROOT)} needs an authored key-listing title",
        )
        listing_titles.extend(listings)

    require(diagram_count == 39, f"expected 39 diagrams, found {diagram_count}")
    require(len(set(captions)) == len(captions), "figure captions must be unique")
    require(
        len(set(listing_titles)) == len(listing_titles),
        "key-listing titles must be unique",
    )

    print(
        "verify_book_structure_v1: "
        f"{len(surfaces)} surfaces, {len(source_chapters)} chapters, "
        f"{diagram_count} captions, and {len(listing_titles)} key listings are coherent"
    )


if __name__ == "__main__":
    main()
