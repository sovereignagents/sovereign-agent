"""Transactions, migrations, and append-only enforcement.

These prove properties of the DATABASE, not of Python politeness. A rule that
lives only in a convention is a rule that a tired contributor removes.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import reference_organizations.store as store
from reference_organizations.store import RestockProposal, apply_restock, record_sale, seed
from sovereign_agent.database import MIGRATION_1, MIGRATIONS, Database
from sovereign_agent.organization import Organization


def store_state(org: Organization) -> tuple[int, int, int]:
    on_hand = int(
        org.db.connection.execute("SELECT on_hand FROM inventory WHERE sku = 'SKU-TEA'").fetchone()[
            "on_hand"
        ]
    )
    events = int(
        org.db.connection.execute(
            "SELECT COUNT(*) AS c FROM events WHERE kind = 'replenishment.committed'"
        ).fetchone()["c"]
    )
    purchases = int(
        org.db.connection.execute(
            "SELECT COUNT(*) AS c FROM cash_entries WHERE amount_cents < 0"
        ).fetchone()["c"]
    )
    return on_hand, events, purchases


def test_rollback_after_inventory_write_leaves_nothing_behind(tmp_path: Path, governed) -> None:
    """Fail AFTER the inventory UPDATE but before the event commits."""
    org, _outcome_id, _sow_id, assignment_id = governed
    signal = record_sale(org.db, "SKU-TEA", 2, 400)
    before = store_state(org)
    with patch.object(store, "append_event", side_effect=RuntimeError("injected failure")):
        with pytest.raises(RuntimeError, match="injected failure"):
            apply_restock(org.db, RestockProposal("SKU-TEA", 6), assignment_id, signal.id)
    assert store_state(org) == before, "partial business mutation survived a rollback"


def test_rollback_leaves_no_orphan_cash_entry(tmp_path: Path, governed) -> None:
    org, _outcome_id, _sow_id, assignment_id = governed
    signal = record_sale(org.db, "SKU-TEA", 2, 400)
    with patch.object(store, "append_event", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            apply_restock(org.db, RestockProposal("SKU-TEA", 6), assignment_id, signal.id)
    row = org.db.connection.execute(
        "SELECT COUNT(*) AS c FROM cash_entries WHERE amount_cents < 0"
    ).fetchone()
    assert row["c"] == 0


def test_successful_sale_and_replenishment_keep_cash_reconciled(tmp_path: Path, governed) -> None:
    org, _outcome_id, _sow_id, assignment_id = governed
    signal = record_sale(org.db, "SKU-TEA", 2, 400)
    assert store.cash_balance_cents(org.db) == 10_800
    apply_restock(org.db, RestockProposal("SKU-TEA", 6), assignment_id, signal.id)
    # 10000 opening + 800 sale - (6 * 120) purchase
    assert store.cash_balance_cents(org.db) == 10_080


def test_inventory_never_goes_negative(tmp_path: Path) -> None:
    from sovereign_agent.errors import Refusal

    org = Organization.init(tmp_path)
    seed(org.db)
    with pytest.raises(Refusal, match="negative"):
        record_sale(org.db, "SKU-TEA", 99, 400)


def test_sale_refuses_reserved_stock_without_partial_writes(tmp_path: Path) -> None:
    from sovereign_agent.errors import Refusal

    org = Organization.init(tmp_path)
    seed(org.db)
    org.db.connection.execute(
        "UPDATE inventory SET on_hand = 6, reserved = 5 WHERE sku = 'SKU-TEA'"
    )
    org.db.connection.commit()
    before = {
        table: int(org.db.connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])
        for table in ("cash_entries", "signals", "events")
    }

    with pytest.raises(Refusal, match="reserved stock"):
        record_sale(org.db, "SKU-TEA", 2, 400)

    row = org.db.connection.execute(
        "SELECT on_hand, reserved FROM inventory WHERE sku = 'SKU-TEA'"
    ).fetchone()
    assert (row["on_hand"], row["reserved"]) == (6, 5)
    assert {
        table: int(org.db.connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])
        for table in ("cash_entries", "signals", "events")
    } == before


@pytest.mark.parametrize("quantity", [0, -1])
def test_sale_quantity_must_be_positive(tmp_path: Path, quantity: int) -> None:
    from sovereign_agent.errors import Refusal

    org = Organization.init(tmp_path)
    seed(org.db)
    with pytest.raises(Refusal, match="positive"):
        record_sale(org.db, "SKU-TEA", quantity, 400)


def test_sale_severity_uses_available_stock_after_reservations(tmp_path: Path) -> None:
    org = Organization.init(tmp_path)
    seed(org.db)
    org.db.connection.execute(
        "UPDATE inventory SET on_hand = 6, reserved = 2, reorder_point = 3 WHERE sku = 'SKU-TEA'"
    )
    org.db.connection.commit()

    signal = record_sale(org.db, "SKU-TEA", 1, 400)

    assert signal.severity == "warning"
    event = org.db.connection.execute(
        "SELECT payload FROM events WHERE kind = 'sale.committed' ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    payload = json.loads(event["payload"])
    assert payload["available_after"] == 3
    assert payload["reserved"] == 2


def test_events_reject_update_and_delete(tmp_path: Path) -> None:
    org = Organization.init(tmp_path)
    seed(org.db)
    for statement in (
        "UPDATE events SET kind = 'TAMPERED'",
        "DELETE FROM events",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            org.db.connection.execute(statement)
        org.db.connection.rollback()


def test_insert_or_replace_cannot_bypass_the_append_only_guard(tmp_path: Path) -> None:
    """Without PRAGMA recursive_triggers, REPLACE deletes a row silently.

    SQLite does not fire BEFORE DELETE triggers for the implicit delete inside
    INSERT OR REPLACE unless recursive triggers are on. A guard that misses this
    is decorative.
    """
    org = Organization.init(tmp_path)
    row = org.db.connection.execute("SELECT id, kind FROM events LIMIT 1").fetchone()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        org.db.connection.execute(
            "INSERT OR REPLACE INTO events(id, kind, payload, created_at) "
            "VALUES (?, 'SNEAKY', '{}', 't')",
            (row["id"],),
        )
    org.db.connection.rollback()
    after = org.db.connection.execute(
        "SELECT kind FROM events WHERE id = ?", (row["id"],)
    ).fetchone()
    assert after["kind"] == row["kind"]


def test_fresh_database_applies_every_migration(tmp_path: Path) -> None:
    db = Database(tmp_path / "fresh.db")
    assert db.applied_versions() == {version for version, _ in MIGRATIONS}
    triggers = {
        row["name"]
        for row in db.connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    }
    assert {"events_no_update", "events_no_delete"} <= triggers


def test_upgrade_from_prior_schema_preserves_data(tmp_path: Path) -> None:
    """A database released at version 1 upgrades forward without losing rows."""
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(MIGRATION_1)
    legacy.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (1, datetime('now'))")
    legacy.execute(
        "INSERT INTO events(id, kind, payload, created_at) "
        "VALUES ('evt_legacy', 'legacy.kind', '{}', '2026-01-01T00:00:00Z')"
    )
    legacy.commit()
    legacy.close()

    db = Database(path)
    assert db.applied_versions() == {version for version, _ in MIGRATIONS}
    row = db.connection.execute(
        "SELECT COUNT(*) AS c FROM events WHERE id = 'evt_legacy'"
    ).fetchone()
    assert row["c"] == 1, "the upgrade destroyed pre-existing history"
    columns = {row[1] for row in db.connection.execute("PRAGMA table_info(evidence)")}
    assert {"outcome_id", "check_id", "success", "state_digest"} <= columns


def test_reopening_does_not_reapply_migrations(tmp_path: Path) -> None:
    """migrate() runs on every open, so it must be a no-op once applied."""
    path = tmp_path / "twice.db"
    first = Database(path)
    stamps = first.connection.execute(
        "SELECT version, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    second = Database(path)
    again = second.connection.execute(
        "SELECT version, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()
    assert [tuple(row) for row in stamps] == [tuple(row) for row in again]
    triggers = {
        row["name"]
        for row in second.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    assert {"events_no_update", "events_no_delete"} <= triggers


def test_migrations_are_forward_only_and_ordered() -> None:
    versions = [version for version, _ in MIGRATIONS]
    assert versions == sorted(versions), "migrations must apply in ascending order"
    assert len(set(versions)) == len(versions), "duplicate migration version"


def test_signal_is_recorded_with_the_sale(tmp_path: Path) -> None:
    org = Organization.init(tmp_path)
    seed(org.db)
    signal = record_sale(org.db, "SKU-TEA", 2, 400)
    row = org.db.connection.execute(
        "SELECT COUNT(*) AS c FROM signals WHERE id = ?", (signal.id,)
    ).fetchone()
    assert row["c"] == 1


def test_idempotency_is_scoped_to_assignment_and_sku(tmp_path: Path) -> None:
    """Replay protection must not silently swallow a different product's restock.

    Keyed on the assignment alone, a replenishment of SKU-B would make a later
    restock of SKU-TEA under the same assignment return "already done" while the
    tea shelf stayed empty.
    """
    import json

    # No declared subject, so the outcome does not constrain which SKU the
    # effect may touch. That is what lets this test exercise the (assignment,
    # kind, subject) key across two products under one assignment.
    from .helpers import governed_assignment

    org, _outcome_id, _sow_id, assignment_id = governed_assignment(tmp_path, subject="")
    signal = record_sale(org.db, "SKU-TEA", 2, 400)
    org.db.connection.execute(
        "INSERT OR REPLACE INTO products(sku, record) VALUES ('SKU-B', ?)",
        (json.dumps({"sku": "SKU-B", "name": "b", "unit_cost_cents": 10, "price_cents": 20}),),
    )
    org.db.connection.execute(
        "INSERT OR REPLACE INTO inventory(sku, on_hand, reserved, reorder_point, record) "
        "VALUES ('SKU-B', 0, 0, 1, '{}')"
    )
    org.db.connection.commit()

    apply_restock(org.db, RestockProposal("SKU-B", 3), assignment_id)
    result = apply_restock(org.db, RestockProposal("SKU-TEA", 6), assignment_id, signal.id)
    assert result.get("idempotent_replay") is None, "a different SKU was treated as a replay"
    row = org.db.connection.execute(
        "SELECT on_hand FROM inventory WHERE sku = 'SKU-TEA'"
    ).fetchone()
    assert int(row["on_hand"]) == 8

    replay = apply_restock(org.db, RestockProposal("SKU-TEA", 6), assignment_id, signal.id)
    assert replay.get("idempotent_replay") is True, "same assignment and SKU must still be a no-op"


def test_append_only_holds_from_a_connection_without_the_pragma(tmp_path: Path) -> None:
    """The guarantee must not depend on application code setting a PRAGMA.

    `recursive_triggers` is per-connection. With only the BEFORE DELETE guard,
    `INSERT OR REPLACE` from a plain sqlite3 connection — the exact tool
    Chapter 1 teaches — silently overwrote an event and left the row count
    unchanged, while verify_store_outcome still reported "ACCEPTED and true".

    This test opens its OWN connection and deliberately does not set the pragma,
    so it fails if enforcement ever moves back into application code.
    """
    org = Organization.init(tmp_path)
    seed(org.db)
    row = org.db.connection.execute("SELECT id, kind FROM events LIMIT 1").fetchone()
    event_id, original_kind = str(row["id"]), str(row["kind"])
    org.db.close()

    outsider = sqlite3.connect(tmp_path / ".sovereign" / "organization.db")
    outsider.row_factory = sqlite3.Row
    try:
        for statement, parameters in (
            (
                "INSERT OR REPLACE INTO events(id, kind, payload, created_at) "
                "VALUES (?, 'TAMPERED', '{}', 'now')",
                (event_id,),
            ),
            ("UPDATE events SET kind = 'TAMPERED' WHERE id = ?", (event_id,)),
            ("DELETE FROM events WHERE id = ?", (event_id,)),
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                outsider.execute(statement, parameters)
                outsider.commit()
            outsider.rollback()

        surviving = outsider.execute("SELECT kind FROM events WHERE id = ?", (event_id,)).fetchone()
        assert surviving["kind"] == original_kind
    finally:
        outsider.close()


def test_a_failed_migration_rolls_back_schema_and_stamp(tmp_path: Path) -> None:
    """A migration that fails part way through must leave nothing behind.

    `executescript()` COMMITs any open transaction before running, so the first
    version of this code left a half-created schema behind, unstamped, and
    reopening re-ran the migration and failed forever. Reported on PR #24.
    """
    import sovereign_agent.database as database_module

    path = tmp_path / "broken.db"
    broken = "CREATE TABLE partial_survivor (id TEXT);\nTHIS IS INVALID SQL;\n"
    original = database_module.MIGRATIONS
    database_module.MIGRATIONS = original + ((99, broken),)
    try:
        with pytest.raises(sqlite3.OperationalError):
            Database(path)
    finally:
        database_module.MIGRATIONS = original

    inspector = sqlite3.connect(path)
    try:
        leaked = inspector.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='partial_survivor'"
        ).fetchall()
        assert leaked == [], "a failed migration left schema behind"
        stamped = [
            int(row[0]) for row in inspector.execute("SELECT version FROM schema_migrations")
        ]
        assert 99 not in stamped, "a failed migration was stamped as applied"
        assert sorted(stamped) == [version for version, _ in original]
    finally:
        inspector.close()

    # The database must still be openable afterwards.
    recovered = Database(path)
    assert recovered.applied_versions() == {version for version, _ in original}
    recovered.close()


def test_migration_statement_splitting_keeps_trigger_bodies_intact() -> None:
    """Trigger bodies contain semicolons; splitting must not cut them in half."""
    from sovereign_agent.database import MIGRATION_3, _split_statements

    statements = _split_statements(MIGRATION_3)
    assert len(statements) == 1
    assert statements[0].startswith("CREATE TRIGGER")
    assert statements[0].rstrip().endswith("END;")


def test_the_effect_key_cannot_collide_across_assignment_and_subject(tmp_path: Path) -> None:
    """Structured columns, not a concatenated string.

    Raised by Sparring: the key was `f"restock:{assignment_id}:{sku}"`, so
    (assignment='asg_A', sku='TEA:X') and (assignment='asg_A:TEA', sku='X')
    produced the same string. A colliding pair returned idempotent_replay=True
    — a restock that never happened, reported as success. That made structured
    columns a correctness fix rather than a schema preference.
    """
    db = Database(tmp_path / "collide.db")
    db.connection.execute("INSERT INTO actors(id, record) VALUES ('op', '{}')")
    db.connection.execute("INSERT INTO outcomes(id, record) VALUES ('out', '{}')")
    db.connection.execute("INSERT INTO sows(id, outcome_id, record) VALUES ('sow', 'out', '{}')")
    for assignment_id in ("asg_A", "asg_A:TEA"):
        db.connection.execute(
            "INSERT INTO assignments(id, sow_id, actor_id, record) VALUES (?, 'sow', 'op', '{}')",
            (assignment_id,),
        )
    db.connection.commit()

    legacy_key = "restock:asg_A:TEA:X"
    assert f"restock:asg_A:{'TEA:X'}" == legacy_key
    assert f"restock:{'asg_A:TEA'}:X" == legacy_key, "precondition: the old scheme collided"

    for evidence_id, assignment_id, subject in (
        ("e1", "asg_A", "TEA:X"),
        ("e2", "asg_A:TEA", "X"),
    ):
        db.connection.execute(
            "INSERT INTO effects(id, assignment_id, kind, subject, payload, created_at, "
            "outcome_id) VALUES (?, ?, 'replenishment', ?, '{}', 't', 'out')",
            (evidence_id, assignment_id, subject),
        )
    db.connection.commit()
    row = db.connection.execute("SELECT COUNT(*) AS c FROM effects").fetchone()
    assert int(row["c"]) == 2, "structured columns must keep these pairs distinct"
    db.close()


def test_a_migration_that_cannot_preserve_the_ledger_refuses_to_run(tmp_path: Path) -> None:
    """Fail closed. Never decide which history was worth keeping.

    Migration 10 rebuilds `effects` with a NOT NULL outcome_id. Its first
    version carried `WHERE COALESCE(...) IS NOT NULL` so the rebuild would always
    succeed — silently dropping every legacy row it could not attribute, then
    DROPping the old table, destroying an operational record from an append-only
    ledger while reporting success. Reported on PR #24 round 5.
    """
    import sovereign_agent.database as database_module

    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    for version, script in database_module.MIGRATIONS:
        if version > 9:
            break
        for statement in database_module._split_statements(script):  # noqa: SLF001
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
    connection.execute("INSERT INTO actors(id, record) VALUES ('op', '{}')")
    connection.execute("INSERT INTO outcomes(id, record) VALUES ('out', '{}')")
    connection.execute("INSERT INTO sows(id, outcome_id, record) VALUES ('sow', 'out', '{}')")
    connection.execute(
        "INSERT INTO assignments(id, sow_id, actor_id, record) VALUES ('a', 'sow', 'op', '{}')"
    )
    # An effect with no attribution in the column and none in the payload.
    connection.execute(
        "INSERT INTO effects(id, assignment_id, kind, subject, payload, created_at) "
        "VALUES ('e_legacy', 'a', 'replenishment', 'SKU-TEA', '{}', 't')"
    )
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        Database(path)

    inspector = sqlite3.connect(path)
    try:
        surviving = inspector.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
        assert surviving == 1, "the migration destroyed an operational record"
        stamped = [
            int(row[0]) for row in inspector.execute("SELECT version FROM schema_migrations")
        ]
        assert 10 not in stamped, "a failed migration was stamped as applied"
        assert inspector.execute(
            "SELECT name FROM sqlite_master WHERE name = 'effects'"
        ).fetchone(), "the original table was dropped despite the failure"
    finally:
        inspector.close()


def test_append_only_guards_exist_on_fresh_and_upgraded_databases(tmp_path: Path) -> None:
    """The guards must reach EXISTING databases, not just new ones.

    MIGRATION_12's body is computed from the table list, so adding a table would
    change the bytes of an already-stamped version: fresh installs would be
    guarded and every upgraded database silently skipped. Raised by Sparring,
    who noted the original test built a fresh database and therefore passed in
    both worlds.
    """
    import sovereign_agent.database as database_module
    from sovereign_agent.database import APPEND_ONLY_TABLES

    def guards(db: Database, table: str) -> set[str]:
        return {
            str(row["name"])
            for row in db.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                (table,),
            )
        }

    fresh = Database(tmp_path / "fresh.db")
    try:
        for table in APPEND_ONLY_TABLES:
            assert guards(fresh, table) == {
                f"{table}_no_update",
                f"{table}_no_delete",
                f"{table}_no_replace",
            }, f"{table} is listed append-only but is unguarded on a fresh database"
    finally:
        fresh.close()

    # Build a database stamped up to the version BEFORE the guards, then upgrade.
    path = tmp_path / "upgraded.db"
    connection = sqlite3.connect(path)
    for version, script in database_module.MIGRATIONS:
        if version >= 12:
            break
        for statement in database_module._split_statements(script):  # noqa: SLF001
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
    connection.commit()
    connection.close()

    upgraded = Database(path)
    try:
        for table in APPEND_ONLY_TABLES:
            assert guards(upgraded, table) == {
                f"{table}_no_update",
                f"{table}_no_delete",
                f"{table}_no_replace",
            }, f"{table} is unguarded after an UPGRADE; the guards only reach new installs"
    finally:
        upgraded.close()


def test_receipts_are_deliberately_not_append_only(tmp_path: Path) -> None:
    """Absence from the list must be a decision, not an oversight.

    `put_serialized` rewrites a receipt in place while an assignment runs, so
    receipts cannot be append-only. Acceptance guards them differently, by
    requiring the canonical record and the indexed columns to agree.
    """
    from sovereign_agent.database import APPEND_ONLY_TABLES

    assert "receipts" not in APPEND_ONLY_TABLES
    db = Database(tmp_path / "receipts.db")
    try:
        triggers = db.connection.execute(
            "SELECT COUNT(*) AS c FROM sqlite_master WHERE type = 'trigger' "
            "AND tbl_name = 'receipts'"
        ).fetchone()
        assert int(triggers["c"]) == 0
    finally:
        db.close()


def test_a_forged_effect_cannot_be_inserted_from_outside(tmp_path: Path) -> None:
    """The concrete attack: re-attributing an effect to credit idle work."""
    from sovereign_agent.models import Role

    org = Organization.init(tmp_path)
    seed(org.db)
    outcome = org.create_outcome(
        "t", "d", ["inventory_at_or_above_reorder_point"], "principal-human", "SKU-TEA"
    )
    org.activate(outcome.id, "master-course")
    signal = record_sale(org.db, "SKU-TEA", 2, 400)
    sow = org.create_sow(outcome.id, "w", Role.OPERATOR, "master-course", "replenishment")
    org.ready_sow(sow.id)
    assignment = org.run_assignment(org.assign(sow.id, "operator-course", "master-course").id)
    apply_restock(org.db, RestockProposal("SKU-TEA", 6), assignment.id, signal.id)
    org.db.close()

    outsider = sqlite3.connect(tmp_path / ".sovereign" / "organization.db")
    outsider.row_factory = sqlite3.Row
    try:
        row = outsider.execute("SELECT id FROM effects LIMIT 1").fetchone()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            outsider.execute(
                "UPDATE effects SET assignment_id = 'asg_FORGED' WHERE id = ?", (row["id"],)
            )
            outsider.commit()
        outsider.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            outsider.execute("DELETE FROM effects WHERE id = ?", (row["id"],))
            outsider.commit()
    finally:
        outsider.close()


def test_migration_12_content_is_frozen() -> None:
    """An applied migration's BYTES must never change — not just its table list.

    The first attempt at this froze `MIGRATION_12_TABLES` and left the body
    flowing through the shared `_append_only_triggers()` helper, so editing the
    helper still rewrote an applied migration while this test passed. Reported
    on PR #24 round 9, with the digest below independently computed by the
    reviewer.

    Fresh installs would take the new bytes; databases that already stamped 12
    would not. Same code, two schemas.
    """
    import hashlib

    from sovereign_agent.database import (
        APPEND_ONLY_TABLES,
        MIGRATION_12,
        MIGRATION_12_SHA256,
        MIGRATION_12_TABLES,
        MIGRATIONS,
    )

    digest = hashlib.sha256(MIGRATION_12.encode()).hexdigest()
    assert digest == MIGRATION_12_SHA256, (
        "migration 12 has been applied to real databases; its bytes are history. "
        "Add a NEW migration instead of editing this one."
    )
    assert MIGRATION_12_SHA256 == (
        "cb5483b35e4ef78d761381dc9a1ac940c59b574f7716c17c84bf9b6c89392a5e"
    ), "the pinned digest itself was edited"

    assert MIGRATION_12_TABLES == ("effects", "verifications", "reviews", "evidence")
    for table in MIGRATION_12_TABLES:
        assert f"{table}_no_update" in MIGRATION_12

    # Any append-only table not covered by 12 needs its own later migration,
    # or existing databases never receive its triggers.
    later = set(APPEND_ONLY_TABLES) - set(MIGRATION_12_TABLES) - {"events"}
    for table in later:
        covered = any(
            f"{table}_no_update" in script for version, script in MIGRATIONS if version > 12
        )
        assert covered, (
            f"{table} is listed append-only but no migration after 12 guards it; "
            "add a NEW migration for further tables"
        )


def test_migration_12_does_not_depend_on_the_shared_helper() -> None:
    """Editing the helper must not be able to rewrite an applied migration.

    The helper stays for building FUTURE migrations. Version 12 is a literal, so
    this asserts the independence directly rather than trusting the reading:
    a helper whose output changed would no longer match the frozen bytes.
    """
    from sovereign_agent.database import MIGRATION_12, MIGRATION_12_TABLES, _append_only_triggers

    generated = "".join(_append_only_triggers(table) for table in MIGRATION_12_TABLES)
    assert generated == MIGRATION_12, (
        "the helper and the shipped migration have diverged. That is ALLOWED — "
        "version 12 is frozen and the helper may evolve for future migrations — "
        "but update this test deliberately rather than by accident."
    )
    import pathlib

    source = pathlib.Path(__file__).resolve().parent.parent / "src/sovereign_agent/database.py"
    body = source.read_text(encoding="utf-8")
    assignment = body.split("MIGRATION_12 = ", 1)[1][:120]
    assert "_append_only_triggers" not in assignment, (
        "MIGRATION_12 is generated again; an applied migration must be a literal"
    )


# === Migration 13 (Unit 8: fencing) against a populated Unit 7 database =====


def _build_unit7_shaped_database(path: Path) -> None:
    """Apply migrations 1-12 by hand and populate real operational rows --
    an outcome, a SOW, an assignment, a claimed message with real lease
    state, and a receipt -- the shape a real Unit-7-era organization.db
    would have on disk the moment before Unit 8's migration 13 first runs
    against it. Mirrors `test_a_migration_that_cannot_preserve_the_ledger_
    refuses_to_run`'s own hand-migration pattern."""
    import sovereign_agent.database as database_module

    connection = sqlite3.connect(path)
    for version, script in database_module.MIGRATIONS:
        if version > 12:
            break
        for statement in database_module._split_statements(script):  # noqa: SLF001
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
    connection.execute("INSERT INTO actors(id, record) VALUES ('operator-course', '{}')")
    connection.execute("INSERT INTO outcomes(id, record) VALUES ('out_legacy', '{}')")
    connection.execute(
        "INSERT INTO sows(id, outcome_id, record) VALUES ('sow_legacy', 'out_legacy', '{}')"
    )
    connection.execute(
        "INSERT INTO assignments(id, sow_id, actor_id, record) "
        "VALUES ('asg_legacy', 'sow_legacy', 'operator-course', "
        '\'{"id": "asg_legacy", "state": "COMPLETED"}\')'
    )
    connection.execute(
        "INSERT INTO messages(id, recipient, record, state, claim_owner, claim_expires_at) "
        "VALUES ('msg_legacy', 'operator-course', "
        '\'{"id": "msg_legacy", "state": "CLAIMED", "claim_owner": "operator-course"}\', '
        "'CLAIMED', 'operator-course', '2020-01-01T00:00:00+00:00')"
    )
    connection.execute(
        "INSERT INTO receipts(id, record, assignment_id, status) "
        "VALUES ('rct_legacy', '{\"id\": \"rct_legacy\"}', 'asg_legacy', 'completed')"
    )
    connection.commit()
    connection.close()


def test_migration_13_upgrade_from_a_populated_unit7_database_preserves_every_record(
    tmp_path: Path,
) -> None:
    """The upgrade path: a real Unit-7-shaped database (migrations 1-12,
    with genuine operational rows already on disk) opens cleanly under
    Unit 8's code, applies migration 13, and loses nothing."""
    path = tmp_path / "unit7.db"
    _build_unit7_shaped_database(path)

    db = Database(path)
    assert db.applied_versions() == {version for version, _ in MIGRATIONS}
    assert 13 in db.applied_versions()

    assert (
        db.connection.execute(
            "SELECT COUNT(*) AS c FROM assignments WHERE id = 'asg_legacy'"
        ).fetchone()["c"]
        == 1
    ), "the upgrade destroyed a pre-existing assignment"
    assert (
        db.connection.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE id = 'msg_legacy'"
        ).fetchone()["c"]
        == 1
    ), "the upgrade destroyed a pre-existing message"
    assert (
        db.connection.execute(
            "SELECT COUNT(*) AS c FROM receipts WHERE id = 'rct_legacy'"
        ).fetchone()["c"]
        == 1
    ), "the upgrade destroyed a pre-existing receipt"

    # The new columns exist and are NULL for pre-existing rows -- absence of
    # a fence, not a fabricated one, for history that predates fencing.
    assignment_row = db.connection.execute(
        "SELECT current_execution_attempt FROM assignments WHERE id = 'asg_legacy'"
    ).fetchone()
    assert assignment_row["current_execution_attempt"] is None
    message_row = db.connection.execute(
        "SELECT fencing_token FROM messages WHERE id = 'msg_legacy'"
    ).fetchone()
    assert message_row["fencing_token"] is None

    # The message's pre-existing claim state (predating fencing tokens
    # entirely) is untouched -- migration 13 adds a column, it does not
    # rewrite existing rows' other columns.
    assert message_row is not None
    claim_row = db.connection.execute(
        "SELECT state, claim_owner, claim_expires_at FROM messages WHERE id = 'msg_legacy'"
    ).fetchone()
    assert claim_row["state"] == "CLAIMED"
    assert claim_row["claim_owner"] == "operator-course"

    # The new tables exist and are queryable, empty until something acquires
    # a lease or an execution attempt.
    assert db.connection.execute("SELECT COUNT(*) AS c FROM actor_leases").fetchone()["c"] == 0
    assert (
        db.connection.execute("SELECT COUNT(*) AS c FROM execution_attempts").fetchone()["c"] == 0
    )
    assert db.connection.execute("SELECT COUNT(*) AS c FROM lease_tokens").fetchone()["c"] == 0


def test_migration_13_is_idempotently_recognized_after_success(tmp_path: Path) -> None:
    """Reopening a database that already has migration 13 applied does not
    re-run it -- the same no-op-on-reopen property every prior migration has."""
    path = tmp_path / "unit7.db"
    _build_unit7_shaped_database(path)
    first = Database(path)
    stamps_first = first.connection.execute(
        "SELECT version, applied_at FROM schema_migrations WHERE version = 13"
    ).fetchall()
    assert len(stamps_first) == 1

    second = Database(path)
    stamps_second = second.connection.execute(
        "SELECT version, applied_at FROM schema_migrations WHERE version = 13"
    ).fetchall()
    assert [tuple(row) for row in stamps_first] == [tuple(row) for row in stamps_second]

    # Real operational work through the fencing tables after a reopen proves
    # the schema is genuinely usable, not merely present.
    from sovereign_agent import fencing

    lease = fencing.acquire_actor_lease(second, "operator-course", "proc_test")
    assert lease.fencing_token >= 1


def test_migration_13_rolls_back_completely_on_a_simulated_failure(tmp_path: Path) -> None:
    """A migration 13 that cannot complete must leave NEITHER a stamped
    version 13 NOR any partially-created fencing table behind -- the same
    fail-closed, all-or-nothing property `test_a_failed_migration_rolls_
    back_schema_and_stamp` already proves for the general mechanism, applied
    here specifically to Unit 8's own migration and a populated Unit 7
    database, so the two are proven together rather than the general
    mechanism being trusted to cover a specific migration by extrapolation."""
    path = tmp_path / "unit7.db"
    _build_unit7_shaped_database(path)

    import sovereign_agent.database as database_module

    broken_migration_13 = database_module.MIGRATION_13 + "\nSELECT this_is_not_valid_sql_syntax;"
    broken_migrations = tuple(
        (13, broken_migration_13) if version == 13 else (version, script)
        for version, script in database_module.MIGRATIONS
    )
    with patch.object(database_module, "MIGRATIONS", broken_migrations):
        with pytest.raises(sqlite3.OperationalError):
            Database(path)

    inspector = sqlite3.connect(path)
    try:
        stamped = [
            int(row[0]) for row in inspector.execute("SELECT version FROM schema_migrations")
        ]
        assert 13 not in stamped, "a failed migration was stamped as applied"
        table_names = {
            row[0]
            for row in inspector.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "actor_leases" not in table_names, (
            "a partially-applied migration left a table behind"
        )
        assert "execution_attempts" not in table_names, (
            "a partially-applied migration left a table behind"
        )
        # The pre-existing operational record from the populated Unit 7
        # database must still be there, completely untouched by the failure.
        assert (
            inspector.execute(
                "SELECT COUNT(*) FROM assignments WHERE id = 'asg_legacy'"
            ).fetchone()[0]
            == 1
        )
        columns = {row[1] for row in inspector.execute("PRAGMA table_info(messages)")}
        assert "fencing_token" not in columns, (
            "a partially-applied ALTER TABLE survived the rollback"
        )
    finally:
        inspector.close()

    # The database is still usable at its pre-13 state -- a fresh open
    # retries migration 13 (with the real, unbroken script this time) and
    # succeeds, rather than being permanently wedged by the earlier failure.
    recovered = Database(path)
    assert 13 in recovered.applied_versions()
    assert (
        recovered.connection.execute(
            "SELECT COUNT(*) AS c FROM assignments WHERE id = 'asg_legacy'"
        ).fetchone()["c"]
        == 1
    )


# === Migration 14 (Principal ruling on PR #31: bind execution attempts to =
# === the actor lease live at acquisition time) =============================


def test_migration_14_upgrade_from_a_database_already_at_migration_13_preserves_a_live_attempt(
    tmp_path: Path,
) -> None:
    """The REAL regression this migration exists to fix, reproduced exactly:
    a database that already has migration 13 applied in its shipped shape
    (execution_attempts with no actor_lease_fencing_token column at all --
    not merely NULL, the column itself did not exist) must upgrade cleanly
    under the current code, preserving a genuinely LIVE execution_attempts
    row rather than raising `sqlite3.OperationalError: table
    execution_attempts has no column named actor_lease_fencing_token`, which
    is exactly what happened live against a real local `make verify` demo
    database when migration 13 was first (incorrectly) amended in place
    instead of adding this migration."""
    import sovereign_agent.database as database_module

    path = tmp_path / "at13.db"
    connection = sqlite3.connect(path)
    for version, script in database_module.MIGRATIONS:
        if version > 13:
            break
        for statement in database_module._split_statements(script):  # noqa: SLF001
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
    connection.execute("INSERT INTO actors(id, record) VALUES ('operator-course', '{}')")
    connection.execute("INSERT INTO outcomes(id, record) VALUES ('out', '{}')")
    connection.execute("INSERT INTO sows(id, outcome_id, record) VALUES ('sow', 'out', '{}')")
    live_record = json.dumps({"id": "asg_live", "state": "RUNNING"})
    connection.execute(
        "INSERT INTO assignments(id, sow_id, actor_id, record, current_execution_attempt) "
        "VALUES (?, ?, ?, ?, ?)",
        ("asg_live", "sow", "operator-course", live_record, "att_live"),
    )
    connection.execute(
        "INSERT INTO execution_attempts(id, assignment_id, actor_id, process_identity, "
        "fencing_token, acquired_at, expires_at, status) VALUES "
        "('att_live', 'asg_live', 'operator-course', 'proc_legacy', 1, "
        "'2026-01-01T00:00:00+00:00', '2026-01-01T00:15:00+00:00', 'ACTIVE')"
    )
    connection.commit()
    connection.close()

    db = Database(path)
    assert db.applied_versions() == {version for version, _ in MIGRATIONS}
    assert 14 in db.applied_versions()

    row = db.connection.execute(
        "SELECT actor_lease_fencing_token, status FROM execution_attempts WHERE id = 'att_live'"
    ).fetchone()
    assert row is not None, "the upgrade destroyed a pre-existing execution attempt"
    assert row["actor_lease_fencing_token"] is None, (
        "a pre-migration-14 row has no real binding to backfill -- NULL, not a fabricated one"
    )
    assert row["status"] == "ACTIVE"

    # The row is still usable through the current application code: fencing.
    # py's own NULL-tolerant read (fencing._NO_ACTOR_LEASE_BINDING) must not
    # crash reading it back.
    from sovereign_agent import fencing

    attempt = fencing.current_execution_attempt(db, "asg_live")
    assert attempt is not None
    assert attempt.actor_lease_fencing_token == fencing._NO_ACTOR_LEASE_BINDING  # noqa: SLF001


def test_migration_14_is_idempotently_recognized_after_success(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    first = Database(path)
    assert 14 in first.applied_versions()
    stamps_first = first.connection.execute(
        "SELECT applied_at FROM schema_migrations WHERE version = 14"
    ).fetchall()

    second = Database(path)
    stamps_second = second.connection.execute(
        "SELECT applied_at FROM schema_migrations WHERE version = 14"
    ).fetchall()
    assert [tuple(row) for row in stamps_first] == [tuple(row) for row in stamps_second]

    columns = {row[1] for row in second.connection.execute("PRAGMA table_info(execution_attempts)")}
    assert "actor_lease_fencing_token" in columns


def test_migration_14_rolls_back_completely_on_a_simulated_failure(tmp_path: Path) -> None:
    """Same fail-closed, all-or-nothing property as migration 13's own
    rollback test, applied to migration 14: a broken migration 14 must not
    leave a stamped version 14, must not leave a partially-applied ALTER
    TABLE column, and must not disturb the pre-existing data."""
    import sovereign_agent.database as database_module

    path = tmp_path / "unit7.db"
    _build_unit7_shaped_database(path)

    broken_migration_14 = database_module.MIGRATION_14 + "\nSELECT this_is_not_valid_sql_syntax;"
    broken_migrations = tuple(
        (14, broken_migration_14) if version == 14 else (version, script)
        for version, script in database_module.MIGRATIONS
    )
    with patch.object(database_module, "MIGRATIONS", broken_migrations):
        with pytest.raises(sqlite3.OperationalError):
            Database(path)

    inspector = sqlite3.connect(path)
    try:
        stamped = [
            int(row[0]) for row in inspector.execute("SELECT version FROM schema_migrations")
        ]
        assert 13 in stamped, "migration 13 should still have succeeded"
        assert 14 not in stamped, "a failed migration was stamped as applied"
        columns = {row[1] for row in inspector.execute("PRAGMA table_info(execution_attempts)")}
        assert "actor_lease_fencing_token" not in columns, (
            "a partially-applied ALTER TABLE survived the rollback"
        )
        assert (
            inspector.execute(
                "SELECT COUNT(*) FROM assignments WHERE id = 'asg_legacy'"
            ).fetchone()[0]
            == 1
        )
    finally:
        inspector.close()

    recovered = Database(path)
    assert 14 in recovered.applied_versions()
    assert (
        recovered.connection.execute(
            "SELECT COUNT(*) AS c FROM assignments WHERE id = 'asg_legacy'"
        ).fetchone()["c"]
        == 1
    )


# === Migration 15 (Unit 9: Pulse origin attribution) =======================


def _build_unit8_shaped_database(path: Path) -> None:
    """Migrations 1-14 by hand, with a real pre-Unit-9 SOW and assignment on
    disk -- the shape a real Unit-8-era organization.db would have the
    moment before migration 15 first runs against it."""
    import sovereign_agent.database as database_module

    connection = sqlite3.connect(path)
    for version, script in database_module.MIGRATIONS:
        if version > 14:
            break
        for statement in database_module._split_statements(script):  # noqa: SLF001
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
    connection.execute("INSERT INTO actors(id, record) VALUES ('operator-course', '{}')")
    connection.execute("INSERT INTO outcomes(id, record) VALUES ('out_legacy', '{}')")
    connection.execute(
        "INSERT INTO sows(id, outcome_id, record) VALUES ('sow_legacy', 'out_legacy', ?)",
        (json.dumps({"id": "sow_legacy", "created_at": "2026-01-01T00:00:00+00:00"}),),
    )
    connection.execute(
        "INSERT INTO assignments(id, sow_id, actor_id, record) "
        "VALUES ('asg_legacy', 'sow_legacy', 'operator-course', "
        '\'{"id": "asg_legacy", "state": "COMPLETED"}\')'
    )
    connection.commit()
    connection.close()


def test_migration_15_fresh_install_creates_the_pulse_tables(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    db = Database(path)
    assert 15 in db.applied_versions()
    tables = {
        row["name"]
        for row in db.connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert "pulse_wake_decisions" in tables
    assert "pulse_origins" in tables


def test_migration_15_upgrade_from_a_populated_unit8_database_preserves_every_record(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unit8.db"
    _build_unit8_shaped_database(path)

    db = Database(path)
    assert db.applied_versions() == {version for version, _ in MIGRATIONS}
    assert (
        db.connection.execute("SELECT COUNT(*) AS c FROM sows WHERE id = 'sow_legacy'").fetchone()[
            "c"
        ]
        == 1
    ), "the upgrade destroyed a pre-existing SOW"
    assert (
        db.connection.execute(
            "SELECT COUNT(*) AS c FROM assignments WHERE id = 'asg_legacy'"
        ).fetchone()["c"]
        == 1
    ), "the upgrade destroyed a pre-existing assignment"


def test_migration_15_backfills_an_explicit_manual_origin_for_every_pre_existing_sow(
    tmp_path: Path,
) -> None:
    """Preservation and explicit manual-origin backfill: a SOW that existed
    before Pulse was ever built gets its own 'manual' row, not silence."""
    path = tmp_path / "unit8.db"
    _build_unit8_shaped_database(path)

    db = Database(path)
    row = db.connection.execute(
        "SELECT origin_kind, assignment_id, created_at FROM pulse_origins "
        "WHERE sow_id = 'sow_legacy'"
    ).fetchone()
    assert row is not None, "no origin row was backfilled for a pre-existing SOW"
    assert row["origin_kind"] == "manual"
    assert row["assignment_id"] == "asg_legacy"
    assert row["created_at"] == "2026-01-01T00:00:00+00:00"


def test_migration_15_backfill_leaves_assignment_id_null_when_a_sow_has_no_single_assignment(
    tmp_path: Path,
) -> None:
    """A SOW with zero (or more than one) assignment cannot be honestly bound
    to exactly one -- NULL there, never a guess, while origin_kind stays
    explicitly 'manual' regardless."""
    import sovereign_agent.database as database_module

    path = tmp_path / "unit8.db"
    connection = sqlite3.connect(path)
    for version, script in database_module.MIGRATIONS:
        if version > 14:
            break
        for statement in database_module._split_statements(script):  # noqa: SLF001
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
    connection.execute("INSERT INTO outcomes(id, record) VALUES ('out_legacy', '{}')")
    connection.execute(
        "INSERT INTO sows(id, outcome_id, record) VALUES ('sow_orphan', 'out_legacy', '{}')"
    )
    connection.commit()
    connection.close()

    db = Database(path)
    row = db.connection.execute(
        "SELECT origin_kind, assignment_id FROM pulse_origins WHERE sow_id = 'sow_orphan'"
    ).fetchone()
    assert row is not None
    assert row["origin_kind"] == "manual"
    assert row["assignment_id"] is None


def test_migration_15_rolls_back_on_malformed_unattributable_sow_data(tmp_path: Path) -> None:
    """Fail closed, without stamping the migration, when a pre-existing SOW's
    record cannot be honestly read -- rather than silently fabricating a
    created_at or skipping the row."""
    import sovereign_agent.database as database_module

    path = tmp_path / "unit8.db"
    connection = sqlite3.connect(path)
    for version, script in database_module.MIGRATIONS:
        if version > 14:
            break
        for statement in database_module._split_statements(script):  # noqa: SLF001
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
    connection.execute("INSERT INTO outcomes(id, record) VALUES ('out_legacy', '{}')")
    connection.execute(
        "INSERT INTO sows(id, outcome_id, record) VALUES "
        "('sow_bad', 'out_legacy', 'not valid json')"
    )
    connection.commit()
    connection.close()

    with pytest.raises(sqlite3.OperationalError):
        Database(path)

    inspector = sqlite3.connect(path)
    try:
        stamped = [
            int(row[0]) for row in inspector.execute("SELECT version FROM schema_migrations")
        ]
        assert 14 in stamped
        assert 15 not in stamped, "a failed migration was stamped as applied"
        table_names = {
            row[0]
            for row in inspector.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "pulse_origins" not in table_names, (
            "a partially-applied migration left a table behind"
        )
        assert (
            inspector.execute("SELECT COUNT(*) FROM sows WHERE id = 'sow_bad'").fetchone()[0] == 1
        ), "the migration's own rollback destroyed the pre-existing (malformed) row"
    finally:
        inspector.close()

    # A hand-repaired row lets a fresh open succeed and stamp 15 normally.
    repair = sqlite3.connect(path)
    repair.execute(
        "UPDATE sows SET record = ? WHERE id = 'sow_bad'",
        (json.dumps({"id": "sow_bad", "created_at": "2026-01-01T00:00:00+00:00"}),),
    )
    repair.commit()
    repair.close()
    recovered = Database(path)
    assert 15 in recovered.applied_versions()


def test_migration_15_rolls_back_completely_on_a_simulated_sql_failure(tmp_path: Path) -> None:
    import sovereign_agent.database as database_module

    path = tmp_path / "unit8.db"
    _build_unit8_shaped_database(path)

    broken_migration_15 = database_module.MIGRATION_15 + "\nSELECT this_is_not_valid_sql_syntax;"
    broken_migrations = tuple(
        (15, broken_migration_15) if version == 15 else (version, script)
        for version, script in database_module.MIGRATIONS
    )
    with patch.object(database_module, "MIGRATIONS", broken_migrations):
        with pytest.raises(sqlite3.OperationalError):
            Database(path)

    inspector = sqlite3.connect(path)
    try:
        stamped = [
            int(row[0]) for row in inspector.execute("SELECT version FROM schema_migrations")
        ]
        assert 15 not in stamped
        table_names = {
            row[0]
            for row in inspector.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "pulse_wake_decisions" not in table_names
        assert (
            inspector.execute("SELECT COUNT(*) FROM sows WHERE id = 'sow_legacy'").fetchone()[0]
            == 1
        )
    finally:
        inspector.close()

    recovered = Database(path)
    assert 15 in recovered.applied_versions()


def test_migration_15_foreign_key_uniqueness_and_append_only_enforcement(tmp_path: Path) -> None:
    from reference_organizations.store import record_sale, seed
    from reference_organizations.store.pulse_gate import store_wake_gate
    from sovereign_agent.organization import Organization
    from sovereign_agent.pulse import run_pulse_once

    org = Organization.init(tmp_path)
    seed(org.db)
    outcome = org.create_outcome(
        "t", "d", ["inventory_at_or_above_reorder_point"], "principal-human", "SKU-TEA"
    )
    org.activate(outcome.id, "master-course")
    signal = record_sale(org.db, "SKU-TEA", 2, 400)
    source_event_id = org.db.connection.execute(
        "SELECT id FROM events WHERE kind = 'sale.committed'"
    ).fetchone()["id"]
    db = org.db

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        db.connection.execute(
            "INSERT INTO pulse_wake_decisions(id, source_signal_id, source_event_id, "
            "subject, decided_at) VALUES ('pdec_x', 'sig_missing', 'evt_missing', "
            "'SKU-TEA', datetime('now'))"
        )

    # A rejected sqlite statement still leaves its implicit transaction open.
    # Close this deliberate invalid probe before entering the production boundary.
    db.connection.rollback()

    # A real, production-created decision and origin row, through the same
    # mechanism the rest of the proof matrix uses -- gives this test a real
    # row to enforce append-only and duplicate-prevention against.
    report = run_pulse_once(org, store_wake_gate)
    assert len(report.created) == 1

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        db.connection.execute(
            "INSERT INTO pulse_wake_decisions(id, source_signal_id, source_event_id, "
            "subject, decided_at) VALUES ('pdec_dup', ?, ?, 'SKU-TEA', datetime('now'))",
            (signal.id, source_event_id),
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.connection.execute(
            "DELETE FROM pulse_wake_decisions WHERE source_signal_id = ?", (signal.id,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.connection.execute("UPDATE pulse_origins SET origin_kind = 'manual'")


def test_migration_15_is_idempotently_recognized_after_success(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    first = Database(path)
    stamps_first = first.connection.execute(
        "SELECT applied_at FROM schema_migrations WHERE version = 15"
    ).fetchall()

    second = Database(path)
    stamps_second = second.connection.execute(
        "SELECT applied_at FROM schema_migrations WHERE version = 15"
    ).fetchall()
    assert [tuple(row) for row in stamps_first] == [tuple(row) for row in stamps_second]
