"""SQLite operational ledger: WAL, foreign keys, forward-only migrations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sovereign_agent.assistant_schema import SCHEMA as MIGRATION_19
from sovereign_agent.assistant_schema import SCHEMA_20 as MIGRATION_20
from sovereign_agent.assistant_schema import SCHEMA_21 as MIGRATION_21
from sovereign_agent.assistant_schema import SCHEMA_22 as MIGRATION_22
from sovereign_agent.assistant_schema import SCHEMA_23 as MIGRATION_23
from sovereign_agent.assistant_schema import SCHEMA_24 as MIGRATION_24

MIGRATION_1 = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes (
    id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sows (
    id TEXT PRIMARY KEY,
    outcome_id TEXT NOT NULL,
    record TEXT NOT NULL,
    FOREIGN KEY(outcome_id) REFERENCES outcomes(id)
);
CREATE TABLE IF NOT EXISTS rulings (
    id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actors (
    id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    id TEXT PRIMARY KEY,
    sow_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    record TEXT NOT NULL,
    FOREIGN KEY(sow_id) REFERENCES sows(id),
    FOREIGN KEY(actor_id) REFERENCES actors(id)
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    recipient TEXT NOT NULL,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS acceptance (
    outcome_id TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY,
    on_hand INTEGER NOT NULL,
    reserved INTEGER NOT NULL DEFAULT 0,
    reorder_point INTEGER NOT NULL,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cash_entries (
    id TEXT PRIMARY KEY,
    amount_cents INTEGER NOT NULL,
    record TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    record TEXT NOT NULL
);
"""

MIGRATION_2 = """
-- Append-only enforcement lives at the database boundary, not in Python habit.
-- Without these, `UPDATE events` and `DELETE FROM events` both succeed.
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: delete refused');
END;

-- Evidence must be bound to what it proves. Columns are indexed rather than
-- buried in the JSON record so acceptance can query bindings directly.
-- REFERENCES on ALTER ADD COLUMN IS enforced by SQLite: a fabricated
-- outcome id is refused by the database, not merely by Python.
ALTER TABLE evidence ADD COLUMN outcome_id TEXT REFERENCES outcomes(id);
ALTER TABLE evidence ADD COLUMN check_id TEXT NOT NULL DEFAULT '';
ALTER TABLE evidence ADD COLUMN success INTEGER NOT NULL DEFAULT 0;
-- Digest of the exact inputs the check read. An event counter cannot detect a
-- silent UPDATE to inventory, so staleness is measured over the read state itself.
ALTER TABLE evidence ADD COLUMN state_digest TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS evidence_binding
    ON evidence(outcome_id, check_id);
"""

MIGRATION_3 = """
-- `recursive_triggers` is a PER-CONNECTION pragma, not a property of the schema.
-- The BEFORE DELETE guard therefore only stopped `INSERT OR REPLACE` on
-- connections the application itself opened. Anyone using a plain `sqlite3`
-- shell -- including a learner following Chapter 1 -- could silently overwrite
-- an event and leave the row count unchanged.
--
-- This guard needs no pragma: it refuses an INSERT whose id already exists, so
-- append-only holds from ANY client. Enforcement now matches the claim.
CREATE TRIGGER IF NOT EXISTS events_no_replace
BEFORE INSERT ON events
WHEN EXISTS (SELECT 1 FROM events WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'events are append-only: replace refused');
END;
"""


MIGRATION_4 = """
-- A preflight scan of the event log is not an idempotency key: two callers can
-- both pass the scan before either writes, and both then order stock. The
-- database has to be the one saying "this already happened".
CREATE TABLE IF NOT EXISTS effect_keys (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


MIGRATION_5 = """
-- Claiming a lease by reading a JSON blob, deciding in Python, then writing the
-- blob back is a read-then-write race: two workers both read NEW and both win.
-- A compare-and-set needs the state in a column the UPDATE can test.
ALTER TABLE messages ADD COLUMN state TEXT NOT NULL DEFAULT 'NEW';
ALTER TABLE messages ADD COLUMN claim_owner TEXT;
ALTER TABLE messages ADD COLUMN claim_expires_at TEXT;
UPDATE messages SET
    state = COALESCE(json_extract(record, '$.state'), 'NEW'),
    claim_owner = json_extract(record, '$.claim_owner'),
    claim_expires_at = json_extract(record, '$.claim_expires_at');
"""


MIGRATION_6 = """
-- A review that leaves no record is a claim nobody can check later. Acceptance
-- could not consult reviews because there was nothing durable to consult.
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    sow_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL,
    reviewer_actor_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    record TEXT NOT NULL,
    FOREIGN KEY(sow_id) REFERENCES sows(id),
    FOREIGN KEY(outcome_id) REFERENCES outcomes(id)
);
CREATE INDEX IF NOT EXISTS reviews_by_outcome ON reviews(outcome_id);
-- Receipts must name the execution they describe, or they cannot be tied to it.
ALTER TABLE receipts ADD COLUMN assignment_id TEXT;
ALTER TABLE receipts ADD COLUMN status TEXT NOT NULL DEFAULT '';
"""


MIGRATION_7 = """
-- effect_keys held ONE concatenated string while the code called it a key on
-- (assignment, sku). Structured columns with a composite constraint make the
-- schema say what the docstring claimed.
CREATE TABLE IF NOT EXISTS effects (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(assignment_id, kind, subject),
    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
);

-- A verification is a BATCH of evidence produced by one run of the checks.
-- Without it, review binds to "whatever evidence existed" and acceptance uses
-- "whatever evidence exists now", and nothing forces those to be the same set.
CREATE TABLE IF NOT EXISTS verifications (
    id TEXT PRIMARY KEY,
    outcome_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    aggregate_digest TEXT NOT NULL,
    passed INTEGER NOT NULL,
    record TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(outcome_id) REFERENCES outcomes(id)
);
CREATE INDEX IF NOT EXISTS verifications_by_outcome ON verifications(outcome_id);

ALTER TABLE evidence ADD COLUMN verification_id TEXT REFERENCES verifications(id);
ALTER TABLE reviews ADD COLUMN verification_id TEXT REFERENCES verifications(id);
"""


MIGRATION_8 = """
-- Sparring's unprompted find: Receipt.assignment_id defaulted to "",
-- _latest_assignment_id returned "", and this column was nullable -- "the
-- performer who never worked" in a new costume. It refused every way Sparring
-- pushed it, but only via guards three layers from the default. SQLite cannot
-- add a NOT NULL constraint in place, so this rebuilds the table.
CREATE TABLE receipts_v2 (
    id TEXT PRIMARY KEY,
    record TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    status TEXT NOT NULL,
    CHECK (assignment_id <> '')
);
INSERT INTO receipts_v2(id, record, assignment_id, status)
    SELECT id, record, COALESCE(NULLIF(assignment_id, ''), 'asg_unattributed_legacy'),
           COALESCE(status, '')
    FROM receipts;
DROP TABLE receipts;
ALTER TABLE receipts_v2 RENAME TO receipts;
CREATE INDEX IF NOT EXISTS receipts_by_assignment ON receipts(assignment_id);
"""


MIGRATION_9 = """
-- The effect edge existed but could only be followed through the JSON payload,
-- so acceptance never followed it: the authorization graph and the acceptance
-- graph met at the SUBJECT (any two outcomes about one SKU shared effects)
-- rather than at the execution. A structured FK makes the edge queryable.
ALTER TABLE effects ADD COLUMN outcome_id TEXT REFERENCES outcomes(id);
UPDATE effects SET outcome_id = json_extract(payload, '$.outcome_id')
    WHERE outcome_id IS NULL;
CREATE INDEX IF NOT EXISTS effects_by_outcome ON effects(outcome_id, assignment_id);
"""


MIGRATION_10 = """
-- The effect edge is what ties an execution to the change it made. Leaving it
-- nullable left the crucial edge optional. SQLite cannot add NOT NULL in place,
-- so the table is rebuilt.
CREATE TABLE effects_v2 (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    outcome_id TEXT NOT NULL,
    UNIQUE(assignment_id, kind, subject),
    FOREIGN KEY(assignment_id) REFERENCES assignments(id),
    FOREIGN KEY(outcome_id) REFERENCES outcomes(id),
    CHECK (outcome_id <> '')
);
-- NO `WHERE ... IS NOT NULL` filter. An earlier version had one, so that the
-- NOT NULL rebuild would always succeed -- and it dropped every legacy row it
-- could not attribute before DROPping the old table, destroying an operational
-- record from an append-only ledger while reporting success.
--
-- Fail closed instead: an unattributable row makes this INSERT violate NOT NULL,
-- the whole migration rolls back inside its BEGIN IMMEDIATE, version 10 is not
-- stamped, and the original table is still there to be repaired by hand. A
-- migration that cannot preserve the ledger must refuse to run, not quietly
-- decide which history was worth keeping.
INSERT INTO effects_v2(id, assignment_id, kind, subject, payload, created_at, outcome_id)
    SELECT id, assignment_id, kind, subject, payload, created_at,
           COALESCE(NULLIF(outcome_id, ''), json_extract(payload, '$.outcome_id'))
    FROM effects;
DROP TABLE effects;
ALTER TABLE effects_v2 RENAME TO effects;
CREATE INDEX IF NOT EXISTS effects_by_outcome ON effects(outcome_id, assignment_id);
"""


MIGRATION_11 = """
-- A verification must name the SOW it is about. Without it, verification
-- selected a SOW implicitly by row order and the caller could not say which
-- work was being verified -- so with two completed SOWs one became permanently
-- unreviewable, and which one was arbitrary.
ALTER TABLE verifications ADD COLUMN sow_id TEXT REFERENCES sows(id);
CREATE INDEX IF NOT EXISTS verifications_by_sow ON verifications(sow_id);
"""


# Tables whose rows must never be rewritten once written. This is MUTATION
# SAFETY, not authentication: the guards stop ordinary tools and honest mistakes
# from altering history. They do not stop an arbitrary database writer, who can
# still append.
#
# It is a maintained LIST, not a discovery mechanism. Adding a proof-bearing
# table means adding it here AND shipping a new migration -- editing an
# already-stamped migration would guard fresh installs and silently skip every
# upgraded database.
#
# `receipts` is deliberately absent: `put_serialized` rewrites a receipt in
# place while an assignment runs. Acceptance still treats it as proof, and
# guards that instead by requiring the canonical record and the indexed columns
# to agree (`Organization._trusted_receipt`).
#
# `active_pilot` is also deliberately absent from this list: it is a
# singleton with no per-row `id` column (its PRIMARY KEY is always the
# literal 1), so it does not fit this list's own three-trigger contract
# (`{table}_no_replace` keys off `NEW.id`, which this table has no
# equivalent of). It carries its own update/delete guards directly in
# migration 16 instead -- replace-safety comes from its `pilot_id` UNIQUE
# constraint, not from a `_no_replace` trigger.
APPEND_ONLY_TABLES: tuple[str, ...] = (
    "events",
    "effects",
    "verifications",
    "reviews",
    "evidence",
    "pulse_wake_decisions",
    "pulse_origins",
    "pilots",
)


def _append_only_triggers(table: str) -> str:
    """The same three guards, for one proof-bearing table."""
    return f"""
CREATE TRIGGER IF NOT EXISTS {table}_no_update
BEFORE UPDATE ON {table}
BEGIN
    SELECT RAISE(ABORT, '{table} are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS {table}_no_delete
BEFORE DELETE ON {table}
BEGIN
    SELECT RAISE(ABORT, '{table} are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS {table}_no_replace
BEFORE INSERT ON {table}
WHEN EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, '{table} are append-only: replace refused');
END;
"""


# Migration 12 as it SHIPPED, byte for byte. Not generated.
#
# The first attempt froze the table LIST and left the body flowing through the
# shared `_append_only_triggers()` helper -- so editing that helper still
# rewrote the bytes of an already-applied migration, which is the exact failure
# the freeze was built to prevent. I froze membership and called it content.
# Proven by mutation: a harmless comment in the helper changed MIGRATION_12's
# digest while the "frozen" test passed.
#
# An applied migration is history. `_append_only_triggers()` stays, for building
# FUTURE migrations only; version 12 no longer depends on it, and its digest is
# pinned by `test_migration_12_content_is_frozen`.
MIGRATION_12_TABLES: tuple[str, ...] = ("effects", "verifications", "reviews", "evidence")

MIGRATION_12_SHA256 = "cb5483b35e4ef78d761381dc9a1ac940c59b574f7716c17c84bf9b6c89392a5e"

MIGRATION_12 = """
CREATE TRIGGER IF NOT EXISTS effects_no_update
BEFORE UPDATE ON effects
BEGIN
    SELECT RAISE(ABORT, 'effects are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS effects_no_delete
BEFORE DELETE ON effects
BEGIN
    SELECT RAISE(ABORT, 'effects are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS effects_no_replace
BEFORE INSERT ON effects
WHEN EXISTS (SELECT 1 FROM effects WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'effects are append-only: replace refused');
END;

CREATE TRIGGER IF NOT EXISTS verifications_no_update
BEFORE UPDATE ON verifications
BEGIN
    SELECT RAISE(ABORT, 'verifications are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS verifications_no_delete
BEFORE DELETE ON verifications
BEGIN
    SELECT RAISE(ABORT, 'verifications are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS verifications_no_replace
BEFORE INSERT ON verifications
WHEN EXISTS (SELECT 1 FROM verifications WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'verifications are append-only: replace refused');
END;

CREATE TRIGGER IF NOT EXISTS reviews_no_update
BEFORE UPDATE ON reviews
BEGIN
    SELECT RAISE(ABORT, 'reviews are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS reviews_no_delete
BEFORE DELETE ON reviews
BEGIN
    SELECT RAISE(ABORT, 'reviews are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS reviews_no_replace
BEFORE INSERT ON reviews
WHEN EXISTS (SELECT 1 FROM reviews WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'reviews are append-only: replace refused');
END;

CREATE TRIGGER IF NOT EXISTS evidence_no_update
BEFORE UPDATE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete
BEFORE DELETE ON evidence
BEGIN
    SELECT RAISE(ABORT, 'evidence are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS evidence_no_replace
BEFORE INSERT ON evidence
WHEN EXISTS (SELECT 1 FROM evidence WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'evidence are append-only: replace refused');
END;
"""


MIGRATION_13 = """
-- Unit 8: process-level fencing. Actor-level idempotency (Unit 4's claim())
-- and single-process bookkeeping (Unit 7's synchronous reclaim) both assumed
-- one process per actor. A supervisor that can recover after a hard kill
-- needs a durable, queryable fencing token -- not one hidden inside a JSON
-- blob a CAS statement cannot compare against in a WHERE clause.

-- The single monotonic source every fencing token in this database is drawn
-- from. AUTOINCREMENT guarantees each row's rowid is strictly greater than
-- every prior row's, even across process restarts, which is the one property
-- a fencing token must have: an old token must always compare less than a
-- fresh one, forever, with no wraparound and no reissue.
CREATE TABLE IF NOT EXISTS lease_tokens (
    token INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- One row per actor: the process currently authorized to host it. Acquiring
-- or renewing is a compare-and-set against this table, the same discipline
-- `relay.claim()` already uses -- one UPDATE (or INSERT for a first
-- acquisition) that only succeeds when no unexpired lease exists, so two
-- racing acquirers produce exactly one winner.
CREATE TABLE IF NOT EXISTS actor_leases (
    actor_id TEXT PRIMARY KEY,
    process_identity TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    renewed_at TEXT NOT NULL,
    FOREIGN KEY(actor_id) REFERENCES actors(id)
);

-- One row per attempt to run an assignment. `assignments.current_execution_
-- attempt` (below) names which row, if any, is presently authorized to
-- write that assignment's terminal state -- the fencing token the terminal
-- transaction in `run_assignment` (and the supervisor's recovery path)
-- compares against atomically before committing.
CREATE TABLE IF NOT EXISTS execution_attempts (
    id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    process_identity TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
);
CREATE INDEX IF NOT EXISTS execution_attempts_by_assignment
    ON execution_attempts(assignment_id);

-- NULL until an attempt is acquired; cleared back to NULL once the terminal
-- transaction commits (or the supervisor recovers the assignment). Reading
-- this column and comparing it to an attempt id IS the fence check -- no
-- other table needs to be consulted to know whether a given attempt may
-- still write.
ALTER TABLE assignments ADD COLUMN current_execution_attempt TEXT;

-- Mailbox completion/retry/dead-letter now verify the token bound at claim
-- time, closing F-U4-1: the same-actor expired-lease branch inside claim()
-- becomes reachable (it issues a fresh token) instead of short-circuiting
-- back to a stale, unrenewed claim.
ALTER TABLE messages ADD COLUMN fencing_token INTEGER;
"""


MIGRATION_14 = """
-- Unit 8, Principal ruling on PR #31: execution-attempt fencing alone
-- (migration 13) answered "may THIS process write THIS ONE assignment's
-- terminal state" -- keyed by assignment_id, it never asked whether the
-- process was allowed to be hosting the actor at all. Two DIFFERENT
-- assignments for the SAME actor could each acquire their own execution
-- attempt and run under two separate processes, unaffected by anything
-- migration 13 built. This column BINDS an execution attempt to the actor
-- lease that was live at the moment it was acquired, connecting the two
-- CAS mechanisms instead of leaving them independent tables that merely
-- happen to coexist.
--
-- Nullable, not NOT NULL: migration 13 already shipped (this branch's own
-- earlier commits ran `make verify` against real local databases, and
-- amending an already-applied migration in place broke every one of them
-- with a real `sqlite3.OperationalError` -- the exact failure this
-- forward-only discipline exists to prevent, caught live rather than
-- theorized). A NOT NULL rebuild (migration 8's or migration 10's own
-- pattern) is not warranted here: execution_attempts is a transient table
-- -- a row exists only while an attempt is genuinely live, cleared back out
-- by release_execution_attempt on completion or supervisor recovery -- so
-- any pre-existing row at upgrade time is, by construction, already stale
-- or about to be recovered, never a record whose absence of this new fact
-- (fencing.acquire_execution_attempt now populates it going forward) is a
-- loss worth refusing the migration over.
ALTER TABLE execution_attempts ADD COLUMN actor_lease_fencing_token INTEGER;
"""


MIGRATION_15 = """
-- Unit 9: Pulse origin attribution. Ruling 2026-08-29-unit9-pulse-is-
-- separate-from-supervisor, holding 2: "created without a human prompt"
-- must be provable in the ledger after the fact, never inferred from the
-- absence of a manual-origin row or the absence of a CLI invocation.

-- One row per source signal that has ever been evaluated to a canonical
-- firing decision. UNIQUE(source_signal_id) IS the "one canonical wake
-- decision per source signal" enforcement -- at the SQLite boundary, not a
-- preflight SELECT: two concurrent evaluators racing the same signal both
-- attempt this INSERT: one wins, one hits the UNIQUE constraint and reads
-- the winner's row back.
CREATE TABLE IF NOT EXISTS pulse_wake_decisions (
    id TEXT PRIMARY KEY,
    source_signal_id TEXT NOT NULL UNIQUE REFERENCES signals(id),
    source_event_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

-- One row per genuine pulse.* event, and per SOW/assignment it created.
-- sow_id and assignment_id are UNIQUE: a wake decision creates AT MOST one
-- initial SOW and one initial assignment, ever -- replay must resolve to
-- the same identifiers, never mint a second pair.
CREATE TABLE IF NOT EXISTS pulse_origins (
    id TEXT PRIMARY KEY,
    origin_kind TEXT NOT NULL DEFAULT 'manual',
    wake_decision_id TEXT UNIQUE REFERENCES pulse_wake_decisions(id),
    pulse_event_id TEXT UNIQUE,
    sow_id TEXT NOT NULL UNIQUE REFERENCES sows(id),
    assignment_id TEXT UNIQUE REFERENCES assignments(id),
    created_at TEXT NOT NULL,
    CHECK (
        (origin_kind = 'manual'
            AND wake_decision_id IS NULL AND pulse_event_id IS NULL)
        OR
        (origin_kind = 'pulse'
            AND wake_decision_id IS NOT NULL AND pulse_event_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS pulse_origins_by_sow ON pulse_origins(sow_id);

-- Proof-bearing: once a wake decision or an origin row exists, it is
-- history. Appended to APPEND_ONLY_TABLES's own three guards below, matching
-- the discipline every other proof-bearing table in this database already
-- uses (migration 12).
CREATE TRIGGER IF NOT EXISTS pulse_wake_decisions_no_update
BEFORE UPDATE ON pulse_wake_decisions
BEGIN
    SELECT RAISE(ABORT, 'pulse_wake_decisions are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS pulse_wake_decisions_no_delete
BEFORE DELETE ON pulse_wake_decisions
BEGIN
    SELECT RAISE(ABORT, 'pulse_wake_decisions are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS pulse_wake_decisions_no_replace
BEFORE INSERT ON pulse_wake_decisions
WHEN EXISTS (SELECT 1 FROM pulse_wake_decisions WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'pulse_wake_decisions are append-only: replace refused');
END;

CREATE TRIGGER IF NOT EXISTS pulse_origins_no_update
BEFORE UPDATE ON pulse_origins
BEGIN
    SELECT RAISE(ABORT, 'pulse_origins are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS pulse_origins_no_delete
BEFORE DELETE ON pulse_origins
BEGIN
    SELECT RAISE(ABORT, 'pulse_origins are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS pulse_origins_no_replace
BEFORE INSERT ON pulse_origins
WHEN EXISTS (SELECT 1 FROM pulse_origins WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'pulse_origins are append-only: replace refused');
END;

-- Every SOW created before this unit is explicit manual-origin history, not
-- an absence. "No Pulse-origin row exists" must never be the definition of
-- manual (the governing ruling's own words) -- so every pre-existing SOW
-- gets its own explicit 'manual' row here, at migration time, rather than
-- leaving manual-vs-unattributed as two things this schema cannot tell
-- apart. assignment_id is backfilled when exactly one assignment exists for
-- the SOW; a SOW with zero or more than one assignment gets NULL there
-- (still explicitly 'manual' on origin_kind, which is the fact this
-- migration must not lose) rather than guessing which assignment to bind.
INSERT INTO pulse_origins(id, origin_kind, sow_id, assignment_id, created_at)
SELECT
    'porg_manual_' || sows.id,
    'manual',
    sows.id,
    (SELECT a.id FROM assignments a WHERE a.sow_id = sows.id
     GROUP BY a.sow_id HAVING COUNT(*) = 1),
    COALESCE(sows.record ->> '$.created_at', datetime('now'))
FROM sows;
"""


MIGRATION_16 = """
-- Unit 11: the pilot-start mechanism (governing ruling Holding 1). A
-- first-class, queryable record -- structured columns, not unindexed JSON --
-- matching the discipline migration 15 already established for Pulse
-- attribution. pilot_id is the CAS key: a plain INSERT is the idempotency
-- check (UNIQUE, not a preflight SELECT), the same discipline
-- create_pulse_work's own pulse_wake_decisions INSERT already uses.
CREATE TABLE IF NOT EXISTS pilots (
    pilot_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    store_org_id TEXT NOT NULL,
    pilot_profile_id TEXT NOT NULL,
    evidence_namespace TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- A singleton slot naming the one pilot presently active, if any.
-- fail-closed on an INCOMPATIBLE concurrent start: the slot's own PRIMARY
-- KEY (always 1) makes a second, DIFFERENT pilot_id's INSERT collide here
-- exactly like pulse_wake_decisions.source_signal_id already does for
-- signals -- refused at the SQLite boundary, not by a preflight SELECT a
-- race could slip past. A REPLAY of the SAME pilot_id never reaches this
-- table a second time (see start_pilot: the plain INSERT into `pilots`
-- itself is what the replay collides against first).
CREATE TABLE IF NOT EXISTS active_pilot (
    slot_id INTEGER PRIMARY KEY CHECK (slot_id = 1),
    pilot_id TEXT NOT NULL UNIQUE REFERENCES pilots(pilot_id)
);

CREATE TRIGGER IF NOT EXISTS pilots_no_update
BEFORE UPDATE ON pilots
BEGIN
    SELECT RAISE(ABORT, 'pilots are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS pilots_no_delete
BEFORE DELETE ON pilots
BEGIN
    SELECT RAISE(ABORT, 'pilots are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS pilots_no_replace
BEFORE INSERT ON pilots
WHEN EXISTS (SELECT 1 FROM pilots WHERE pilot_id = NEW.pilot_id)
BEGIN
    SELECT RAISE(ABORT, 'pilots are append-only: replace refused');
END;

-- active_pilot holds exactly one row, ever, for the life of a database: the
-- singleton PRIMARY KEY (slot_id = 1) is what a concurrent, INCOMPATIBLE
-- start collides against. Guarded the same append-only way regardless --
-- defense in depth, matching this project's own standing discipline that a
-- proof-bearing row is never rewritten once written, singleton or not.
CREATE TRIGGER IF NOT EXISTS active_pilot_no_update
BEFORE UPDATE ON active_pilot
BEGIN
    SELECT RAISE(ABORT, 'active_pilot is append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS active_pilot_no_delete
BEFORE DELETE ON active_pilot
BEGIN
    SELECT RAISE(ABORT, 'active_pilot is append-only: delete refused');
END;
"""


MIGRATION_17 = """
-- Heartbeat: durable liveness records (see heartbeat.py). DELIBERATELY a
-- separate table, never rows in `events`: the ledger records governed WORK,
-- and a liveness tick written there would let "the process is running"
-- masquerade as "something happened". Presence is not behavior.
CREATE TABLE IF NOT EXISTS heartbeats (
    beat_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Append-only like every proof-bearing table here: liveness history is a
-- record, not a mutable "last seen" field an eager writer could rewrite.
CREATE TRIGGER IF NOT EXISTS heartbeats_no_update
BEFORE UPDATE ON heartbeats
BEGIN
    SELECT RAISE(ABORT, 'heartbeats are append-only: update refused');
END;
CREATE TRIGGER IF NOT EXISTS heartbeats_no_delete
BEFORE DELETE ON heartbeats
BEGIN
    SELECT RAISE(ABORT, 'heartbeats are append-only: delete refused');
END;
CREATE TRIGGER IF NOT EXISTS heartbeats_no_replace
BEFORE INSERT ON heartbeats
WHEN EXISTS (SELECT 1 FROM heartbeats WHERE beat_id = NEW.beat_id)
BEGIN
    SELECT RAISE(ABORT, 'heartbeats are append-only: replace refused');
END;
"""


MIGRATION_18 = """
-- Advanced teaching mechanisms. These tables keep durable state in the same
-- inspectable SQLite file as the rest of the organization; no daemon, broker,
-- vector database, or scheduler service is hidden behind the lesson.
CREATE TABLE automations (
    id TEXT PRIMARY KEY, interval_seconds INTEGER NOT NULL CHECK(interval_seconds >= 1),
    next_run_at TEXT NOT NULL, condition_state TEXT NOT NULL DEFAULT '{}',
    payload TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
    failure_count INTEGER NOT NULL DEFAULT 0, max_failures INTEGER NOT NULL DEFAULT 3
);
CREATE TABLE automation_runs (
    id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id),
    due_at TEXT NOT NULL, message TEXT NOT NULL, status TEXT NOT NULL,
    error TEXT, created_at TEXT NOT NULL, UNIQUE(automation_id, due_at)
);
CREATE TABLE transcript_messages (
    session_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL,
    content TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(session_id, seq)
);
CREATE TABLE context_compactions (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, through_seq INTEGER NOT NULL,
    summary TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(session_id, through_seq)
);
CREATE TABLE host_instances (
    id TEXT PRIMARY KEY, lease_expires_at TEXT NOT NULL
);
CREATE TABLE session_claims (
    session_id TEXT PRIMARY KEY, host_id TEXT NOT NULL REFERENCES host_instances(id),
    incarnation INTEGER NOT NULL, lease_expires_at TEXT NOT NULL
);
CREATE TABLE session_completions (
    session_id TEXT PRIMARY KEY, host_id TEXT NOT NULL, incarnation INTEGER NOT NULL,
    result TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE delivery_attempts (
    delivery_id TEXT PRIMARY KEY, attempt_count INTEGER NOT NULL,
    status TEXT NOT NULL, process_after TEXT, last_error TEXT
);
CREATE TABLE memories (
    id TEXT PRIMARY KEY, content TEXT NOT NULL, embedding TEXT,
    visibility TEXT NOT NULL, importance REAL NOT NULL,
    created_at TEXT NOT NULL
);

-- Source transcripts and their derived summaries are both history. A new
-- compaction appends a replacement view; it never rewrites its source.
CREATE TRIGGER transcript_messages_no_update BEFORE UPDATE ON transcript_messages
BEGIN SELECT RAISE(ABORT, 'transcript_messages are append-only: update refused'); END;
CREATE TRIGGER transcript_messages_no_delete BEFORE DELETE ON transcript_messages
BEGIN SELECT RAISE(ABORT, 'transcript_messages are append-only: delete refused'); END;
CREATE TRIGGER context_compactions_no_update BEFORE UPDATE ON context_compactions
BEGIN SELECT RAISE(ABORT, 'context_compactions are append-only: update refused'); END;
CREATE TRIGGER context_compactions_no_delete BEFORE DELETE ON context_compactions
BEGIN SELECT RAISE(ABORT, 'context_compactions are append-only: delete refused'); END;
"""


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (1, MIGRATION_1),
    (2, MIGRATION_2),
    (3, MIGRATION_3),
    (4, MIGRATION_4),
    (5, MIGRATION_5),
    (6, MIGRATION_6),
    (7, MIGRATION_7),
    (8, MIGRATION_8),
    (9, MIGRATION_9),
    (10, MIGRATION_10),
    (11, MIGRATION_11),
    (12, MIGRATION_12),
    (13, MIGRATION_13),
    (14, MIGRATION_14),
    (15, MIGRATION_15),
    (16, MIGRATION_16),
    (17, MIGRATION_17),
    (18, MIGRATION_18),
    (19, MIGRATION_19),
    (20, MIGRATION_20),
    (21, MIGRATION_21),
    (22, MIGRATION_22),
    (23, MIGRATION_23),
    (24, MIGRATION_24),
)


def _split_statements(script: str) -> list[str]:
    """Split a migration into executable statements.

    `sqlite3` refuses more than one statement per `execute()`, and migrations
    contain CREATE TRIGGER bodies with internal semicolons. `sqlite3.complete_statement`
    knows where a statement genuinely ends, including inside BEGIN ... END.
    """
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        if not line.strip() or line.lstrip().startswith("--"):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        # Without recursive triggers, `INSERT OR REPLACE` deletes the old row
        # WITHOUT firing the BEFORE DELETE guard, silently defeating append-only.
        self.connection.execute("PRAGMA recursive_triggers = ON")
        first_assistant_migration = 19 not in self.applied_versions()
        self.migrate()
        if first_assistant_migration:
            epoch = self.connection.execute(
                "SELECT epoch FROM assistant_control WHERE id=1"
            ).fetchone()[0]
            marker = self.path.with_suffix(".authority")
            try:
                with marker.open("x") as authority:
                    authority.write(epoch)
            except FileExistsError:
                if marker.read_text() != epoch:
                    raise ValueError("authority marker disagrees with database") from None

    def __del__(self) -> None:
        # sqlite3.Connection participates in an internal reference cycle. On a
        # low descriptor limit, waiting for a later GC pass can exhaust files
        # even though the owning Organization is already unreachable.
        connection = getattr(self, "connection", None)
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass

    def applied_versions(self) -> set[int]:
        """Versions already recorded. Empty when the ledger table does not exist yet."""
        try:
            rows = self.connection.execute("SELECT version FROM schema_migrations").fetchall()
        except sqlite3.OperationalError:
            return set()
        return {int(row["version"]) for row in rows}

    def migrate(self) -> None:
        """Apply pending migrations in order. Forward-only; never downgrades.

        Each migration's DDL **and** its version stamp go inside one explicit
        `BEGIN IMMEDIATE`, so a failure part way through leaves the database
        exactly as it was. SQLite rolls DDL back like any other statement.

        This deliberately does not use `executescript()`. That helper COMMITs
        any open transaction before it runs, which silently defeated the
        rollback this docstring promises: a migration that created a table and
        then hit invalid SQL left the table behind, unstamped, so reopening
        re-ran it and failed forever.
        """
        applied = self.applied_versions()
        for version, script in MIGRATIONS:
            if version in applied:
                continue
            previous = self.connection.isolation_level
            self.connection.isolation_level = None
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                for statement in _split_statements(script):
                    self.connection.execute(statement)
                self.connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (?, datetime('now'))",
                    (version,),
                )
                self.connection.execute("COMMIT")
            except Exception:
                self.connection.execute("ROLLBACK")
                raise
            finally:
                self.connection.isolation_level = previous

    @contextmanager
    def immediate(self) -> Iterator[sqlite3.Connection]:
        """A write transaction that takes its lock UP FRONT.

        `BEGIN IMMEDIATE` acquires the reserved lock before any statement runs,
        so two connections cannot both read a row, both decide to act, and both
        write. Deferred transactions -- SQLite's default -- allow exactly that.
        """
        if self.connection.in_transaction:
            raise RuntimeError(
                "immediate requires no pending transaction; commit or rollback explicitly"
            )
        previous = self.connection.isolation_level
        self.connection.isolation_level = None
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        finally:
            self.connection.isolation_level = previous

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def get(self, table: str, key: str, value: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT record FROM {table} WHERE {key} = ?", (value,)
        ).fetchone()
        return json.loads(row["record"]) if row else None

    def put(
        self,
        table: str,
        record_id: str,
        record: dict[str, Any],
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = json.dumps(record, default=str)
        if table == "outcomes":
            self.connection.execute(
                "INSERT OR REPLACE INTO outcomes(id, record) VALUES (?, ?)",
                (record_id, payload),
            )
        elif table == "sows":
            self.connection.execute(
                "INSERT OR REPLACE INTO sows(id, outcome_id, record) VALUES (?, ?, ?)",
                (record_id, extra["outcome_id"] if extra else record["outcome_id"], payload),
            )
        elif table == "actors":
            self.connection.execute(
                "INSERT OR REPLACE INTO actors(id, record) VALUES (?, ?)",
                (record_id, payload),
            )
        elif table == "assignments":
            # NOT a plain `INSERT OR REPLACE`: that statement fully replaces
            # the row, including columns it does not name -- which would
            # silently reset `current_execution_attempt` (Unit 8's fencing
            # pointer) to NULL on every ordinary state save, undoing an
            # attempt `fencing.acquire_execution_attempt` had just bound a
            # moment earlier in the same call. `ON CONFLICT ... DO UPDATE`
            # updates only the columns this call actually owns and leaves
            # `current_execution_attempt` exactly as it was -- that column is
            # written ONLY by `fencing.py`'s own dedicated SQL and by the
            # terminal-transaction fence check in `organization.run_assignment`.
            self.connection.execute(
                "INSERT INTO assignments(id, sow_id, actor_id, record) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET sow_id = excluded.sow_id, "
                "actor_id = excluded.actor_id, record = excluded.record",
                (record_id, record["sow_id"], record["actor_id"], payload),
            )
        elif table == "messages":
            self.connection.execute(
                "INSERT OR REPLACE INTO messages(id, recipient, record, state, claim_owner, "
                "claim_expires_at, fencing_token) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    record["recipient"],
                    payload,
                    record.get("state", "NEW"),
                    record.get("claim_owner"),
                    record.get("claim_expires_at"),
                    record.get("fencing_token"),
                ),
            )
        else:
            self.connection.execute(
                f"INSERT OR REPLACE INTO {table}(id, record) VALUES (?, ?)",
                (record_id, payload),
            )

    def put_serialized(self, table: str, record_id: str, payload: str) -> None:
        """Persist already-canonical JSON without changing its bytes."""
        json.loads(payload)
        if table != "receipts":
            raise ValueError("put_serialized is restricted to canonical receipts")
        record = json.loads(payload)
        self.connection.execute(
            "INSERT OR REPLACE INTO receipts(id, record, assignment_id, status) "
            "VALUES (?, ?, ?, ?)",
            (record_id, payload, record.get("assignment_id"), record.get("status", "")),
        )

    def close(self) -> None:
        """Release SQLite descriptors promptly instead of waiting for cyclic GC."""
        self.connection.close()
