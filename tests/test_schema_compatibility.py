"""A rollback executable cannot silently open and write an unknown schema."""

import sqlite3

import pytest

from sovereign_agent.database import MIGRATION_1, Database


def test_unknown_schema_is_refused_without_changing_bytes_or_leaking_connection(
    tmp_path, monkeypatch
):
    path = tmp_path / "agent.sqlite"
    db = Database(path)
    db.close()
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO schema_migrations VALUES (999,'future')")
    before = path.read_bytes()
    marker = path.with_suffix(".authority").read_bytes()
    original = sqlite3.connect
    opened = []

    def observe(*args, **kwargs):
        connection = original(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", observe)
    with pytest.raises(ValueError, match="unknown migrations: \\[999\\]"):
        Database(path)
    assert path.read_bytes() == before
    assert path.with_suffix(".authority").read_bytes() == marker
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_unknown_version_prevents_even_known_pending_migrations(tmp_path):
    path = tmp_path / "partial.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(MIGRATION_1)
        connection.executemany(
            "INSERT INTO schema_migrations VALUES (?,?)", [(1, "old"), (999, "future")]
        )
    before = path.read_bytes()
    with pytest.raises(ValueError, match="unknown migrations"):
        Database(path)
    assert path.read_bytes() == before
    assert not path.with_suffix(".authority").exists()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='assistant_work'"
            ).fetchone()
            is None
        )


def test_explicit_migrate_also_checks_compatibility(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    db.connection.execute("INSERT INTO schema_migrations VALUES (999,'future')")
    db.connection.commit()
    with pytest.raises(ValueError, match="unknown migrations"):
        db.migrate()
    assert 999 in db.applied_versions()
    db.close()


def test_malformed_migration_ledger_is_not_treated_as_an_empty_database(tmp_path):
    path = tmp_path / "malformed.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_migrations (unexpected TEXT)")
    before = path.read_bytes()
    with pytest.raises(sqlite3.OperationalError, match="version"):
        Database(path)
    assert path.read_bytes() == before
