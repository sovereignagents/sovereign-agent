"""Handoff protocol. See docs/architecture.md §2.16.

The file-based protocol by which one half transfers control to another half.
Write an atomic JSON file under ipc/handoff_to_<target>.json. The orchestrator
picks it up via IpcWatcher, validates, archives it to logs/handoffs/.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from sovereign_agent._internal.atomic import atomic_write_json
from sovereign_agent.errors import ValidationError
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import _parse_dt, now_utc

HalfName = Literal["loop", "structured", "research"]


@dataclass
class Handoff:
    from_half: str
    to_half: str
    written_at: datetime
    session_id: str
    reason: str
    context: str
    data: dict
    return_instructions: str = ""
    version: int = 1
    constraints_reminder: dict | None = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "from_half": self.from_half,
            "to_half": self.to_half,
            "written_at": self.written_at.isoformat(),
            "session_id": self.session_id,
            "reason": self.reason,
            "context": self.context,
            "data": self.data,
            "return_instructions": self.return_instructions,
            "constraints_reminder": self.constraints_reminder,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Handoff:
        required = ("from_half", "to_half", "session_id", "reason", "context", "data")
        for key in required:
            if key not in data:
                raise ValidationError(
                    code="SA_VAL_INVALID_HANDOFF_SCHEMA",
                    message=f"handoff payload missing required field {key!r}",
                    context={"payload": data},
                )
        return cls(
            version=int(data.get("version", 1)),
            from_half=data["from_half"],
            to_half=data["to_half"],
            written_at=_parse_dt(data.get("written_at") or now_utc().isoformat()),
            session_id=data["session_id"],
            reason=data["reason"],
            context=data["context"],
            data=data["data"],
            return_instructions=data.get("return_instructions", ""),
            constraints_reminder=data.get("constraints_reminder"),
        )


def write_handoff(session: Session, to_half: str, handoff: Handoff) -> Path:
    """Atomically write a handoff file to ipc/handoff_to_<to_half>.json."""
    if handoff.to_half != to_half:
        raise ValidationError(
            code="SA_VAL_INVALID_HANDOFF_SCHEMA",
            message=(
                f"to_half mismatch: handoff.to_half={handoff.to_half!r}, "
                f"parameter to_half={to_half!r}"
            ),
        )
    path = session.ipc_dir / f"handoff_to_{to_half}.json"
    atomic_write_json(path, handoff.to_dict())
    return path


def read_handoff(session: Session, to_half: str) -> Handoff | None:
    """Read the current handoff file if present, returns None if not."""
    path = session.ipc_dir / f"handoff_to_{to_half}.json"
    if not path.exists():
        return None
    import json

    with open(path, encoding="utf-8") as f:
        return Handoff.from_dict(json.load(f))


def read_latest_archived_handoff(session: Session, to_half: str) -> Handoff | None:
    """Return the most recent archived handoff for a target half, or None."""
    audit_dir = session.handoffs_audit_dir
    if not audit_dir.exists():
        return None
    matches = sorted(
        p for p in audit_dir.iterdir() if p.is_file() and to_half in p.name and p.suffix == ".json"
    )
    if not matches:
        return None
    import json

    with open(matches[-1], encoding="utf-8") as f:
        return Handoff.from_dict(json.load(f))


__all__ = [
    "HalfName",
    "Handoff",
    "write_handoff",
    "read_handoff",
    "read_latest_archived_handoff",
]
