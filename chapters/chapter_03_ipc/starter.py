"""Chapter 3 starter — IPC primitives and the Ticket state machine.

Implement:

  write_ipc_message(directory, payload) -> Path
    Write JSON atomically (temp file + rename). Filename format:
    <millis_since_epoch>-<4-hex>.json so files sort chronologically.

  Ticket with transitions: pending -> running -> (success | skipped | error)
    On succeed(), require a verified Manifest. On fail(), record the
    structured error code.

See chapters/chapter_03_ipc/solution.py for reference exports.

Run `pytest chapters/chapter_03_ipc/tests.py -v` to check your work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


def write_ipc_message(directory: Path, payload: dict) -> Path:
    raise NotImplementedError(
        "Implement atomic JSON write: temp file -> os.fsync -> Path.replace()."
    )


class TicketState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class OutputRecord:
    path: Path
    sha256: str
    size_bytes: int


@dataclass
class Manifest:
    ticket_id: str
    operation: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    outputs: list[OutputRecord] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def verify(self) -> bool:
        """Check every listed output file exists and its sha256 matches."""
        raise NotImplementedError
