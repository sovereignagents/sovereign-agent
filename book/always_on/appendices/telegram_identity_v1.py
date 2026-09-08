"""Discover your private user ID with a one-time setup challenge; never enroll anyone."""

import os
import secrets

from sovereign_agent.telegram_channel import Telegram


def matching_operators(updates, challenge):
    if not isinstance(updates, list) or len(updates) > 100:
        raise ValueError("invalid setup update batch")
    found = set()
    for update in updates:
        if not isinstance(update, dict):
            continue
        message = update.get("message")
        if not isinstance(message, dict):
            continue
        sender, chat = message.get("from"), message.get("chat")
        if not isinstance(sender, dict) or not isinstance(chat, dict):
            continue
        actor = sender.get("id")
        if (
            type(actor) is int
            and actor > 0
            and not sender.get("is_bot")
            and chat.get("type") == "private"
            and type(chat.get("id")) is int
            and chat["id"] == actor
            and message.get("text") == challenge
        ):
            found.add(actor)
    if len(found) > 1:
        raise ValueError("setup challenge appeared from multiple accounts; start a new challenge")
    return next(iter(found), None)


def main():
    token = os.environ.get("SOVEREIGN_AGENT_TELEGRAM_TOKEN", "")
    if not token:
        raise ValueError("set the dedicated bot credential in your environment first")
    bot = Telegram(token)
    challenge = "lucy-setup-" + secrets.token_urlsafe(18)
    print(
        "From your intended private account, send this exact text to your dedicated bot:",
        flush=True,
    )
    print(challenge, flush=True)
    # A fresh teaching bot avoids an unrelated backlog. Offset zero never
    # confirms/discards updates here; normal durable intake acknowledges later.
    for _ in range(3):
        updates = bot.call(
            "getUpdates", {"offset": 0, "limit": 100, "timeout": 20, "allowed_updates": ["message"]}
        )
        actor = matching_operators(updates, challenge)
        if actor is not None:
            print("Verified challenge sender ID:", actor)
            print(
                "Review this ID and add it to your operator allowlist locally. "
                "No account was enrolled."
            )
            return 0
    print(
        "No matching private setup message arrived. "
        "Use a dedicated bot with no other poller or backlog."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
