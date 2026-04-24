"""Tests for Ticket, TicketState, Manifest (Decision 9 + Pattern D)."""

from __future__ import annotations

import pytest

from sovereign_agent._internal.atomic import atomic_write_json, compute_sha256
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.errors import ValidationError
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc
from sovereign_agent.tickets.manifest import Manifest, OutputRecord
from sovereign_agent.tickets.state import TicketState
from sovereign_agent.tickets.ticket import Ticket, create_ticket, list_tickets


def _build_manifest(
    ticket: Ticket, *, write_output: bool = True, corrupt: bool = False
) -> Manifest:
    raw_path = ticket.directory / "raw_output.json"
    if write_output:
        atomic_write_json(raw_path, {"ok": True})
    sha = compute_sha256(raw_path) if raw_path.exists() else "0" * 64
    if corrupt:
        sha = "f" * 64
    return Manifest(
        ticket_id=ticket.ticket_id,
        operation=ticket.operation,
        started_at=now_utc(),
        completed_at=now_utc(),
        duration_ms=1,
        outputs=[
            OutputRecord(
                path=raw_path,
                sha256=sha,
                size_bytes=raw_path.stat().st_size if raw_path.exists() else 0,
            )
        ],
    )


def test_ticket_create_starts_in_pending(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    assert t.read_state() == TicketState.PENDING


def test_ticket_happy_path(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.start()
    assert t.read_state() == TicketState.RUNNING
    manifest = _build_manifest(t)
    t.succeed(manifest, "it worked")
    assert t.read_state() == TicketState.SUCCESS
    result = t.read_result()
    assert result.state == TicketState.SUCCESS
    assert result.summary == "it worked"
    assert result.manifest is not None
    assert result.manifest.verify() is True


def test_ticket_succeed_rejects_invalid_manifest(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.start()
    bad = _build_manifest(t, corrupt=True)
    with pytest.raises(SovereignIOError):
        t.succeed(bad, "should fail")
    # Stays in RUNNING — caller can recover by calling fail().
    assert t.read_state() == TicketState.RUNNING


def test_ticket_succeed_requires_non_empty_summary(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.start()
    m = _build_manifest(t)
    with pytest.raises(ValidationError):
        t.succeed(m, "")


def test_ticket_state_transitions_forward_only(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.start()
    m = _build_manifest(t)
    t.succeed(m, "done")
    # SUCCESS is terminal; no further transitions.
    with pytest.raises(ValidationError):
        t.start()
    with pytest.raises(ValidationError):
        t.fail("SA_TOOL_EXECUTION_FAILED", "nope")


def test_ticket_skip(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.skip("no work needed")
    assert t.read_state() == TicketState.SKIPPED
    assert "no work needed" in t.read_summary()


def test_ticket_fail(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.start()
    t.fail("SA_TOOL_EXECUTION_FAILED", "broke")
    assert t.read_state() == TicketState.ERROR
    r = t.read_result()
    assert r.error_code == "SA_TOOL_EXECUTION_FAILED"
    assert r.error_message == "broke"
    assert "SA_TOOL_EXECUTION_FAILED" in r.summary


def test_manifest_verify_detects_tampering(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.start()
    m = _build_manifest(t)
    t.succeed(m, "ok")
    # Tamper with the output file after the ticket succeeds.
    raw = t.directory / "raw_output.json"
    raw.write_text('{"tampered": true}')
    assert m.verify() is False


def test_manifest_verify_missing_file(fresh_session: Session) -> None:
    t = create_ticket(fresh_session, operation="test.op")
    t.start()
    m = _build_manifest(t)
    t.succeed(m, "ok")
    (t.directory / "raw_output.json").unlink()
    assert m.verify() is False


def test_ticket_ids_unique(fresh_session: Session) -> None:
    ids = {create_ticket(fresh_session, operation="op").ticket_id for _ in range(500)}
    assert len(ids) == 500


def test_list_tickets(fresh_session: Session) -> None:
    t1 = create_ticket(fresh_session, operation="a")
    t2 = create_ticket(fresh_session, operation="b")
    t2.start()
    t2.fail("SA_TOOL_EXECUTION_FAILED", "bad")
    all_tickets = list_tickets(fresh_session)
    assert {t.ticket_id for t in all_tickets} == {t1.ticket_id, t2.ticket_id}
    errs = list_tickets(fresh_session, state_filter=TicketState.ERROR)
    assert [t.ticket_id for t in errs] == [t2.ticket_id]
