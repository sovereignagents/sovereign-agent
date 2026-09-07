"""Paused schedules preserve due work, and invalid definitions never poison later ticks."""

import json

import pytest

from sovereign_agent.assistant_work import schedule, tick, unschedule
from sovereign_agent.cli import main
from sovereign_agent.database import Database


def test_paused_scheduler_retains_due_state_then_coalesces_once(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    schedule(db, "morning", "lucy", "brief", first_due=100, interval_seconds=10)
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_control SET paused=1")
    assert tick(db, now=139) == []
    assert db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == 100
    assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 0
    with db.immediate() as connection:
        connection.execute("UPDATE assistant_control SET paused=0")
    assert len(tick(db, now=139)) == 1
    assert db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == 140
    assert tick(db, now=139) == []
    event = json.loads(
        db.connection.execute(
            "SELECT payload FROM events WHERE kind='assistant.job.enqueued'"
        ).fetchone()[0]
    )
    assert event["coalesced"] == 3
    db.close()


@pytest.mark.parametrize(
    "definition",
    [
        {"identifier": "x" * 251},
        {"identifier": " "},
        {"session": "x" * 201},
        {"channel": "local", "recipient": "123"},
        {"channel": "telegram:", "recipient": "123"},
        {"channel": "telegram:test", "recipient": "0"},
        {"channel": "telegram:test", "recipient": "١٢٣"},
        {"channel": None},
    ],
)
def test_invalid_definition_is_refused_before_storage(tmp_path, definition):
    db = Database(tmp_path / "agent.sqlite")
    arguments = dict(
        identifier="morning", session="lucy", prompt="brief", first_due=100, interval_seconds=10
    )
    arguments.update(definition)
    with pytest.raises(ValueError):
        schedule(db, **arguments)
    assert db.connection.execute("SELECT count(*) FROM assistant_jobs").fetchone()[0] == 0
    schedule(db, "valid", "lucy", "brief", first_due=100, interval_seconds=10)
    assert len(tick(db, now=100)) == 1
    db.close()


def test_duplicate_definition_and_disable_preserve_existing_work(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    schedule(db, "morning", "lucy", "brief", first_due=100, interval_seconds=10)
    created = tick(db, now=100)
    with pytest.raises(ValueError, match="already exists"):
        schedule(db, "morning", "other", "changed", first_due=0, interval_seconds=1)
    assert tuple(
        db.connection.execute(
            "SELECT session,prompt,interval_seconds,next_due FROM assistant_jobs"
        ).fetchone()
    ) == ("lucy", "brief", 10, 110)
    unschedule(db, "morning")
    unschedule(db, "morning")
    reopened = Database(db.path)
    assert tick(reopened, now=200) == []
    reopened.close()
    assert db.connection.execute("SELECT id FROM assistant_work").fetchone()[0] == created[0]
    with pytest.raises(ValueError, match="already exists"):
        schedule(db, "morning", "lucy", "brief", first_due=200, interval_seconds=20)
    with pytest.raises(ValueError, match="unknown schedule"):
        unschedule(db, "missing")
    db.close()


@pytest.mark.parametrize("maximum", [True, 1.5, 0, 1001])
def test_scheduler_scan_limit_is_an_actual_bounded_integer(tmp_path, maximum):
    db = Database(tmp_path / "agent.sqlite")
    with pytest.raises(ValueError, match="scheduler pass"):
        tick(db, maximum=maximum)
    db.close()


def test_cli_unschedule_stops_future_work_and_retains_definition(tmp_path, capsys):
    assert (
        main(
            [
                "agent",
                "schedule",
                "brief",
                "--root",
                str(tmp_path),
                "--id",
                "morning",
                "--first-due",
                "100",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["agent", "unschedule", "morning", "--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "DISABLED",
        "job": "morning",
        "existing_work": "retained",
    }
    db = Database(tmp_path / "agent.sqlite")
    assert tick(db, now=200) == []
    assert db.connection.execute("SELECT enabled FROM assistant_jobs").fetchone()[0] == 0
    db.close()
