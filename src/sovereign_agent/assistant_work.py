"""Durable intake and fixed-interval scheduling with one live owner per session."""

from __future__ import annotations

import json
import math
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
        ) != (session, prompt, channel, recipient, subject):
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
    connection.execute(
        "INSERT INTO assistant_work"
        "(id,origin,session,prompt,created,channel,recipient,status,result,control,subject) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
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
    if not identifier or not session or not prompt.strip() or len(prompt.encode()) > 16_384:
        raise ValueError("invalid job")
    with db.immediate() as connection:
        connection.execute(
            "INSERT INTO assistant_jobs"
            "(id,session,prompt,interval_seconds,next_due,channel,recipient) "
            "VALUES (?,?,?,?,?,?,?)",
            (identifier, session, prompt, interval_seconds, first_due, channel, recipient),
        )


def tick(db: Database, *, now: float | None = None, maximum: int = 100) -> list[str]:
    now = time.time() if now is None else now
    if not math.isfinite(now) or not 1 <= maximum <= 1000:
        raise ValueError("invalid scheduler pass")
    created = []
    with db.immediate() as connection:
        rows = connection.execute(
            "SELECT * FROM assistant_jobs WHERE enabled=1 AND next_due<=? "
            "ORDER BY next_due,id LIMIT ?",
            (now, maximum),
        ).fetchall()
        for row in rows:
            identifier = _enqueue(
                connection,
                f"job:{row['id']}:{row['next_due']!r}",
                row["session"],
                row["prompt"],
                now,
                row["channel"],
                row["recipient"],
            )
            created.append(identifier)
            skipped = math.floor((now - row["next_due"]) / row["interval_seconds"])
            next_due = row["next_due"] + (skipped + 1) * row["interval_seconds"]
            connection.execute(
                "UPDATE assistant_jobs SET next_due=? WHERE id=?", (next_due, row["id"])
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
            "SELECT w.* FROM assistant_work w WHERE w.available_after<=? AND "
            "(?=0 OR w.control=1) AND "
            "((?=0 AND w.status='READY') OR (w.status='RUNNING' AND w.expires<=?) OR "
            "(?=1 AND w.status IN ('READY','BLOCKED','CANCELLED'))) AND "
            "(?=0 OR EXISTS (SELECT 1 FROM assistant_orders o WHERE o.work_id=w.id "
            "AND o.status IN ('SENDING','UNKNOWN'))) AND NOT EXISTS "
            "(SELECT 1 FROM assistant_work other WHERE other.session=w.session "
            "AND other.status='RUNNING' AND other.expires>?) "
            "ORDER BY w.control DESC,w.created,w.rowid LIMIT 1",
            (now, control_only, recovery_only, now, recovery_only, recovery_only, now),
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
        "AND status='RUNNING' AND expires>? AND subject=?",
        (work.id, work.owner, work.generation, now, work.subject),
    ).fetchone()
    if row is None:
        raise PermissionError("worker claim expired or superseded")


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
            "UPDATE assistant_work SET status='CANCELLED',cancelled=1,generation=generation+1 "
            "WHERE id=? AND status IN ('READY','RUNNING','BLOCKED')",
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
        connection.execute(
            "INSERT OR IGNORE INTO assistant_daily(session,day) VALUES (?,?)", (work.session, day)
        )
        row = connection.execute(
            "SELECT * FROM assistant_daily WHERE session=? AND day=?", (work.session, day)
        ).fetchone()
        if row["model_calls"] >= 100 or row["estimated_cost_pence"] + estimate_pence > 1000:
            raise PermissionError("daily model allowance exhausted")
        connection.execute(
            "UPDATE assistant_daily SET model_calls=model_calls+1,"
            "estimated_cost_pence=estimated_cost_pence+? WHERE session=? AND day=?",
            (estimate_pence, work.session, day),
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
