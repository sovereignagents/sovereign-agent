"""Human-readable session report.

Reads the session's state, trace, and tickets; renders a markdown timeline.
Used by `sovereign-agent report <session_id>`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sovereign_agent.observability.trace import TraceReader
from sovereign_agent.session.directory import Session
from sovereign_agent.tickets.ticket import list_tickets


def generate_session_report(session: Session) -> str:
    """Return a markdown report describing everything that happened."""
    s = session.state
    lines: list[str] = []
    lines.append(f"# Session report: {s.session_id}")
    lines.append("")
    lines.append(f"- **Scenario:** {s.scenario}")
    lines.append(f"- **State:** `{s.state}`")
    lines.append(f"- **Current half:** `{s.current_half}`")
    lines.append(f"- **Created:** {s.created_at.isoformat()}")
    lines.append(f"- **Updated:** {s.updated_at.isoformat()}")
    if s.user_id:
        lines.append(f"- **User:** {s.user_id}")
    if s.result:
        lines.append("")
        lines.append("## Result")
        lines.append("")
        for key, value in s.result.items():
            preview = _short(value)
            lines.append(f"- **{key}:** {preview}")

    # Tickets
    tickets = list_tickets(session)
    lines.append("")
    lines.append(f"## Tickets ({len(tickets)})")
    lines.append("")
    if not tickets:
        lines.append("*No tickets recorded.*")
    else:
        for ticket in tickets:
            result = ticket.read_result()
            dur = ""
            if result.started_at and result.completed_at:
                dur = (
                    f" ({int((result.completed_at - result.started_at).total_seconds() * 1000)} ms)"
                )
            lines.append(
                f"- `{ticket.ticket_id}` — {ticket.operation} — **{result.state.value}**{dur}"
            )
            if result.summary:
                lines.append(f"    - {result.summary}")
            if result.error_code:
                lines.append(f"    - **Error [{result.error_code}]**: {result.error_message}")

    # Handoffs
    handoff_dir = session.handoffs_audit_dir
    if handoff_dir.exists():
        handoffs = sorted(p for p in handoff_dir.iterdir() if p.suffix == ".json")
        if handoffs:
            lines.append("")
            lines.append(f"## Handoffs ({len(handoffs)})")
            lines.append("")
            for h in handoffs:
                lines.append(f"- `{h.name}`")

    # Trace
    reader = TraceReader(session)
    by_type: dict[str, int] = defaultdict(int)
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    for event in reader:
        by_type[event.event_type] += 1
        if first_ts is None or event.timestamp < first_ts:
            first_ts = event.timestamp
        if last_ts is None or event.timestamp > last_ts:
            last_ts = event.timestamp
    total_events = sum(by_type.values())
    lines.append("")
    lines.append(f"## Trace events ({total_events})")
    lines.append("")
    if by_type:
        for etype, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- `{etype}`: {count}")
        if first_ts and last_ts:
            duration = (last_ts - first_ts).total_seconds()
            lines.append("")
            lines.append(
                f"*Span:* {first_ts.isoformat()} → {last_ts.isoformat()} ({duration:.1f}s)"
            )
    else:
        lines.append("*No trace events recorded.*")

    # Generated at footer.
    lines.append("")
    lines.append(f"*Generated at {datetime.now(tz=UTC).isoformat()}*")
    return "\n".join(lines) + "\n"


def _short(v: object, maxlen: int = 200) -> str:
    s = repr(v) if not isinstance(v, str) else v
    return s if len(s) <= maxlen else s[: maxlen - 1] + "…"


__all__ = ["generate_session_report"]
