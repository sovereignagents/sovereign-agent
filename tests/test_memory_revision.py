"""Forgetting must change future context, not only the preference table."""

import pytest

from sovereign_agent.assistant_context import context, forget, preferences, remember
from sovereign_agent.assistant_work import claim, enqueue, finish
from sovereign_agent.database import Database


def finish_result(db, origin, session, result):
    identifier = enqueue(db, origin, session, "Prepare a brief.")
    owner = claim(db, "worker", identifier=identifier)
    finish(db, owner, "DONE", result)
    return identifier


def test_forgetting_excludes_prior_summary_after_reopening(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    remember(db, "lucy", "supplier", "Example Creamery", "operator/message/1")
    remember(db, "lucy", "format", "three bullets", "operator/message/2")
    finish_result(db, "old", "lucy", "Lucy prefers Example Creamery.")
    assert "Example Creamery" in context(db, "lucy", "brief", allowed=frozenset())[0]["content"]
    forget(db, "lucy", "supplier")
    db.close()
    db = Database(tmp_path / "agent.sqlite")
    selected = context(db, "lucy", "brief", allowed=frozenset())[0]["content"]
    assert "Example Creamery" not in selected and "three bullets" in selected
    assert (
        db.connection.execute("SELECT result FROM assistant_work").fetchone()[0]
        == "Lucy prefers Example Creamery."
    )
    finish_result(db, "new", "lucy", "New summary after forgetting.")
    assert "New summary" in context(db, "lucy", "brief", allowed=frozenset())[0]["content"]
    db.close()


def test_late_completion_and_duplicate_intake_keep_the_old_context_revision(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    identifier = enqueue(db, "old", "lucy", "brief")
    owner = claim(db, "worker")
    other = Database(db.path)
    forget(other, "lucy", "supplier")
    finish(db, owner, "DONE", "Example Creamery from an already running turn.")
    assert enqueue(other, "old", "lucy", "brief") == identifier
    assert db.connection.execute("SELECT context_revision FROM assistant_work").fetchone()[0] == 0
    assert (
        "Example Creamery" not in context(other, "lucy", "brief", allowed=frozenset())[0]["content"]
    )
    other.close()
    db.close()


def test_forgetting_one_session_preserves_another_sessions_history(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    finish_result(db, "lucy-old", "lucy", "Lucy's old summary")
    finish_result(db, "other-old", "other", "Other operator's summary")
    forget(db, "lucy", "supplier")
    assert (
        "Lucy's old summary" not in context(db, "lucy", "brief", allowed=frozenset())[0]["content"]
    )
    assert (
        "Other operator's summary"
        in context(db, "other", "brief", allowed=frozenset())[0]["content"]
    )
    db.close()


def test_forgetting_rolls_back_preference_and_revision_together(tmp_path, monkeypatch):
    db = Database(tmp_path / "agent.sqlite")
    remember(db, "lucy", "supplier", "Example Creamery", "operator")

    def crash(*args, **kwargs):
        raise RuntimeError("event write failed")

    monkeypatch.setattr("sovereign_agent.assistant_context.append_event", crash)
    with pytest.raises(RuntimeError):
        forget(db, "lucy", "supplier")
    assert preferences(db, "lucy")[0]["value"] == "Example Creamery"
    assert (
        db.connection.execute("SELECT count(*) FROM assistant_memory_revisions").fetchone()[0] == 0
    )
    db.close()


def test_capacity_permits_correction_and_freeing_one_slot(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    for number in range(100):
        remember(db, "lucy", f"note-{number}", "value", "operator")
    with pytest.raises(ValueError, match="capacity"):
        remember(db, "lucy", "another", "value", "operator")
    remember(db, "lucy", "note-0", "corrected", "operator/correction")
    assert preferences(db, "lucy", "corrected", maximum=1)[0]["value"] == "corrected"
    forget(db, "lucy", "note-1")
    remember(db, "lucy", "another", "value", "operator")
    assert len(preferences(db, "lucy", maximum=100)) == 100
    db.close()
