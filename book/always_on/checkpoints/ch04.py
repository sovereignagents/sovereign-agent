"""Chapter 4: persistence, correction, and forgetting that changes future context."""

import argparse
import copy
import json
import runpy
import tempfile
from pathlib import Path

from reference_organizations.store.agent import OfflineShopModel, seed_lucy, shop_dispatcher
from sovereign_agent.agent_loop import run_loop
from sovereign_agent.assistant_context import context, forget, preferences, remember
from sovereign_agent.assistant_work import claim, enqueue, finish
from sovereign_agent.database import Database
from sovereign_agent.model_turn import HTTPModel


class ObservedModel:
    def __init__(self, model):
        self.model = model
        self.first_messages = None

    def complete(self, messages, tools, **kwargs):
        if self.first_messages is None:
            self.first_messages = copy.deepcopy(messages)
        return self.model.complete(messages, tools, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--transcript", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lucy-memory-") as temporary:
        path = Path(temporary) / "agent.sqlite"
        db = Database(path)
        seed_lucy(db)
        remember(db, "lucy", "supplier", "Ask for morning delivery", "lucy/message/1")
        db.close()
        db = Database(path)
        retained = preferences(db, "lucy", "delivery")[0]
        assert retained["source"] == "lucy/message/1"
        print("After reopening:", retained["value"])
        remember(db, "lucy", "supplier", "Ask for afternoon delivery", "lucy/message/2")
        print("After correction:", preferences(db, "lucy", "delivery")[0]["value"])
        remember(db, "lucy", "format", "three bullets", "lucy/message/3")
        enqueue(db, "old-turn", "lucy", "Prepare a brief")
        owner = claim(db, "first-worker")
        finish(db, owner, "DONE", "Lucy asks for afternoon delivery.")
        forget(db, "lucy", "supplier")
        selected = context(db, "lucy", "Prepare replenishment drafts.", allowed=frozenset())
        assert "afternoon delivery" not in selected[0]["content"]
        assert "three bullets" in selected[0]["content"]
        print("Forgotten value in future context:", "afternoon delivery" in selected[0]["content"])
        assert db.connection.execute("SELECT count(*) FROM assistant_work").fetchone()[0] == 1
        print("Operational record retained:", True)
        enqueue(db, "new-turn", "lucy", "Prepare replenishment drafts from current stock.")
        model = ObservedModel(
            HTTPModel(model=args.model, reasoning_effort="none")
            if args.live
            else OfflineShopModel()
        )
        previous = runpy.run_path(str(Path(__file__).with_name("ch03.py")))
        dispatcher = shop_dispatcher(db)
        messages = context(
            db, "lucy", previous["MESSAGES"][1]["content"], allowed=dispatcher.allowed
        )
        messages[0]["content"] = previous["MESSAGES"][0]["content"] + "\n" + messages[0]["content"]
        current = claim(db, "new-worker")
        result = run_loop(model, dispatcher, messages)
        assert model.first_messages is not None
        assert "three bullets" in model.first_messages[0]["content"]
        assert "afternoon delivery" not in model.first_messages[0]["content"]
        passed = previous["draft_evidence"](result)
        finish(db, current, "DONE" if passed else "BLOCKED", result.answer)
        print("Context reached the model:", True)
        print("Draft evidence:", "PASS" if passed else "FAIL")
        if args.transcript:
            print(json.dumps(result.messages, indent=2))
        db.close()
        return 0 if result.status == "COMPLETED" and passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
