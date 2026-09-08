"""Durable addressed mailbox with claim leases, fenced against F-U4-1."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sovereign_agent.database import Database
from sovereign_agent.errors import Refusal
from sovereign_agent.events import append_event
from sovereign_agent.ids import new_id, utc_now
from sovereign_agent.models import Message, MessageState

LEASE = timedelta(minutes=15)
MAX_RETRIES = 3


def _mint_claim_token(db: Database) -> int:
    """Draw a fresh token from the same monotonic counter `fencing.py` uses.

    Every claim that actually WINS the CAS below -- a fresh NEW message or a
    takeover of an expired lease, by any actor including the one that just
    lost it -- gets a token strictly greater than any token minted before it,
    forever. The idempotent same-owner-unexpired return path (below) does
    NOT call this: returning the SAME token for a claim you already hold is
    what makes that path idempotent rather than a silent takeover of your
    own lease.
    """
    cursor = db.connection.execute(
        "INSERT INTO lease_tokens(kind, created_at) VALUES ('mailbox_claim', ?)",
        (utc_now().isoformat(),),
    )
    token = cursor.lastrowid
    assert token is not None
    return int(token)


def send(db: Database, sender: str, recipient: str, subject: str, body: str) -> Message:
    message = Message(
        id=new_id("msg"),
        sender=sender,
        recipient=recipient,
        subject=subject,
        body=body,
        state=MessageState.NEW,
        created_at=utc_now(),
    )
    with db.transaction():
        db.put("messages", message.id, message.model_dump(mode="json"))
        append_event(db, "message.sent", {"id": message.id, "recipient": recipient})
    return message


def sweep_claims(db: Database, now: datetime, recipient: str | None = None) -> list[str]:
    """Expiry is rechecked in the mutation itself; never overwrite a fresh owner."""
    with db.immediate() as connection:
        rows = connection.execute(
            "UPDATE messages SET state = 'NEW', claim_owner = NULL, "
            "record = json_set(record, '$.state', 'NEW', '$.claim_owner', NULL) "
            "WHERE state = 'CLAIMED' AND claim_expires_at <= ? "
            "AND (? IS NULL OR recipient = ?) RETURNING id",
            (now.isoformat(), recipient, recipient),
        ).fetchall()
        identifiers = sorted(str(row["id"]) for row in rows)
        for identifier in identifiers:
            append_event(db, "message.claim_swept", {"id": identifier})
    return identifiers


def inbox(db: Database, actor_id: str) -> list[Message]:
    sweep_claims(db, utc_now(), actor_id)
    rows = db.connection.execute(
        "SELECT record FROM messages WHERE recipient = ? AND state IN ('NEW', 'CLAIMED')",
        (actor_id,),
    ).fetchall()
    return [Message.model_validate_json(row["record"]) for row in rows]


def claim(db: Database, message_id: str, actor_id: str) -> Message:
    """Take an exclusive lease, or refuse. Compare-and-set, not read-then-write.

    The claim is a single `UPDATE ... WHERE state = 'NEW'` that must affect
    exactly one row. An earlier version read the message, decided in Python, and
    wrote it back: two connections both read NEW, both wrote, and both believed
    they owned the lease.

    **F-U4-1, closed.** The original same-owner short-circuit below --
    `if message.state == MessageState.CLAIMED and message.claim_owner ==
    actor_id: return message` -- fired unconditionally, even when that
    owner's own lease had already expired, which meant the CAS's own
    expired-lease clause (`claim_expires_at <= now`) was unreachable for the
    owner: only a *different* actor could ever hit it. Recorded as a named
    limit rather than silently fixed
    (`docs/rulings/2026-08-26-deferral-unit4-fencing.md`), because closing it
    meant deciding what a fencing token even IS -- Unit 8's territory, not
    Unit 4's. Now: the short-circuit only fires when the lease is *both*
    same-owner *and* unexpired (still idempotent -- a retried worker inside
    its own lease window gets the SAME fencing token back, not a new one).
    Same-owner-but-expired falls through into the CAS exactly like a
    different actor's takeover attempt would, and wins it the same way,
    minting a FRESH fencing token -- so a resumed worker that let its lease
    lapse can never present the stale token to `complete()`/`dead_letter()`
    below and have it accepted.
    """
    raw = db.get("messages", "id", message_id)
    if raw is None:
        raise Refusal(
            "Message missing.",
            "Addresses are exact actor ids.",
            "sovereign-agent inbox",
            "Use a real actor id.",
        )
    message = Message.model_validate(raw)
    if message.recipient != actor_id:
        raise Refusal(
            happened=f"{actor_id} cannot claim a message addressed to {message.recipient}.",
            why="A newly invented subagent is not an independently governed actor.",
            inspect="sovereign-agent actor list",
            next_command="Claim only with the addressed actor id.",
        )
    now = utc_now()
    if (
        message.state == MessageState.CLAIMED
        and message.claim_owner == actor_id
        and message.claim_expires_at is not None
        and message.claim_expires_at > now
    ):
        return message

    expires_at = now + LEASE
    with db.immediate() as connection:
        token = _mint_claim_token(db)
        # One statement decides the winner. Either this row was NEW (or its lease
        # had expired) at the moment of the UPDATE, or it was not. The expired
        # branch is now reachable by the SAME owner reclaiming their own lapsed
        # lease, not only by a different actor -- F-U4-1's fix.
        cursor = connection.execute(
            "UPDATE messages SET state = 'CLAIMED', claim_owner = ?, claim_expires_at = ?, "
            "fencing_token = ?, "
            "record = json_set(json_set(json_set(json_set(record, '$.state', 'CLAIMED'), "
            "'$.claim_owner', ?), '$.claim_expires_at', ?), '$.fencing_token', ?) "
            "WHERE id = ? AND (state = 'NEW' OR (state = 'CLAIMED' AND claim_expires_at <= ?))",
            (
                actor_id,
                expires_at.isoformat(),
                token,
                actor_id,
                expires_at.isoformat(),
                token,
                message_id,
                now.isoformat(),
            ),
        )
        if cursor.rowcount != 1:
            raise Refusal(
                "Message is not claimable.",
                "Claims are exclusive: another actor holds an unexpired lease.",
                "sovereign-agent inbox",
                "Wait for lease expiry.",
            )
        append_event(
            db, "message.claimed", {"id": message_id, "actor_id": actor_id, "fencing_token": token}
        )

    claimed = Message.model_validate(db.get("messages", "id", message_id))
    return claimed


def complete(db: Database, message_id: str, actor_id: str, *, fencing_token: int | None) -> Message:
    """Mark a claimed message DONE, verifying the caller's fencing token atomically.

    `claim_owner == actor_id` alone is not exclusivity: it is the SAME check
    that made the pre-Unit-8 mailbox actor-idempotent rather than
    process-exclusive (`docs/rulings/2026-08-26-one-process-per-actor.md`) --
    two processes hosting one actor id both pass it. `fencing_token` is
    REQUIRED (keyword-only, no default) precisely so a caller cannot silently
    skip presenting it: it must be the token this caller's own most recent
    successful `claim()` returned, and the UPDATE's WHERE clause checks it
    against the durable row in the SAME statement that performs the write --
    never re-derived from the row itself, which would make staleness
    undetectable by construction (the row's own current token always
    "matches itself"). A stale process presenting the token from a claim
    that has since been superseded by a fresher one -- its own resumed lease,
    or a different contender's -- is refused here rather than allowed to
    mark work done it may no longer be the one actually doing.
    """
    message = Message.model_validate(db.get("messages", "id", message_id) or {})
    if message.claim_owner != actor_id:
        raise Refusal(
            "Only the claimant can complete a message.",
            "Mailbox claims are exclusive.",
            "inbox",
            "claim first",
        )
    with db.immediate() as connection:
        cursor = connection.execute(
            "UPDATE messages SET state = 'DONE', "
            "record = json_set(record, '$.state', 'DONE') "
            "WHERE id = ? AND claim_owner = ? AND fencing_token IS ?",
            (message_id, actor_id, fencing_token),
        )
        if cursor.rowcount != 1:
            raise Refusal(
                f"{actor_id} no longer holds the fencing token for {message_id!r}.",
                "A newer claim -- by this actor's own reclaim of an expired "
                "lease, or by a different contender -- has since taken over. "
                "Completing under a stale token would let a process that lost "
                "its lease still mark work done.",
                "sovereign-agent inbox",
                "Re-claim the message before completing it.",
                category="fencing_token_stale",
            )
        append_event(db, "message.done", {"id": message_id})
    return Message.model_validate(db.get("messages", "id", message_id))


def dead_letter(db: Database, message: Message) -> Message:
    """Retry a failed delivery, or park it as DEAD after MAX_RETRIES.

    Verifies the presented `message.fencing_token` atomically against the
    durable row before writing, the same discipline as `complete()`: a stale
    in-memory `message` (read before a fresher claim took over the row) must
    not be able to drive this transition either. `fencing_token IS ?`
    (SQLite's null-safe equality) matches correctly even when the token is
    `NULL` -- a never-claimed message's own starting state. The write is
    inside a transaction and appends an event, like every other state
    change; it previously wrote outside one, so a crash mid-call could leave
    a message with no record of why it moved.
    """
    presented_token = message.fencing_token
    if message.retry_count < MAX_RETRIES:
        message.retry_count += 1
        message.state = MessageState.NEW
        message.claim_owner = None
        message.claim_expires_at = None
        message.fencing_token = None
        kind = "message.retried"
    else:
        message.state = MessageState.DEAD
        kind = "message.dead_lettered"
    payload = json.dumps(message.model_dump(mode="json"), default=str)
    with db.immediate() as connection:
        cursor = connection.execute(
            "UPDATE messages SET state = ?, claim_owner = ?, claim_expires_at = ?, "
            "fencing_token = ?, record = ? "
            "WHERE id = ? AND fencing_token IS ?",
            (
                message.state.value,
                message.claim_owner,
                message.claim_expires_at.isoformat() if message.claim_expires_at else None,
                message.fencing_token,
                payload,
                message.id,
                presented_token,
            ),
        )
        if cursor.rowcount != 1:
            raise Refusal(
                f"Message {message.id!r} was modified by another claim before "
                "this dead-letter transition could commit.",
                "The in-memory `message` this call received is stale relative "
                "to the durable row -- re-read it before retrying.",
                "sovereign-agent inbox",
                "Re-fetch the message and retry.",
                category="fencing_token_stale",
            )
        append_event(db, kind, {"id": message.id, "retry_count": message.retry_count})
    return message
