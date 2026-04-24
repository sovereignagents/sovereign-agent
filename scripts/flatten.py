"""Flatten the repo (or a scope) into a single text bundle.

Produces two artifacts under the output directory:

  manifest.md   — human-readable index of what's in the bundle
  flat.txt      — the actual concatenation, with clear file-path headers

Designed to be safe to paste into an LLM chat or attach to an API call.
Respects a skip list (.git, .venv, __pycache__, artifacts) and a size cap.

Usage:

    python scripts/flatten.py --scope . --out-dir _transient/flatten
    python scripts/flatten.py --scope sovereign_agent --out-dir out/ --max-bytes 4000000
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path

DEFAULT_EXTENSIONS = [
    ".py",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".cfg",
    ".ini",
    ".txt",
    ".json",
    ".example",
    ".env",
]
DEFAULT_SKIP_DIRS = [
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".egg-info",
    "node_modules",
    "_transient",
    "_transient-files",
    ".tox",
    ".idea",
    ".vscode",
]


def matches_any(relpath: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relpath, p) for p in patterns)


def should_skip_dir(dirname: str, skip_dirs: list[str]) -> bool:
    return dirname in skip_dirs or dirname.startswith(".") and dirname in skip_dirs


def collect_files(
    scope: Path,
    extensions: list[str],
    skip_dirs: list[str],
    exclude_patterns: list[str],
) -> list[Path]:
    """Walk `scope` and return files matching the extension list."""
    out: list[Path] = []
    exts = {e.lower() for e in extensions}
    for path in sorted(scope.rglob("*")):
        # Filter directories early.
        if any(part in skip_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in exts:
            continue
        rel = path.relative_to(scope).as_posix()
        if matches_any(rel, exclude_patterns):
            continue
        out.append(path)
    return out


def render_manifest(scope: Path, files: list[Path], total_bytes: int) -> str:
    lines = [
        "# Flatten manifest",
        "",
        f"- Scope: `{scope}`",
        f"- Files: {len(files)}",
        f"- Total size: {total_bytes:,} bytes",
        "",
        "## Contents",
        "",
    ]
    for f in files:
        rel = f.relative_to(scope).as_posix()
        size = f.stat().st_size
        lines.append(f"- `{rel}` ({size:,} B)")
    return "\n".join(lines) + "\n"


def render_flat(scope: Path, files: list[Path], max_bytes: int) -> tuple[str, int, list[str]]:
    """Concatenate files with a clear file-path header separator.

    Returns (text, bytes_written, truncated_files).
    """
    parts: list[str] = []
    total = 0
    truncated: list[str] = []
    for f in files:
        rel = f.relative_to(scope).as_posix()
        try:
            body = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            truncated.append(rel)
            continue
        header = f"\n\n===== FILE: {rel} =====\n\n"
        chunk = header + body
        if total + len(chunk) > max_bytes:
            # Truncate the bundle at the cap; note which file we stopped at.
            remaining = max_bytes - total
            if remaining > len(header) + 100:
                parts.append(header + body[: remaining - len(header) - 50] + "\n\n...[TRUNCATED]")
                total += remaining
            truncated.append(rel + " (truncated)")
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts), total, truncated


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", default=".", help="Directory to flatten (default: .)")
    ap.add_argument("--out-dir", required=True, help="Where to write manifest.md and flat.txt")
    ap.add_argument(
        "--extensions",
        default=",".join(DEFAULT_EXTENSIONS),
        help="Comma-separated file extensions to include",
    )
    ap.add_argument(
        "--skip-dirs",
        default=",".join(DEFAULT_SKIP_DIRS),
        help="Comma-separated directory names to skip",
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob pattern to exclude (repeatable)",
    )
    ap.add_argument(
        "--max-bytes",
        type=int,
        default=4_000_000,
        help="Stop writing when flat.txt reaches this many bytes (default: 4 MB)",
    )
    args = ap.parse_args(argv)

    scope = Path(args.scope).resolve()
    out_dir = Path(args.out_dir).resolve()
    if not scope.exists():
        print(f"error: scope does not exist: {scope}", file=sys.stderr)
        return 2

    extensions = [e.strip() for e in args.extensions.split(",") if e.strip()]
    skip_dirs = [d.strip() for d in args.skip_dirs.split(",") if d.strip()]

    files = collect_files(scope, extensions, skip_dirs, args.exclude)
    if not files:
        print("error: no files matched", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    flat_text, total_bytes, truncated = render_flat(scope, files, args.max_bytes)
    (out_dir / "flat.txt").write_text(flat_text, encoding="utf-8")
    (out_dir / "manifest.md").write_text(
        render_manifest(scope, files, total_bytes),
        encoding="utf-8",
    )

    print(f"  bundled {len(files)} files, {total_bytes:,} bytes")
    print(f"  output  {out_dir}/flat.txt")
    print(f"          {out_dir}/manifest.md")
    if truncated:
        print(f"  warning: {len(truncated)} file(s) skipped or truncated")
        for t in truncated[:5]:
            print(f"    - {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
