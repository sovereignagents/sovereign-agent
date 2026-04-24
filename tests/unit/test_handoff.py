"""Tests for handoff protocol."""

from __future__ import annotations

import pytest

from sovereign_agent.errors import ValidationError
from sovereign_agent.handoff import Handoff, read_handoff, write_handoff
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc


def _make_handoff(session: Session, to_half: str = "structured") -> Handoff:
    return Handoff(
        from_half="loop",
        to_half=to_half,
        written_at=now_utc(),
        session_id=session.session_id,
        reason="confirm",
        context="destructive action",
        data={"action": "delete"},
    )


def test_write_and_read_roundtrip(fresh_session: Session) -> None:
    h = _make_handoff(fresh_session)
    path = write_handoff(fresh_session, "structured", h)
    assert path.name == "handoff_to_structured.json"
    loaded = read_handoff(fresh_session, "structured")
    assert loaded is not None
    assert loaded.reason == "confirm"
    assert loaded.data["action"] == "delete"


def test_write_rejects_target_mismatch(fresh_session: Session) -> None:
    h = _make_handoff(fresh_session, to_half="structured")
    with pytest.raises(ValidationError):
        write_handoff(fresh_session, "research", h)


def test_handoff_from_dict_validates_required_fields() -> None:
    with pytest.raises(ValidationError):
        Handoff.from_dict({"from_half": "loop"})  # lots of missing fields


def test_read_handoff_returns_none_when_absent(fresh_session: Session) -> None:
    assert read_handoff(fresh_session, "structured") is None
