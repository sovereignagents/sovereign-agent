"""Trace reader and event type.

The trace writer itself is `Session.append_trace_event` (see
sovereign_agent/session/directory.py), which does an atomic O_APPEND of one
JSON object per line. This file provides the reader/iterator and the
recommended event-shape dataclass.

See docs/architecture.md §2.17.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import _parse_dt


@dataclass
class TraceEvent:
    """Recommended shape of a trace event.

    The trace file is a loose JSONL — readers should tolerate missing
    optional fields. This dataclass is a convenience for consumers that
    want typed access.
    """

    event_type: str
    actor: str
    timestamp: datetime
    session_id: str = ""
    event_id: str = ""
    ticket_id: str | None = None
    payload: dict = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict) -> TraceEvent:
        ts = raw.get("timestamp")
        return cls(
            event_type=raw.get("event_type", "unknown"),
            actor=raw.get("actor", "unknown"),
            timestamp=_parse_dt(ts) if ts else datetime.fromtimestamp(0),
            session_id=raw.get("session_id", ""),
            event_id=raw.get("event_id", ""),
            ticket_id=raw.get("ticket_id"),
            payload=raw.get("payload", {}),
        )


class TraceReader:
    """Iterator over trace events for one session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def __iter__(self) -> Iterator[TraceEvent]:
        path = self.session.trace_path
        if not path.exists():
            return iter([])
        return _read_jsonl(path)

    def filter(
        self,
        *,
        event_type: str | None = None,
        ticket_id: str | None = None,
        actor: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[TraceEvent]:
        for event in self:
            if event_type is not None and event.event_type != event_type:
                continue
            if ticket_id is not None and event.ticket_id != ticket_id:
                continue
            if actor is not None and event.actor != actor:
                continue
            if since is not None and event.timestamp < since:
                continue
            yield event


def _read_jsonl(path: Path) -> Iterator[TraceEvent]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                # A truncated last line from a crash is survivable — skip and continue.
                continue
            yield TraceEvent.from_raw(raw)


__all__ = ["TraceEvent", "TraceReader"]
