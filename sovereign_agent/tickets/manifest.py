"""Manifest: the proof-of-work record written when a ticket succeeds.

Pattern D from the architecture doc. A long-running operation has NOT
succeeded until it has written a manifest.json with a verified checksum.
Not when the function returns, not when the worker exits, not when the
LLM says it's done. Only when there's a valid manifest.

This is the antidote to LLM hallucinated success at the framework level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sovereign_agent._internal.atomic import compute_sha256
from sovereign_agent.session.state import _parse_dt


@dataclass
class OutputRecord:
    """One output file listed in a manifest."""

    path: Path
    sha256: str
    size_bytes: int
    content_type: str = "application/json"

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OutputRecord:
        return cls(
            path=Path(data["path"]),
            sha256=data["sha256"],
            size_bytes=int(data["size_bytes"]),
            content_type=data.get("content_type", "application/json"),
        )


@dataclass
class Manifest:
    """Proof-of-work record for one ticket."""

    ticket_id: str
    operation: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    outputs: list[OutputRecord] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def verify(self) -> bool:
        """Check that every listed output exists and its sha256 matches.

        Idempotent and safe to call repeatedly (e.g. by graders after the fact).
        Returns True if every file verifies; False if any missing or mismatched.
        """
        for record in self.outputs:
            if not record.path.exists():
                return False
            actual = compute_sha256(record.path)
            if actual != record.sha256:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "operation": self.operation,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": self.duration_ms,
            "outputs": [o.to_dict() for o in self.outputs],
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Manifest:
        return cls(
            ticket_id=data["ticket_id"],
            operation=data["operation"],
            started_at=_parse_dt(data["started_at"]),
            completed_at=_parse_dt(data["completed_at"]),
            duration_ms=int(data["duration_ms"]),
            outputs=[OutputRecord.from_dict(o) for o in data.get("outputs", [])],
            metrics=data.get("metrics", {}),
        )


__all__ = ["Manifest", "OutputRecord"]
