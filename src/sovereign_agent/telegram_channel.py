"""One Telegram operator channel: durable intake, explicit ambiguous delivery."""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Protocol

from sovereign_agent.assistant_work import _enqueue
from sovereign_agent.database import Database
from sovereign_agent.http_transport import request


class Bot(Protocol):
    account: str

    def call(self, method: str, data: dict[str, Any]) -> Any: ...


class Telegram:
    def __init__(self, token: str) -> None:
        if not re.fullmatch(r"[0-9]+:[a-zA-Z0-9_-]+", token):
            raise ValueError("invalid Telegram credential format")
        self._token = token
        self.account = token.split(":", 1)[0]

    def call(self, method: str, data: dict[str, Any]) -> Any:
        if method not in {"getUpdates", "sendMessage"}:
            raise ValueError("unsupported Telegram operation")
        try:
            response = request(
                "https://api.telegram.org/bot" + self._token + "/" + method,
                data=json.dumps(data).encode(),
                headers={"Content-Type": "application/json"},
                timeout=35,
            )
            if response.status != 200:
                raise OSError("Telegram declined operation")
            result = json.loads(response.body)
            if result.get("ok") is not True:
                raise ValueError("Telegram declined operation")
            return result["result"]
        except OSError, ValueError, KeyError, TypeError:
            # API URLs contain the token. Never expose exception URLs or bodies.
            raise OSError("Telegram request failed; inspect connectivity and credentials") from None


def poll(db: Database, bot: Bot, operators: frozenset[int]) -> list[str]:
    if not operators or any(type(actor) is not int or actor <= 0 for actor in operators):
        raise ValueError("explicit numeric operator allowlist required")
    channel = "telegram:" + bot.account
    owner = uuid.uuid4().hex
    with db.immediate() as connection:
        lease = connection.execute(
            "SELECT * FROM assistant_channel_leases WHERE channel=?", (channel,)
        ).fetchone()
        if lease and lease["expires"] > time.time():
            raise PermissionError("another poller owns this bot account")
        connection.execute(
            "INSERT INTO assistant_channel_leases(channel,owner,expires) VALUES (?,?,?) "
            "ON CONFLICT(channel) DO UPDATE SET owner=excluded.owner,expires=excluded.expires",
            (channel, owner, time.time() + 40),
        )
    try:
        return _poll_owned(db, bot, operators, channel, owner)
    finally:
        with db.immediate() as connection:
            connection.execute(
                "DELETE FROM assistant_channel_leases WHERE channel=? AND owner=?", (channel, owner)
            )


def _poll_owned(
    db: Database, bot: Bot, operators: frozenset[int], channel: str, owner: str
) -> list[str]:
    cursor = db.connection.execute(
        "SELECT offset FROM assistant_channel_cursor WHERE channel=?", (channel,)
    ).fetchone()
    offset = cursor[0] if cursor else 0
    updates = bot.call(
        "getUpdates",
        {"offset": offset, "limit": 100, "timeout": 20, "allowed_updates": ["message"]},
    )
    if not isinstance(updates, list) or len(updates) > 100:
        raise ValueError("invalid Telegram update batch")
    identifiers = []
    with db.immediate() as connection:
        current = connection.execute(
            "SELECT 1 FROM assistant_channel_leases WHERE channel=? AND owner=? AND expires>?",
            (channel, owner, time.time()),
        ).fetchone()
        if not current:
            raise PermissionError("poller claim expired")
        highest = offset - 1
        for update in updates:
            update_id = update.get("update_id")
            if type(update_id) is not int or update_id < 0:
                raise ValueError("invalid update identity")
            # Do not discard an earlier member of an unordered batch. The cursor
            # is published only after every accepted payload is durable.
            highest = max(highest, update_id)
            message = update.get("message", {})
            actor = message.get("from", {}).get("id")
            chat = message.get("chat", {})
            text = message.get("text")
            if (
                type(actor) is int
                and actor in operators
                and chat.get("type") == "private"
                and chat.get("id") == actor
                and not message.get("from", {}).get("is_bot")
                and isinstance(text, str)
                and text.strip()
                and len(text.encode()) <= 16_384
            ):
                origin = f"{channel}:{update_id}"
                existed = connection.execute(
                    "SELECT id FROM assistant_work WHERE origin=?", (origin,)
                ).fetchone()
                identifier = _enqueue(
                    connection, origin, f"{channel}:{actor}", text, time.time(), channel, str(actor)
                )
                if not existed:
                    identifiers.append(identifier)
        connection.execute(
            "INSERT INTO assistant_channel_cursor(channel,offset) VALUES (?,?) "
            "ON CONFLICT(channel) DO UPDATE SET offset=excluded.offset",
            (channel, max(offset, highest + 1)),
        )
    return identifiers


def deliver_one(db: Database, bot: Bot, operators: frozenset[int]) -> str | None:
    with db.immediate() as connection:
        row = connection.execute(
            "SELECT * FROM assistant_work WHERE channel=? AND "
            "status IN ('DONE','BLOCKED','CANCELLED','REJECTED') AND delivery='PENDING' "
            "ORDER BY created LIMIT 1",
            ("telegram:" + bot.account,),
        ).fetchone()
        if row is None:
            return None
        if not row["recipient"].isdigit() or int(row["recipient"]) not in operators:
            connection.execute(
                "UPDATE assistant_work SET delivery='DENIED' WHERE id=?", (row["id"],)
            )
            return "DENIED"
        # A crash after this commit is ambiguous, even if no HTTP call happened.
        connection.execute("UPDATE assistant_work SET delivery='SENDING' WHERE id=?", (row["id"],))
    try:
        text = row["result"] or "Work ended without a report."
        if len(text) > 3900:
            text = text[:3800] + "\n[Report truncated; request a shorter report.]"
        result = bot.call("sendMessage", {"chat_id": int(row["recipient"]), "text": text})
        if not isinstance(result, dict) or type(result.get("message_id")) is not int:
            raise ValueError("missing delivery receipt")
        status = "SENT"
    except OSError, ValueError:
        status = "UNKNOWN"
    with db.immediate() as connection:
        connection.execute(
            "UPDATE assistant_work SET delivery=? WHERE id=? AND delivery='SENDING'",
            (status, row["id"]),
        )
    return status
