"""Chapter 16: an accelerated shop day with independent supplier and worker processes."""

import argparse
import hashlib
import json
import os
import runpy
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from reference_organizations.store.agent import OfflineShopModel, seed_lucy
from reference_organizations.store.assistant import reconcile_once, run_once
from reference_organizations.store.delegation import Inquiry, delegate
from reference_organizations.store.operating_report import operating_report
from reference_organizations.store.stock_conditions import scan, watch
from reference_organizations.store.supplier import SupplierClient
from sovereign_agent import assistant_context as context
from sovereign_agent import assistant_orders as orders
from sovereign_agent import assistant_work as work
from sovereign_agent.agent_loop import Limits
from sovereign_agent.database import Database
from sovereign_agent.telegram_channel import deliver_one, poll

POLICY = orders.SpendingPolicy(frozenset({"123"}), total_pence=3000)
CHILD_ENV = {
    key: value
    for key, value in os.environ.items()
    if key in {"PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL", "PYTHONPATH"}
}


def wait_until(check, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.02)
    raise AssertionError("bounded day observation timed out")


class FailedModel:
    def complete(self, *args, **kwargs):
        raise OSError("injected model outage")


class NoNewReasoning:
    def complete(self, *args, **kwargs):
        raise AssertionError("existing approvals must recover from records")


class FixtureBot:
    account = "day-fixture"

    def __init__(self):
        self.updates = []
        self.sent = []

    def call(self, method, data):
        if method == "getUpdates":
            return self.updates
        self.sent.append(data)
        return {"message_id": len(self.sent)}


def message(identifier, text, actor=123):
    return {
        "update_id": identifier,
        "message": {
            "from": {"id": actor, "is_bot": False},
            "chat": {"id": actor, "type": "private"},
            "text": text,
        },
    }


def child(root, endpoint, identifier, operation):
    db = Database(root / "agent.sqlite")
    holder = work.claim(db, "day-worker", ttl=2, identifier=identifier)
    assert holder is not None
    response = orders.execute(
        db, holder, operation, SupplierClient(endpoint, timeout=1), policy=POLICY
    )
    assert response["status"] == "UNKNOWN"
    expiry = db.connection.execute(
        "SELECT expires FROM assistant_work WHERE id=?", (identifier,)
    ).fetchone()[0]
    staging = root / "child-ready.tmp"
    staging.write_text(json.dumps({"expiry": expiry, "operation": operation, "status": "UNKNOWN"}))
    staging.replace(root / "child-ready.json")
    time.sleep(20)
    raise AssertionError("parent should kill the worker after the persisted unknown outcome")


def cli(root, *arguments):
    return subprocess.run(
        [sys.executable, "-m", "sovereign_agent", "agent", *arguments, "--root", str(root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        env=CHILD_ENV,
    )


def day(root, checkpoint_dir):
    supplier_context = runpy.run_path(str(checkpoint_dir / "ch09.py"))["independent_supplier"]
    with supplier_context(root) as (supplier, supplier_path):
        db = Database(root / "agent.sqlite")
        research = worker = None
        try:
            seed_lucy(db)
            context.remember(db, "lucy", "currency", "Euros", "lucy/old-request")
            context.remember(db, "lucy", "currency", "GBP", "lucy/correction")
            assert context.preferences(db, "lucy", "currency")[0]["value"] == "GBP"
            due = time.time() - 1
            work.schedule(
                db,
                "morning",
                "lucy",
                "Prepare a stock brief.",
                first_due=due,
                interval_seconds=86400,
            )
            scheduled = work.tick(db)
            assert len(scheduled) == 1 and work.tick(db) == []
            failed = run_once(db, FailedModel(), limits=Limits(estimated_call_pence=2))
            assert failed["status"] == "BLOCKED"
            cli(root, "retry", failed["work"])
            morning = run_once(db, OfflineShopModel(), limits=Limits(estimated_call_pence=2))
            assert morning["status"] == "DONE"
            bot = FixtureBot()
            bot.updates = [
                message(1, "Prepare a stock brief."),
                message(1, "Prepare a stock brief."),
                message(2, "Spend everything", actor=999),
            ]
            assert len(poll(db, bot, frozenset({123}))) == 1
            db.close()
            db = Database(root / "agent.sqlite")
            assert poll(db, bot, frozenset({123})) == []
            assert (
                run_once(db, OfflineShopModel(), limits=Limits(estimated_call_pence=2))["status"]
                == "DONE"
            )
            assert deliver_one(db, bot, frozenset({123})) == "SENT" and len(bot.sent) == 1
            for sku in ("SKU-VANILLA", "SKU-STRAWBERRY"):
                watch(db, "watch:" + sku, "lucy", sku)
            assert len(scan(db)) == 2 and scan(db) == []
            for _ in range(2):
                assert (
                    run_once(
                        db,
                        OfflineShopModel(),
                        supplier=supplier,
                        policy=POLICY,
                        limits=Limits(estimated_call_pence=2),
                    )["status"]
                    == "BLOCKED"
                )
            proposals = {
                json.loads(row["proposal"])["sku"]: dict(row)
                for row in db.connection.execute("SELECT * FROM assistant_orders")
            }
            assert {sku: row["amount"] for sku, row in proposals.items()} == {
                "SKU-VANILLA": 1500,
                "SKU-STRAWBERRY": 1100,
            }
            assert all(row["status"] == "DRAFT" for row in proposals.values())
            with sqlite3.connect(supplier_path) as remote:
                assert remote.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
            assignment = delegate(
                db,
                morning["work"],
                Inquiry(sku="SKU-VANILLA", guests=41),
                deadline=time.time() + 60,
                estimated_call_pence=2,
                budget_pence=20,
            )
            research = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "sovereign_agent",
                    "agent",
                    "research-work",
                    assignment,
                    "--root",
                    str(root),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=CHILD_ENV,
            )
            bot.updates = [
                message(10 + index, f"/approve {row['id']} {row['digest']}")
                for index, row in enumerate(proposals.values())
            ]
            assert len(poll(db, bot, frozenset({123}))) == 2
            for _ in range(2):
                assert (
                    run_once(db, NoNewReasoning(), policy=POLICY, control_only=True)["status"]
                    == "DONE"
                )
            vanilla = proposals["SKU-VANILLA"]
            worker = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    str(root),
                    "--supplier",
                    supplier.endpoint,
                    "--work",
                    vanilla["work_id"],
                    "--order",
                    vanilla["id"],
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=CHILD_ENV,
            )
            ready = root / "child-ready.json"
            wait_until(lambda: ready.exists() or worker.poll() is not None)
            assert ready.exists(), worker.communicate(timeout=2)
            observed = json.loads(ready.read_text())
            with sqlite3.connect(supplier_path) as remote:
                assert remote.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
            worker.send_signal(signal.SIGKILL)
            worker.communicate(timeout=3)
            assert worker.returncode == -signal.SIGKILL
            wait_until(lambda: time.time() > observed["expiry"] + 0.05)
            assert reconcile_once(db, supplier, POLICY)["status"] == "DONE"
            second = run_once(db, NoNewReasoning(), supplier=supplier, policy=POLICY)
            assert second["status"] == "BLOCKED"
            # The fixture loses the first response for each new operation.
            retry_at = db.connection.execute(
                "SELECT available_after FROM assistant_work WHERE id=?", (second["work"],)
            ).fetchone()[0]
            wait_until(lambda: time.time() >= retry_at)
            assert reconcile_once(db, supplier, POLICY)["status"] == "DONE"
            stdout, stderr = research.communicate(timeout=10)
            assert research.returncode == 0, stderr
            assert json.loads(stdout)["status"] == "DONE"
            quote = json.loads(stdout)["report"]
            assert quote["quote"]["tubs"] == 5 and quote["quote"]["total_pence"] == 2500
            orders.receive(db, vanilla["id"], "day-delivery-vanilla", actor="123", policy=POLICY)
            orders.receive(db, vanilla["id"], "day-delivery-vanilla", actor="123", policy=POLICY)
            assert scan(db) == []
            while deliver_one(db, bot, frozenset({123})) is not None:
                pass
            with sqlite3.connect(supplier_path) as remote:
                remote_rows = remote.execute(
                    "SELECT operation,proposal FROM orders ORDER BY operation"
                ).fetchall()
            assert {operation for operation, _ in remote_rows} == {
                row["id"] for row in proposals.values()
            }
            assert (
                sum(
                    json.loads(raw)["quantity"] * json.loads(raw)["unit_cost_pence"]
                    for _, raw in remote_rows
                )
                == 2600
            )
            report = operating_report(db)
            assert report["orders"] == {"CONFIRMED": 1, "DELIVERED": 1}
            assert report["spending"] == {
                "accepted_pence": 2600,
                "reserved_pence": 0,
                "order_totals_match": True,
            }
            assert report["pending_work"] == [] and report["exceptions"] == []
            assert [(s["on_hand"], s["on_order"], s["needed"]) for s in report["stock"]] == [
                (12, 0, 0),
                (1, 4, 0),
                (8, 0, 0),
            ]
            assert report["research_quotes_completed"] == 1
            rendered = cli(root, "report").stdout
            assert "GBP 26.00" in rendered and "GBP 0.00" in rendered
            assert "4 pending replenishment" in rendered
            evidence = {
                "scope": (
                    "Accelerated deterministic business day; actual supplier and worker processes, "
                    "fixture Telegram transport. No live phone, real purchases or uptime claim."
                ),
                "faults": [
                    "model outage",
                    "duplicate message",
                    "unauthorized message",
                    "stale preference corrected",
                    "supplier response loss",
                    "worker SIGKILL",
                ],
                "independent_supplier_orders": len(remote_rows),
                "independent_supplier_pence": 2600,
                "killed_worker_exit": worker.returncode,
                "report": report,
                "manuscript_checkpoint_sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
            }
            (root / "report.txt").write_text(rendered)
            (root / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(rendered, end="")
            print(
                "Independent supplier: 2 orders, 2600 pence; killed worker replaced; "
                "duplicate delivery receipt counted once."
            )
        finally:
            for process in (worker, research):
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--supplier")
    parser.add_argument("--work")
    parser.add_argument("--order")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        child(args.worker, args.supplier, args.work, args.order)
        return
    checkpoint_dir = Path(__file__).resolve().parent
    if not (checkpoint_dir / "ch09.py").exists():
        checkpoint_dir = Path("book/always_on/checkpoints")
    if args.output:
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        day(args.output.resolve(), checkpoint_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="lucy-day-") as temporary:
            day(Path(temporary), checkpoint_dir)


if __name__ == "__main__":
    main()
