"""Chapter 6: durable private messages, session routing and explicit delivery uncertainty."""

import argparse
import json
import os
import runpy
import tempfile
from pathlib import Path

from reference_organizations.store.agent import OfflineShopModel, seed_lucy, shop_dispatcher
from reference_organizations.store.evaluation import CASES, candidate_checks, evaluate
from sovereign_agent.agent_loop import run_loop
from sovereign_agent.assistant_context import (
    activate_skill,
    context,
    remember,
    skill_snapshot,
    stage_skill,
)
from sovereign_agent.assistant_work import assert_current, claim, finish, reserve_model_call
from sovereign_agent.database import Database
from sovereign_agent.model_turn import HTTPModel
from sovereign_agent.telegram_channel import Telegram, deliver_one, poll

PROMPT = "Prepare replenishment drafts from current stock. State GBP amounts."


def update(identifier, actor=123):
    return {
        "update_id": identifier,
        "message": {
            "from": {"id": actor, "is_bot": False},
            "chat": {"id": actor, "type": "private"},
            "text": PROMPT,
        },
    }


class OfflineBot:
    account = "teaching"

    def __init__(self, updates):
        self.updates = updates
        self.offsets = []
        self.sent = []
        self.lose_next_reply = False

    def call(self, method, data):
        if method == "getUpdates":
            self.offsets.append(data["offset"])
            # Replaying even acknowledged data deliberately challenges local deduplication.
            return self.updates
        self.sent.append(data)
        if self.lose_next_reply:
            self.lose_next_reply = False
            raise TimeoutError("accepted remotely but reply lost")
        return {"message_id": 900 + len(self.sent)}


def initialize(path):
    db = Database(path)
    seed_lucy(db)
    if not skill_snapshot(db)[1]:
        source = Path(__file__).parents[1] / "skills" / "opening-check-v1.toml"
        candidate = stage_skill(db, source)
        activate_skill(
            db,
            candidate.name,
            candidate.version,
            evaluate=lambda skill: candidate_checks(
                evaluate(OfflineShopModel, skill=skill, cases=CASES[:3])
            ),
            required_cases=frozenset(f"{case.name}:0" for case in CASES[:3]),
        )
    return db


def run_claim(db, current, model):
    dispatcher = shop_dispatcher(db)
    messages = context(db, current.session, current.prompt, allowed=dispatcher.allowed)
    result = run_loop(
        model,
        dispatcher,
        messages,
        check_current=lambda: assert_current(db.connection, current),
        reserve_call=lambda: reserve_model_call(db, current, 0),
    )
    previous = runpy.run_path(str(Path(__file__).with_name("ch03.py")))
    passed = result.status == "COMPLETED" and previous["draft_evidence"](result)
    finish(db, current, "DONE" if passed else "BLOCKED", result.answer)
    return passed, result


def offline():
    with tempfile.TemporaryDirectory(prefix="lucy-channel-") as temporary:
        db = initialize(Path(temporary) / "agent.sqlite")
        bot = OfflineBot([update(103, actor=999), update(101), update(102)])
        operators = frozenset({123})
        ids = poll(db, bot, operators)
        assert len(ids) == 2
        print("Accepted private requests:", len(ids))
        session = "telegram:teaching:123"
        remember(db, session, "format", "three bullets", "lucy/explicit-message")
        db.close()
        db = Database(db.path)
        print("Duplicate intake after restart:", len(poll(db, bot, operators)))
        assert bot.offsets == [0, 104]
        ids = [
            row[0]
            for row in db.connection.execute(
                "SELECT id FROM assistant_work WHERE status='READY' ORDER BY created,rowid"
            )
        ]
        first = claim(db, "phone-worker", identifier=ids[0])
        assert first is not None
        second_connection = Database(db.path)
        competing = claim(second_connection, "second-worker", identifier=ids[1])
        assert competing is None
        print("Conflicting session claim:", competing)
        second_connection.close()
        passed, result = run_claim(db, first, OfflineShopModel())
        assert passed and "three bullets" in result.messages[0]["content"]
        second = claim(db, "phone-worker", identifier=ids[1])
        assert second is not None
        assert run_claim(db, second, OfflineShopModel())[0]
        print("Completed drafts:", 2)
        bot.lose_next_reply = True
        print("First delivery:", deliver_one(db, bot, operators))
        print("Second delivery:", deliver_one(db, bot, operators))
        db.close()
        db = Database(db.path)
        print("Automatic resend:", deliver_one(db, bot, operators))
        assert len(bot.sent) == 2
        assert {row[0] for row in db.connection.execute("SELECT delivery FROM assistant_work")} == {
            "UNKNOWN",
            "SENT",
        }
        receipts = db.connection.execute(
            "SELECT count(*) FROM events WHERE kind='assistant.channel.sent'"
        ).fetchone()[0]
        print("Recorded send receipts:", receipts)
        orders = db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0]
        print("Purchases:", orders)
        assert receipts == 1 and orders == 0
        db.close()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="use your dedicated test bot and allowlisted private account",
    )
    parser.add_argument(
        "--root", type=Path, help="persistent dedicated test state; required for Telegram"
    )
    parser.add_argument(
        "--live", action="store_true", help="use the local HTTP model for Telegram work"
    )
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--transcript", action="store_true")
    args = parser.parse_args()
    if not args.telegram:
        if args.live:
            parser.error(
                "--live requires --telegram here; Chapter 5 supplies the model-only experiment"
            )
        return offline()
    if args.root is None:
        parser.error("--telegram requires a dedicated persistent --root")
    token = os.environ.get("SOVEREIGN_AGENT_TELEGRAM_TOKEN", "")
    actors = os.environ.get("SOVEREIGN_AGENT_OPERATORS", "").split(",")
    if not token or not all(actor.isdigit() and int(actor) > 0 for actor in actors):
        parser.error(
            "set the bot credential and positive numeric operator allowlist in your environment"
        )
    bot = Telegram(token)
    operators = frozenset(int(actor) for actor in actors)
    db = initialize(args.root / "agent.sqlite")
    ids = poll(db, bot, operators)
    print("New allowed requests:", len(ids))
    if not ids:
        print("No new allowed private text arrived during the bounded poll.")
    # Read durable work, including requests admitted by a prior process that
    # stopped before execution. The in-memory poll result is not the queue.
    queued = db.connection.execute(
        "SELECT id FROM assistant_work WHERE channel=? AND status='READY' "
        "ORDER BY created,rowid LIMIT 20",
        ("telegram:" + bot.account,),
    ).fetchall()
    results = []
    for row in queued:
        identifier = row[0]
        current = claim(db, "phone-checkpoint", identifier=identifier)
        if current is None:
            continue
        model = (
            HTTPModel(model=args.model, reasoning_effort="none")
            if args.live
            else OfflineShopModel()
        )
        passed, result = run_claim(db, current, model)
        results.append({"work": identifier, "draft_evidence": passed})
        if args.transcript:
            print(json.dumps(result.messages, indent=2))
    deliveries = []
    for _ in range(20):
        delivery = deliver_one(db, bot, operators)
        if delivery is None:
            break
        deliveries.append(delivery)
    for row in results:
        row["delivery"] = db.connection.execute(
            "SELECT delivery FROM assistant_work WHERE id=?", (row["work"],)
        ).fetchone()[0]
    print(
        json.dumps(
            {
                "results": results,
                "outbox_observations": deliveries,
                "scope": "bounded construction run; inspect the actual reply on your phone",
            },
            indent=2,
        )
    )
    db.close()
    return (
        0
        if (results or deliveries)
        and all(row["draft_evidence"] and row["delivery"] == "SENT" for row in results)
        and all(value == "SENT" for value in deliveries)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
