"""Atomic filesystem helpers used throughout sovereign-agent.

The spine of Decision 1, 3, and 9 is that writes to the session directory
are atomic: readers see either the old version or the new version, never a
torn one. These helpers centralize the temp-file-then-rename and O_APPEND
patterns so every call site uses them consistently.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

from sovereign_agent.errors import IOError as SovereignIOError


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace `path` with `data`.

    Writes to a temp file in the same directory (so the final rename is
    guaranteed to be on the same filesystem), fsync's it, then uses
    Path.replace() which is an atomic rename on POSIX.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Use NamedTemporaryFile with delete=False so we can rename it ourselves.
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(path)
    except Exception as exc:
        # Clean up temp file on any failure.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise SovereignIOError(
            code="SA_IO_ATOMIC_WRITE_FAILED",
            message=f"atomic write to {path} failed: {exc}",
            context={"path": str(path)},
            cause=exc,
        ) from exc


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Atomically write text to `path`."""
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, obj: Any, *, indent: int | None = 2) -> None:
    """Atomically write `obj` as JSON to `path`."""
    data = json.dumps(obj, indent=indent, default=_json_default, sort_keys=False)
    atomic_write_text(path, data)


def atomic_append_jsonl(path: Path, obj: Any) -> None:
    """Append one JSON object plus newline to a JSONL file.

    POSIX guarantees that writes to a file opened with O_APPEND are atomic
    up to PIPE_BUF (typically 4KB) and that the offset update is atomic
    under concurrent appenders. Our trace events are small JSON objects,
    well under that limit, so this is safe for concurrent writers.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, default=_json_default, sort_keys=False) + "\n"
    data = line.encode("utf-8")
    if len(data) > 4096:
        # PIPE_BUF is typically 4096 on Linux. If someone writes a
        # whopper of a trace event, we'd rather they know than silently
        # risk a torn write.
        raise SovereignIOError(
            code="SA_IO_ATOMIC_WRITE_FAILED",
            message=(
                f"trace event is {len(data)} bytes, exceeds atomic-append limit "
                "(4096 bytes). Trim the event payload or split it across "
                "multiple events."
            ),
            context={"path": str(path), "size_bytes": len(data)},
        )
    # O_APPEND semantics: each write call appends atomically.
    with open(path, "ab") as f:
        f.write(data)


def _json_default(obj: Any) -> Any:
    """JSON encoder fallback for datetimes, Paths, and dataclasses.

    We don't require callers to pre-serialize — the trace writer and
    session.json writer both benefit from "just put the object in."
    """
    from dataclasses import asdict, is_dataclass
    from datetime import datetime
    from enum import Enum

    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"object of type {type(obj).__name__} is not JSON serializable")


def compute_sha256(path: Path) -> str:
    """Compute the sha256 of a file, returned as lowercase hex."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def new_ipc_filename() -> str:
    """Generate an IPC message filename: <millis>-<4hex>.json.

    The millis prefix sorts chronologically; the hex suffix avoids
    collisions when two writes happen in the same millisecond.
    """
    return f"{int(time.time() * 1000)}-{secrets.token_hex(2)}.json"


__all__ = [
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_json",
    "atomic_append_jsonl",
    "compute_sha256",
    "new_ipc_filename",
]
