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


def _enqueue(
    connection: sqlite3.Connection,
    origin: str,
    session: str,
    prompt: str,
    now: float,
    channel: str = "local",
    recipient: str = "",
) -> str:
    if not origin or not session or not prompt.strip() or len(prompt.encode()) > 16_384:
        raise ValueError("nonempty bounded intake required")
    identifier = uuid.uuid4().hex
    connection.execute(
        "INSERT OR IGNORE INTO assistant_work(id,origin,session,prompt,created,channel,recipient) "
        "VALUES (?,?,?,?,?,?,?)",
        (identifier, origin, session, prompt, now, channel, recipient),
    )
    row = connection.execute("SELECT * FROM assistant_work WHERE origin=?", (origin,)).fetchone()
    assert row
    if (row["session"], row["prompt"], row["channel"], row["recipient"]) != (
        session,
        prompt,
        channel,
        recipient,
    ):
        raise ValueError("intake identity reused for different content")
    return str(row["id"])


def enqueue(
    db: Database,
    origin: str,
    session: str,
    prompt: str,
    *,
    now: float | None = None,
    channel: str = "local",
    recipient: str = "",
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


def claim(db: Database, owner: str, *, now: float | None = None, ttl: float = 90) -> Claim | None:
    now = time.time() if now is None else now
    if not owner or not math.isfinite(ttl) or not 0 < ttl <= 3600:
        raise ValueError("bounded claim lifetime required")
    with db.immediate() as connection:
        row = connection.execute(
            "SELECT w.* FROM assistant_work w WHERE (w.status='READY' OR "
            "(w.status='RUNNING' AND w.expires<=?)) AND NOT EXISTS "
            "(SELECT 1 FROM assistant_work other WHERE other.session=w.session "
            "AND other.status='RUNNING' AND other.expires>?) ORDER BY w.created,w.rowid LIMIT 1",
            (now, now),
        ).fetchone()
        if row is None:
            return None
        generation = row["generation"] + 1
        connection.execute(
            "UPDATE assistant_work SET status='RUNNING',generation=?,owner=?,expires=? WHERE id=?",
            (generation, owner, now + ttl, row["id"]),
        )
        append_event(db, "assistant.work.claimed", {"work": row["id"], "generation": generation})
        return Claim(row["id"], row["session"], row["prompt"], generation, owner)


def assert_current(connection: sqlite3.Connection, work: Claim, now: float | None = None) -> None:
    now = time.time() if now is None else now
    control = connection.execute("SELECT epoch,paused FROM assistant_control WHERE id=1").fetchone()
    location = connection.execute("PRAGMA database_list").fetchone()[2]
    try:
        current_epoch = Path(location).with_suffix(".authority").read_text()
    except OSError:
        raise PermissionError("authority marker is unavailable") from None
    if not control or control["paused"] or current_epoch != control["epoch"]:
        raise PermissionError("runtime paused or replaced by restore")
    row = connection.execute(
        "SELECT 1 FROM assistant_work WHERE id=? AND owner=? AND generation=? "
        "AND status='RUNNING' AND expires>?",
        (work.id, work.owner, work.generation, now),
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
            "UPDATE assistant_work SET status=?,result=?,expires=NULL WHERE id=?",
            (status, result, work.id),
        )
        append_event(
            db,
            "assistant.work.finished",
            {"work": work.id, "status": status, "generation": work.generation},
        )


def cancel(db: Database, identifier: str) -> None:
    """Operator action; cancellation cannot recall an already transmitted order."""
    with db.immediate() as connection:
        changed = connection.execute(
            "UPDATE assistant_work SET status='CANCELLED',generation=generation+1 "
            "WHERE id=? AND status IN ('READY','RUNNING','BLOCKED')",
            (identifier,),
        ).rowcount
        if changed:
            append_event(db, "assistant.work.cancelled", {"work": identifier})
