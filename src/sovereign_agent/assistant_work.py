"""Durable intake and fixed-interval scheduling with one live owner per session."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sovereign_agent.database import Database
from sovereign_agent.events import append_event


@dataclass(frozen=True)
class Claim:
    id: str
    session: str
    prompt: str
    generation: int
    owner: str
    epoch: str
    subject: str = ""
    role: str = "shop"


class IntakeLimitError(ValueError):
    """A condition may defer admission without consuming its pending episode."""


def _enqueue(
    connection: sqlite3.Connection,
    origin: str,
    session: str,
    prompt: str,
    now: float,
    channel: str = "local",
    recipient: str = "",
    subject: str = "",
    *,
    require_admission: bool = False,
    role: str = "shop",
    billing_session: str = "",
) -> str:
    if (
        not origin
        or not session
        or not prompt.strip()
        or len(prompt.encode()) > 16_384
        or len(origin) > 250
        or len(session) > 200
        or not math.isfinite(now)
        or not isinstance(subject, str)
        or len(subject) > 100
        or role not in {"shop", "research"}
        or len(billing_session) > 200
    ):
        raise ValueError("nonempty bounded intake required")
    existing = connection.execute(
        "SELECT * FROM assistant_work WHERE origin=?", (origin,)
    ).fetchone()
    if existing:
        if (
            existing["session"],
            existing["prompt"],
            existing["channel"],
            existing["recipient"],
            existing["subject"],
            existing["role"],
            existing["billing_session"],
        ) != (session, prompt, channel, recipient, subject, role, billing_session):
            raise ValueError("intake identity reused for different content")
        if require_admission and existing["status"] == "REJECTED":
            raise IntakeLimitError("existing intake was rejected")
        return str(existing["id"])
    control = channel.startswith("telegram:") and prompt.split(maxsplit=1)[0] in {
        "/approve",
        "/revoke",
        "/cancel",
    }
    day = int(now // 86400)
    connection.execute(
        "INSERT OR IGNORE INTO assistant_daily(session,day) VALUES (?,?)", (session, day)
    )
    admitted = connection.execute(
        "SELECT controls,admitted FROM assistant_daily WHERE session=? AND day=?", (session, day)
    ).fetchone()[int(not control)]
    pending = connection.execute(
        "SELECT count(*) FROM assistant_work WHERE session=? "
        "AND status IN ('READY','RUNNING','BLOCKED') AND control=?",
        (session, int(control)),
    ).fetchone()[0]
    rejected = admitted >= (200 if control else 50) or pending >= 20
    if rejected and require_admission:
        raise IntakeLimitError("intake capacity exhausted; condition remains pending")
    identifier = uuid.uuid4().hex
    revision = connection.execute(
        "SELECT revision FROM assistant_memory_revisions WHERE session=?", (session,)
    ).fetchone()
    connection.execute(
        "INSERT INTO assistant_work"
        "(id,origin,session,prompt,created,channel,recipient,status,result,control,subject,role,"
        "billing_session,context_revision) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            identifier,
            origin,
            session,
            prompt,
            now,
            channel,
            recipient,
            "REJECTED" if rejected else "READY",
            "Request limit reached; resolve pending work or return tomorrow." if rejected else None,
            int(control),
            subject,
            role,
            billing_session,
            revision[0] if revision else 0,
        ),
    )
    if not rejected:
        connection.execute(
            "UPDATE assistant_daily SET admitted=admitted+?,controls=controls+? "
            "WHERE session=? AND day=?",
            (int(not control), int(control), session, day),
        )
    return identifier


def enqueue(
    db: Database,
    origin: str,
    session: str,
    prompt: str,
    *,
    now: float | None = None,
    channel: str = "local",
    recipient: str = "",
    subject: str = "",
) -> str:
    with db.immediate() as connection:
        return _enqueue(
            connection,
            origin,
            session,
            prompt,
            time.time() if now is None else now,
            channel,
            recipient,
            subject,
        )


def validate_route(channel: str, recipient: str) -> None:
    if (
        not isinstance(channel, str)
        or not isinstance(recipient, str)
        or len(channel) > 200
        or len(recipient) > 200
        or not (
            (channel == "local" and not recipient)
            or (
                re.fullmatch(r"telegram:[A-Za-z0-9_-]+", channel)
                and recipient.isascii()
                and recipient.isdigit()
                and int(recipient) > 0
            )
        )
    ):
        raise ValueError("local output or an explicit positive Telegram recipient required")


def schedule(
    db: Database,
    identifier: str,
    session: str,
    prompt: str,
    *,
    first_due: float,
    interval_seconds: int,
    channel: str = "local",
    recipient: str = "",
) -> None:
    """Epoch UTC intervals; missed runs coalesce to one, rather than a backlog storm."""
    if type(interval_seconds) is not int or interval_seconds < 1 or not math.isfinite(first_due):
        raise ValueError("finite due time and positive integral interval required")
    if (
        any(
            not isinstance(value, str) or not value.strip() or len(value) > 100
            for value in (identifier, session)
        )
        or not isinstance(prompt, str)
        or not prompt.strip()
        or len(prompt.encode()) > 16_384
    ):
        raise ValueError("bounded job identity, session and prompt required")
    validate_route(channel, recipient)
    with db.immediate() as connection:
        if connection.execute("SELECT 1 FROM assistant_jobs WHERE id=?", (identifier,)).fetchone():
            raise ValueError(
                "schedule identity already exists; use a new identity for a replacement"
            )
        connection.execute(
            "INSERT INTO assistant_jobs"
            "(id,session,prompt,interval_seconds,next_due,channel,recipient) "
            "VALUES (?,?,?,?,?,?,?)",
            (identifier, session, prompt, interval_seconds, first_due, channel, recipient),
        )


def unschedule(db: Database, identifier: str) -> None:
    """Stop future ticks without deleting work that a prior tick already admitted."""
    with db.immediate() as connection:
        if (
            connection.execute(
                "UPDATE assistant_jobs SET enabled=0 WHERE id=?", (identifier,)
            ).rowcount
            != 1
        ):
            raise ValueError("unknown schedule")


def tick(db: Database, *, now: float | None = None, maximum: int = 100) -> list[str]:
    now = time.time() if now is None else now
    if not math.isfinite(now) or type(maximum) is not int or not 1 <= maximum <= 1000:
        raise ValueError("invalid scheduler pass")
    created = []
    with db.immediate() as connection:
        if connection.execute("SELECT paused FROM assistant_control WHERE id=1").fetchone()[0]:
            return []
        rows = connection.execute(
            "SELECT * FROM assistant_jobs WHERE enabled=1 AND next_due<=? "
            "ORDER BY next_due,id LIMIT ?",
            (now, maximum),
        ).fetchall()
        for row in rows:
            try:
                identifier = _enqueue(
                    connection,
                    f"job:{row['id']}:{row['next_due']!r}",
                    row["session"],
                    row["prompt"],
                    now,
                    row["channel"],
                    row["recipient"],
                    require_admission=True,
                )
            except IntakeLimitError:
                if not row["deferred"]:
                    append_event(db, "assistant.job.deferred", {"job": row["id"]})
                    connection.execute(
                        "UPDATE assistant_jobs SET deferred=1 WHERE id=?", (row["id"],)
                    )
                continue
            created.append(identifier)
            skipped = math.floor((now - row["next_due"]) / row["interval_seconds"])
            next_due = row["next_due"] + (skipped + 1) * row["interval_seconds"]
            connection.execute(
                "UPDATE assistant_jobs SET next_due=?,deferred=0 WHERE id=?", (next_due, row["id"])
            )
            append_event(
                db,
                "assistant.job.enqueued",
                {"job": row["id"], "work": identifier, "coalesced": skipped},
            )
    return created


def claim(
    db: Database,
    owner: str,
    *,
    now: float | None = None,
    ttl: float = 90,
    recovery_only: bool = False,
    control_only: bool = False,
    role: str = "shop",
    identifier: str = "",
) -> Claim | None:
    now = time.time() if now is None else now
    if not owner or not math.isfinite(now) or not math.isfinite(ttl) or not 0 < ttl <= 3600:
        raise ValueError("bounded claim lifetime required")
    with db.immediate() as connection:
        control = connection.execute(
            "SELECT epoch,paused FROM assistant_control WHERE id=1"
        ).fetchone()
        if control["paused"]:
            return None
        row = connection.execute(
            "SELECT w.* FROM assistant_work w WHERE w.role=? AND (?='' OR w.id=?) "
            "AND w.available_after<=? AND "
            "(?=0 OR w.control=1) AND "
            "((?=0 AND w.status='READY') OR (w.status='RUNNING' AND w.expires<=?) OR "
            "(?=1 AND w.status IN ('READY','BLOCKED','CANCELLED'))) AND "
            "(?=0 OR EXISTS (SELECT 1 FROM assistant_orders o WHERE o.work_id=w.id "
            "AND o.status IN ('SENDING','UNKNOWN'))) AND NOT EXISTS "
            "(SELECT 1 FROM assistant_work other WHERE other.session=w.session "
            "AND other.status='RUNNING' AND other.expires>?) "
            "ORDER BY w.control DESC,w.created,w.rowid LIMIT 1",
            (
                role,
                identifier,
                identifier,
                now,
                control_only,
                recovery_only,
                now,
                recovery_only,
                recovery_only,
                now,
            ),
        ).fetchone()
        if row is None:
            return None
        generation = row["generation"] + 1
        connection.execute(
            "UPDATE assistant_work SET status='RUNNING',generation=?,owner=?,expires=? WHERE id=?",
            (generation, owner, now + ttl, row["id"]),
        )
        append_event(db, "assistant.work.claimed", {"work": row["id"], "generation": generation})
        return Claim(
            row["id"],
            row["session"],
            row["prompt"],
            generation,
            owner,
            control["epoch"],
            row["subject"],
            row["role"],
        )


def assert_current(connection: sqlite3.Connection, work: Claim, now: float | None = None) -> None:
    now = time.time() if now is None else now
    control = connection.execute("SELECT epoch,paused FROM assistant_control WHERE id=1").fetchone()
    location = connection.execute("PRAGMA database_list").fetchone()[2]
    try:
        current_epoch = Path(location).with_suffix(".authority").read_text()
    except OSError:
        raise PermissionError("authority marker is unavailable") from None
    if (
        not control
        or control["paused"]
        or current_epoch != control["epoch"]
        or work.epoch != current_epoch
    ):
        raise PermissionError("runtime paused or replaced by restore")
    row = connection.execute(
        "SELECT 1 FROM assistant_work WHERE id=? AND owner=? AND generation=? "
        "AND status='RUNNING' AND expires>? AND subject=? AND role=? AND session=? AND prompt=?",
        (
            work.id,
            work.owner,
            work.generation,
            now,
            work.subject,
            work.role,
            work.session,
            work.prompt,
        ),
    ).fetchone()
    if row is None:
        raise PermissionError("worker claim expired or superseded")
    if work.role == "research":
        contract = connection.execute(
            "SELECT d.deadline,p.cancelled FROM assistant_delegations d "
            "JOIN assistant_work p ON p.id=d.parent_id WHERE d.work_id=?",
            (work.id,),
        ).fetchone()
        if contract is None or contract["deadline"] <= now or contract["cancelled"]:
            raise PermissionError("delegation expired or parent cancelled")


def observe(db: Database, work: Claim, message: dict[str, Any]) -> None:
    with db.immediate() as connection:
        assert_current(connection, work)
        connection.execute(
            "INSERT INTO assistant_transcript(work_id,generation,message) VALUES (?,?,?)",
            (work.id, work.generation, json.dumps(message, allow_nan=False)),
        )


def finish(
    db: Database, work: Claim, status: str, result: str, *, now: float | None = None
) -> None:
    if status not in {"DONE", "BLOCKED", "CANCELLED"}:
        raise ValueError("invalid terminal work state")
    with db.immediate() as connection:
        assert_current(connection, work, now)
        connection.execute(
            "UPDATE assistant_work SET status=?,result=?,expires=NULL,available_after=? WHERE id=?",
            (
                status,
                result,
                (time.time() if now is None else now)
                + (min(60, 2 ** min(work.generation, 6)) if status == "BLOCKED" else 0),
                work.id,
            ),
        )
        append_event(
            db,
            "assistant.work.finished",
            {"work": work.id, "status": status, "generation": work.generation},
        )


def cancel(db: Database, identifier: str) -> None:
    """Operator action; cancellation cannot recall an already transmitted order."""
    with db.immediate() as connection:
        amount = connection.execute(
            "SELECT coalesce(sum(amount),0) FROM assistant_orders "
            "WHERE work_id=? AND status='APPROVED'",
            (identifier,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE assistant_spending SET reserved_pence=reserved_pence-? WHERE id=1", (amount,)
        )
        connection.execute(
            "UPDATE assistant_orders SET revoked=1,status=CASE WHEN status IN ('APPROVED','DRAFT') "
            "THEN 'REVOKED' ELSE status END WHERE work_id=?",
            (identifier,),
        )
        changed = connection.execute(
            "UPDATE assistant_work SET status='CANCELLED',cancelled=1,generation=generation+1,"
            "result='Cancellation recorded; transmitted orders still require reconciliation.' "
            "WHERE id=? AND status IN ('READY','RUNNING','BLOCKED')",
            (identifier,),
        ).rowcount
        # A parent may have finished its stock task while its child still works.
        # Stop that child without rewriting the parent's completed business result.
        changed += connection.execute(
            "UPDATE assistant_work SET cancelled=1,generation=generation+1 "
            "WHERE id=? AND status='DONE' AND cancelled=0 AND EXISTS "
            "(SELECT 1 FROM assistant_delegations d JOIN assistant_work child "
            "ON child.id=d.work_id WHERE d.parent_id=assistant_work.id "
            "AND child.status IN ('READY','RUNNING','BLOCKED'))",
            (identifier,),
        ).rowcount
        if changed:
            append_event(db, "assistant.work.cancelled", {"work": identifier})


def reserve_model_call(
    db: Database, work: Claim, estimate_pence: int, *, now: float | None = None
) -> None:
    """Retain estimated exposure even if the provider's reply is lost. Not an invoice cap."""
    if type(estimate_pence) is not int or estimate_pence < 0:
        raise ValueError("nonnegative integral model estimate required")
    now = time.time() if now is None else now
    if not math.isfinite(now):
        raise ValueError("finite clock required")
    day = int(now // 86400)
    with db.immediate() as connection:
        assert_current(connection, work, now)
        ledger = connection.execute(
            "SELECT billing_session,estimated_cost_pence FROM assistant_work WHERE id=?",
            (work.id,),
        ).fetchone()
        billing = ledger["billing_session"] or work.session
        if work.role == "research":
            contract = connection.execute(
                "SELECT * FROM assistant_delegations WHERE work_id=?", (work.id,)
            ).fetchone()
            if (
                contract["model_calls"] >= contract["model_calls_limit"]
                or estimate_pence != contract["estimated_call_pence"]
                or ledger["estimated_cost_pence"] + estimate_pence > contract["budget_pence"]
            ):
                raise PermissionError("delegation model allowance exhausted")
            connection.execute(
                "UPDATE assistant_delegations SET model_calls=model_calls+1 WHERE work_id=?",
                (work.id,),
            )
        connection.execute(
            "INSERT OR IGNORE INTO assistant_daily(session,day) VALUES (?,?)", (billing, day)
        )
        row = connection.execute(
            "SELECT * FROM assistant_daily WHERE session=? AND day=?", (billing, day)
        ).fetchone()
        if (
            row["model_calls"] >= row["call_limit"]
            or row["estimated_cost_pence"] + estimate_pence > row["cost_limit"]
        ):
            raise PermissionError("daily model allowance exhausted")
        connection.execute(
            "UPDATE assistant_daily SET model_calls=model_calls+1,"
            "estimated_cost_pence=estimated_cost_pence+? WHERE session=? AND day=?",
            (estimate_pence, billing, day),
        )
        connection.execute(
            "UPDATE assistant_work SET estimated_cost_pence=estimated_cost_pence+? WHERE id=?",
            (estimate_pence, work.id),
        )


def session_state(db: Database, session: str) -> str:
    if db.connection.execute("SELECT paused FROM assistant_control").fetchone()[0]:
        return "SUSPENDED"
    rows = db.connection.execute(
        "SELECT status FROM assistant_work WHERE session=?", (session,)
    ).fetchall()
    if any(row[0] == "RUNNING" for row in rows):
        return "TURN_RUNNING"
    orders = db.connection.execute(
        "SELECT o.status FROM assistant_orders o JOIN assistant_work w ON w.id=o.work_id "
        "WHERE w.session=?",
        (session,),
    ).fetchall()
    if any(row[0] in {"SENDING", "UNKNOWN"} for row in orders):
        return "AWAITING_EXTERNAL"
    if any(row[0] in {"DRAFT", "APPROVED"} for row in orders):
        return "AWAITING_APPROVAL"
    return "IDLE"
