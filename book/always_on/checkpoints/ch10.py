"""Chapter 10: replace a killed owner, then fence an old owner that is still alive."""

import argparse
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

from reference_organizations.store.agent import seed_lucy
from reference_organizations.store.assistant import run_once
from reference_organizations.store.supplier import SupplierClient
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose
from sovereign_agent.assistant_work import claim, enqueue, finish, observe
from sovereign_agent.database import Database


def wait_until(check, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("bounded process observation timed out")


def old_worker(root, target):
    db = Database(root / "agent.sqlite")
    work = claim(db, "old-worker", ttl=2)
    assert work is not None
    supplier = SupplierClient(target)
    operation = propose(db, work, "SKU-VANILLA", 6, target=supplier.identity)
    digest = db.connection.execute("SELECT digest FROM assistant_orders").fetchone()[0]
    policy = SpendingPolicy(frozenset({"lucy"}), total_pence=2000)
    approve(db, operation, digest, actor="lucy", policy=policy, expires=time.time() + 60)
    expires = db.connection.execute("SELECT expires FROM assistant_work").fetchone()[0]
    temporary = root / "worker-ready.tmp"
    temporary.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "operation": operation,
                "work": work.id,
                "generation": work.generation,
                "expires": expires,
            }
        )
    )
    temporary.replace(root / "worker-ready.json")
    wait_until((root / "release-old").exists, seconds=15)
    blocked = []
    attempts = {
        "transcript": lambda: observe(db, work, {"role": "assistant", "content": "stale output"}),
        "completion": lambda: finish(db, work, "DONE", "stale completion"),
        "supplier": lambda: execute(db, work, operation, supplier, policy=policy),
    }
    for name, action in attempts.items():
        try:
            action()
        except PermissionError:
            blocked.append(name)
        else:
            raise AssertionError("stale owner succeeded at " + name)
    print(json.dumps({"stale_boundaries_refused": blocked}), flush=True)
    db.close()


class NoNewReasoning:
    def complete(self, *args, **kwargs):
        raise AssertionError("replacement must continue the existing approved record")


def experiment(root, *, kill):
    root.mkdir()
    supplier_context = runpy.run_path(str(Path(__file__).with_name("ch08.py")))["supplier_process"]
    with supplier_context(root) as (supplier, supplier_path):
        db = Database(root / "agent.sqlite")
        seed_lucy(db)
        identifier = enqueue(db, "morning", "lucy", "Replenish vanilla")
        # Only the child creates the claim and approval before becoming unavailable.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL"}
        }
        child = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker",
                str(root),
                "--supplier",
                supplier.endpoint,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=environment,
        )
        try:
            ready = root / "worker-ready.json"
            wait_until(lambda: ready.exists() or child.poll() is not None)
            assert ready.exists(), child.communicate(timeout=2)
            prior = json.loads(ready.read_text())
            assert prior["work"] == identifier and prior["generation"] == 1
            assert claim(db, "too-early") is None
            if kill:
                child.send_signal(signal.SIGKILL)
                child.communicate(timeout=3)
                assert child.returncode == -signal.SIGKILL
            else:
                assert child.poll() is None
            # Observe actual expiry; this case does not rewrite or fast-forward the ledger.
            wait_until(lambda: time.time() > prior["expires"] + 0.05)
            result = run_once(
                db,
                NoNewReasoning(),
                owner="replacement",
                supplier=supplier,
                policy=SpendingPolicy(frozenset({"lucy"}), total_pence=2000),
            )
            assert result["status"] == "DONE" and result["work"] == identifier
            current = db.connection.execute(
                "SELECT generation,owner,status FROM assistant_work"
            ).fetchone()
            assert tuple(current) == (2, "replacement", "DONE")
            boundaries = []
            if not kill:
                assert child.poll() is None
                (root / "release-old").touch(exist_ok=False)
                stdout, stderr = child.communicate(timeout=5)
                assert child.returncode == 0, stderr
                boundaries = json.loads(stdout)["stale_boundaries_refused"]
                assert boundaries == ["transcript", "completion", "supplier"]
            with sqlite3.connect(supplier_path) as remote:
                assert remote.execute("SELECT operation FROM orders").fetchall() == [
                    (prior["operation"],)
                ]
            assert tuple(
                db.connection.execute(
                    "SELECT reserved_pence,spent_pence FROM assistant_spending"
                ).fetchone()
            ) == (0, 1500)
            assert (
                db.connection.execute("SELECT count(*) FROM assistant_transcript").fetchone()[0]
                == 0
            )
            assert run_once(db, NoNewReasoning(), supplier=supplier)["status"] == "IDLE"
            return {
                "case": "killed" if kill else "still_alive",
                "initial_pid": prior["pid"],
                "observed_exit": child.returncode,
                "generation": current["generation"],
                "work_state": current["status"],
                "supplier_orders": 1,
                "spent_pence": 1500,
                "stale_boundaries_refused": boundaries,
                "new_model_calls": 0,
            }
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--supplier")
    parser.add_argument("--evidence", action="store_true")
    args = parser.parse_args()
    if args.worker:
        old_worker(args.worker, args.supplier)
        return
    with tempfile.TemporaryDirectory(prefix="lucy-worker-") as directory:
        root = Path(directory)
        results = [experiment(root / "killed", kill=True), experiment(root / "stale", kill=False)]
    print("Killed worker replaced:", results[0]["work_state"])
    print("Live stale worker refused:", len(results[1]["stale_boundaries_refused"]))
    print("Supplier orders in each isolated case:", *(item["supplier_orders"] for item in results))
    print("New model calls during recovery:", sum(item["new_model_calls"] for item in results))
    if args.evidence:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
