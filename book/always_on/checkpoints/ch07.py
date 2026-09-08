"""Chapter 7: durable clock jobs and stock episodes create draft work while unattended."""

import argparse
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from reference_organizations.store.agent import OfflineShopModel
from reference_organizations.store.assistant import run_once
from reference_organizations.store.stock_conditions import scan, watch
from sovereign_agent.assistant_work import schedule, tick, unschedule
from sovereign_agent.database import Database
from sovereign_agent.model_turn import HTTPModel


def observed_drafts(messages):
    names = {
        call["id"]: call["function"]["name"]
        for message in messages
        for call in message.get("tool_calls", [])
    }
    drafts = []
    for message in messages:
        if message["role"] == "tool" and names.get(message["tool_call_id"]) == "draft_order":
            value = json.loads(message["content"])
            if value.get("ok") is True:
                draft = value["value"]
                drafts.append((draft["sku"], draft["quantity"], draft["total_pence"]))
    return sorted(drafts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="use the actual local HTTP model, including the unattended child",
    )
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--transcript", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="lucy-wake-") as temporary:
        root = Path(temporary)
        previous = runpy.run_path(str(Path(__file__).with_name("ch06.py")))
        db = previous["initialize"](root / "agent.sqlite")
        model = (
            HTTPModel(model=args.model, reasoning_effort="none")
            if args.live
            else OfflineShopModel()
        )
        first_due = time.time() - 39
        observed = first_due + 39
        schedule(
            db, "morning", "lucy", previous["PROMPT"], first_due=first_due, interval_seconds=10
        )
        with db.immediate() as connection:
            connection.execute("UPDATE assistant_control SET paused=1")
        assert tick(db, now=observed) == []
        assert (
            db.connection.execute("SELECT next_due FROM assistant_jobs").fetchone()[0] == first_due
        )
        print("Pause preserved due job:", True)
        with db.immediate() as connection:
            connection.execute("UPDATE assistant_control SET paused=0")
        created = tick(db, now=observed)
        assert len(created) == 1 and tick(db, now=observed) == []
        event = json.loads(
            db.connection.execute(
                "SELECT payload FROM events WHERE kind='assistant.job.enqueued'"
            ).fetchone()[0]
        )
        print("Coalesced missed runs:", event["coalesced"])
        assert event["coalesced"] == 3
        whole_shop = run_once(db, model)
        assert whole_shop["status"] == "DONE"
        assert observed_drafts(whole_shop["loop"]["messages"]) == [
            ("SKU-STRAWBERRY", 4, 1100),
            ("SKU-VANILLA", 6, 1500),
        ]
        print("Morning draft evidence:", "PASS")
        unschedule(db, "morning")
        assert tick(db, now=observed + 100) == []
        watch(db, "vanilla-low", "lucy", "SKU-VANILLA")
        first = scan(db)
        assert len(first) == 1 and scan(db) == []
        scoped = run_once(db, model)
        assert scoped["status"] == "DONE"
        assert observed_drafts(scoped["loop"]["messages"]) == [("SKU-VANILLA", 6, 1500)]
        print("First stock episode:", "PASS")
        with db.immediate() as connection:
            connection.execute("UPDATE inventory SET on_hand=8 WHERE sku='SKU-VANILLA'")
        assert scan(db) == []
        with db.immediate() as connection:
            connection.execute("UPDATE inventory SET on_hand=1 WHERE sku='SKU-VANILLA'")
        assert (
            db.connection.execute("SELECT armed FROM assistant_stock_conditions").fetchone()[0] == 1
        )
        db.close()
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL"}
        }
        if args.live:
            environment.update(
                SOVEREIGN_AGENT_MODEL_MODE="live", SOVEREIGN_AGENT_LLM_MODEL=args.model
            )
        # No prompt argument, no credentials, and no supplier endpoint: the child
        # must discover the persisted condition and can only produce drafts.
        process = subprocess.Popen(
            [sys.executable, "-m", "sovereign_agent", "agent", "serve", "--root", str(root)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        db = Database(root / "agent.sqlite")
        try:
            deadline = time.monotonic() + (90 if args.live else 8)
            row = None
            while time.monotonic() < deadline and process.poll() is None:
                row = db.connection.execute(
                    "SELECT id,status,result FROM assistant_work "
                    "WHERE origin='stock-condition:vanilla-low:2'"
                ).fetchone()
                if row and row["status"] in {"DONE", "BLOCKED"}:
                    break
                time.sleep(0.02)
            assert row is not None and row["status"] == "DONE", (
                dict(row) if row else "no condition work"
            )
            messages = [
                json.loads(item[0])
                for item in db.connection.execute(
                    "SELECT message FROM assistant_transcript WHERE work_id=? ORDER BY rowid",
                    (row["id"],),
                )
            ]
            assert observed_drafts(messages) == [("SKU-VANILLA", 7, 1750)]
            assert row["result"] == (
                'Draft estimates:\n- "SKU-VANILLA": 7 tubs, £17.50 GBP.\nTotal: £17.50 GBP.'
            )
            print("Unattended second episode:", "PASS")
            print("Persisted draft amount:", "£17.50 GBP")
            assert (
                db.connection.execute(
                    "SELECT generation FROM assistant_stock_conditions"
                ).fetchone()[0]
                == 2
            )
            assert scan(db) == []
            print("Duplicate episode work:", 0)
            orders = db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0]
            print("Purchases:", orders)
            assert orders == 0
            if args.transcript:
                print(
                    json.dumps(
                        {
                            "morning": whole_shop["loop"]["messages"],
                            "first_episode": scoped["loop"]["messages"],
                            "unattended_episode": messages,
                            "displayed_reports": {
                                "morning": whole_shop["answer"],
                                "first_episode": scoped["answer"],
                                "unattended_episode": row["result"],
                            },
                        },
                        indent=2,
                    )
                )
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
            db.close()
        assert process.returncode == 0, (process.returncode, stderr)
        assert "STOPPED" in stdout
        print("Worker stopped cleanly:", True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
