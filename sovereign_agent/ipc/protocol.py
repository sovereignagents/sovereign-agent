"""Filesystem IPC primitives (Decision 3 + Decision 4).

Inter-process communication in sovereign-agent happens by writing JSON files
to shared directories and having the receiver poll. Writes use the
temp-file-then-rename pattern so readers never see partial writes.

The `_close` sentinel (Decision 4) is how workers are told to shut down
cleanly — no SIGKILL, no signal-handling edge cases.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from sovereign_agent._internal.atomic import atomic_write_json, new_ipc_filename
from sovereign_agent.errors import IOError as SovereignIOError

CLOSE_SENTINEL_NAME = "_close"

# Grace period (ms) before a file is considered safe to read. Anything newer
# than this is skipped on the current poll pass — belt-and-braces on top of
# the atomic rename, which already prevents torn reads.
READ_GRACE_MS = 100


def write_ipc_message(directory: Path, payload: dict) -> Path:
    """Atomically write a JSON message to an IPC directory.

    Filename format is <millis>-<4hex>.json so files sort chronologically
    and never collide.

    Returns the final path.
    """
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / new_ipc_filename()
    atomic_write_json(final, payload)
    return final


def write_close_sentinel(ipc_input_dir: Path) -> Path:
    """Write the `_close` sentinel into the worker's input directory.

    Workers check for this on every poll and exit cleanly when they see it.
    The file content is empty; only its presence matters.
    """
    ipc_input_dir.mkdir(parents=True, exist_ok=True)
    path = ipc_input_dir / CLOSE_SENTINEL_NAME
    # Use atomic rename even for the empty sentinel — this way a worker that
    # polls mid-write never sees a half-created file.
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(b"")
    tmp.replace(path)
    return path


def is_close_sentinel(name_or_path: str | Path) -> bool:
    name = name_or_path.name if isinstance(name_or_path, Path) else name_or_path
    return name == CLOSE_SENTINEL_NAME


def clear_close_sentinel(ipc_input_dir: Path) -> bool:
    """Remove the sentinel if it exists. Returns whether it was present."""
    path = ipc_input_dir / CLOSE_SENTINEL_NAME
    if path.exists():
        path.unlink()
        return True
    return False


def read_and_consume(
    directory: Path,
    *,
    max_age_ms: int = READ_GRACE_MS,
    archive_dir: Path | None = None,
    error_dir: Path | None = None,
) -> list[tuple[Path, dict]]:
    """Read all JSON files in `directory` older than `max_age_ms`.

    Returns a list of (original_path, parsed_payload). After reading, each
    file is MOVED — either to `archive_dir` (on success) or `error_dir` (on
    parse failure). This is the core of per-session-isolated error handling:
    a malformed file in one session does not block processing for any other.

    The `_close` sentinel is never consumed here; callers decide whether to
    honor it separately.

    If `archive_dir` is None, defaults to `directory / "processed"`.
    If `error_dir` is None, defaults to `directory.parent / "errors"`.
    """
    out: list[tuple[Path, dict]] = []
    if not directory.exists():
        return out

    arc = archive_dir or (directory / "processed")
    err = error_dir or (directory.parent / "errors")
    arc.mkdir(parents=True, exist_ok=True)

    now_ms = int(time.time() * 1000)
    for entry in sorted(directory.iterdir()):
        if not entry.is_file():
            continue
        if is_close_sentinel(entry):
            continue
        # Skip files that look in-flight (a sibling .tmp exists) or that
        # are too young.
        if entry.suffix == ".tmp":
            continue
        try:
            age_ms = now_ms - int(entry.stat().st_mtime * 1000)
        except FileNotFoundError:
            # Raced with another consumer; skip.
            continue
        if age_ms < max_age_ms:
            continue

        try:
            with open(entry, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            # Quarantine and continue.
            err.mkdir(parents=True, exist_ok=True)
            dest = err / entry.name
            try:
                entry.replace(dest)
            except OSError:
                # If even the quarantine move fails, delete to unblock future polls.
                try:
                    entry.unlink()
                except FileNotFoundError:
                    pass
            # Record why for later forensics.
            _write_quarantine_note(err, entry.name, exc)
            continue

        # Move to archive after successful read. The moved path is where
        # the message now lives; we return the ORIGINAL path in the tuple
        # so callers have a stable identifier.
        dest = arc / entry.name
        try:
            entry.replace(dest)
        except OSError as exc:
            # Non-fatal: log and skip. We do not block other messages.
            _write_quarantine_note(err, entry.name, exc)
            continue

        out.append((entry, payload))
    return out


def _write_quarantine_note(err_dir: Path, orig_name: str, exc: BaseException) -> None:
    """Drop a small .note.txt alongside a quarantined file."""
    try:
        err_dir.mkdir(parents=True, exist_ok=True)
        note_path = err_dir / f"{orig_name}.note.txt"
        note_path.write_text(
            f"quarantined at {time.time()}: {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
    except OSError:
        # Note-writing is best-effort; never fail the caller for it.
        pass


def send_input(ipc_input_dir: Path, payload: dict) -> Path:
    """Write a message to a worker's input directory.

    Convenience wrapper over write_ipc_message, with a consistent return
    for callers that want to know the final path.
    """
    if not ipc_input_dir.exists():
        raise SovereignIOError(
            code="SA_IO_NOT_FOUND",
            message=f"ipc input directory does not exist: {ipc_input_dir}",
            context={"path": str(ipc_input_dir)},
        )
    return write_ipc_message(ipc_input_dir, payload)


__all__ = [
    "CLOSE_SENTINEL_NAME",
    "READ_GRACE_MS",
    "write_ipc_message",
    "write_close_sentinel",
    "is_close_sentinel",
    "clear_close_sentinel",
    "read_and_consume",
    "send_input",
]
