"""Actual concurrent research and stock work, cancellation and bounded replacement."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from reference_organizations.store.agent import OfflineShopModel, seed_lucy
from reference_organizations.store.assistant import run_once as shop_once
from reference_organizations.store.delegation import (
    Inquiry,
    OfflineCateringModel,
    delegate,
    quote,
    run_once,
)
from sovereign_agent.assistant_work import cancel, claim, enqueue, reserve_model_call
from sovereign_agent.database import Database


def child():
    root = Path(sys.argv[2])
    identifier = sys.argv[3]
    gate = Path(sys.argv[4])
    output = Path(sys.argv[5])
    db = Database(root / "agent.sqlite")

    class WaitingModel(OfflineCateringModel):
        announced = False

        def complete(self, *args, **kwargs):
            if not self.announced:
                self.announced = True
                gate.with_suffix(".ready").write_text("model entered")
                end = time.monotonic() + 10
                while not gate.exists():
                    if time.monotonic() > end:
                        raise TimeoutError("test release not received")
                    time.sleep(0.01)
            return super().complete(*args, **kwargs)

    result = run_once(db, WaitingModel(), identifier=identifier)
    output.write_text(json.dumps(result))
    db.close()


def main():
    with tempfile.TemporaryDirectory(prefix="lucy-delegation-") as temporary:
        root = Path(temporary)
        db = Database(root / "agent.sqlite")
        seed_lucy(db)
        before = [
            tuple(r)
            for r in db.connection.execute(
                "SELECT sku,on_hand,reserved FROM inventory ORDER BY sku"
            )
        ]
        for guests, tubs, pence in (
            (1, 1, 500),
            (10, 1, 500),
            (11, 2, 1000),
            (41, 5, 2500),
            (200, 20, 10000),
        ):
            result = quote(db, Inquiry(sku="SKU-VANILLA", guests=guests))
            assert (result["tubs"], result["total_pence"]) == (tubs, pence)
        print("Authored quote boundary cases:", 5)
        for cancel_child in (False, True):
            label = "cancel" if cancel_child else "complete"
            parent = enqueue(db, "parent:" + label, "lucy", "Prepare the stock brief.")
            deadline = time.time() + 30
            inquiry = Inquiry(sku="SKU-VANILLA", guests=41)
            identifier = delegate(db, parent, inquiry, deadline=deadline, estimated_call_pence=7)
            assert (
                delegate(db, parent, inquiry, deadline=deadline, estimated_call_pence=7)
                == identifier
            )
            try:
                delegate(
                    db,
                    parent,
                    Inquiry(sku="SKU-VANILLA", guests=42),
                    deadline=deadline,
                    estimated_call_pence=7,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("changed handoff accepted")
            gate = root / (label + ".release")
            output = root / (label + ".json")
            env = {
                k: v
                for k, v in os.environ.items()
                if k in {"PATH", "SYSTEMROOT", "TMPDIR", "LANG", "LC_ALL"}
            }
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "child",
                    str(root),
                    identifier,
                    str(gate),
                    str(output),
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                end = time.monotonic() + 5
                while not gate.with_suffix(".ready").exists():
                    if process.poll() is not None:
                        raise AssertionError(process.communicate())
                    assert time.monotonic() < end, "research child did not claim"
                    time.sleep(0.01)
                assert (
                    db.connection.execute(
                        "SELECT status FROM assistant_work WHERE id=?", (identifier,)
                    ).fetchone()[0]
                    == "RUNNING"
                )
                assert shop_once(db, OfflineShopModel())["status"] == "DONE"
                assert (
                    db.connection.execute(
                        "SELECT status FROM assistant_work WHERE id=?", (parent,)
                    ).fetchone()[0]
                    == "DONE"
                )
                assert process.poll() is None
                print(label + ": stock done while research process waits", True)
                if cancel_child:
                    cancel(db, parent)
                gate.write_text("continue")
                process.communicate(timeout=5)
                assert process.returncode == 0
                result = json.loads(output.read_text())
                if cancel_child:
                    assert result["status"] == "AUTHORITY_STOP"
                    assert (
                        db.connection.execute(
                            "SELECT status FROM assistant_work WHERE id=?", (identifier,)
                        ).fetchone()[0]
                        == "CANCELLED"
                    )
                    assert (
                        db.connection.execute(
                            "SELECT count(*) FROM assistant_transcript WHERE work_id=?",
                            (identifier,),
                        ).fetchone()[0]
                        == 0
                    )
                    assert (
                        db.connection.execute(
                            "SELECT status FROM assistant_work WHERE id=?", (parent,)
                        ).fetchone()[0]
                        == "DONE"
                    )
                    print("Cancellation preserves completed stock result:", True)
                else:
                    assert result["status"] == "DONE"
                    report = result["report"]
                    assert report["quote"]["tubs"] == 5 and report["quote"]["total_pence"] == 2500
                    assert report["assignment_usage"] == {
                        "model_calls": 2,
                        "estimated_cost_pence": 14,
                    }
                    assert report["baseline"]["model_calls"] == 0
                    assert run_once(db, OfflineCateringModel(), identifier=identifier) == {
                        "status": "IDLE"
                    }
                    print("Child quote:", 5, "tubs", 2500, "pence; repeat research work", "IDLE")
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
        parent = enqueue(db, "parent:expired", "lucy", "brief")
        identifier = delegate(
            db, parent, Inquiry(sku="SKU-VANILLA", guests=1), deadline=time.time() + 0.1
        )
        time.sleep(0.15)
        assert run_once(db, OfflineCateringModel(), identifier=identifier) == {"status": "IDLE"}
        assert (
            db.connection.execute(
                "SELECT status FROM assistant_work WHERE id=?", (identifier,)
            ).fetchone()[0]
            == "CANCELLED"
        )
        print("Expired unclaimed work:", "CANCELLED")
        parent = enqueue(db, "parent:budget", "lucy", "brief")
        identifier = delegate(
            db,
            parent,
            Inquiry(sku="SKU-VANILLA", guests=1),
            deadline=time.time() + 30,
            model_calls=1,
            estimated_call_pence=5,
        )
        old = claim(db, "old-research", role="research", identifier=identifier, ttl=0.1)
        assert old is not None
        reserve_model_call(db, old, 5)
        time.sleep(0.15)
        replacement = claim(db, "replacement", role="research", identifier=identifier)
        assert replacement is not None and replacement.generation == old.generation + 1
        try:
            reserve_model_call(db, replacement, 5)
        except PermissionError:
            print("Replacement cannot reset assignment allowance:", True)
        else:
            raise AssertionError("assignment allowance reset")
        assert before == [
            tuple(r)
            for r in db.connection.execute(
                "SELECT sku,on_hand,reserved FROM inventory ORDER BY sku"
            )
        ]
        assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 0
        usage = db.connection.execute(
            "SELECT model_calls,estimated_cost_pence FROM assistant_daily WHERE session='lucy'"
        ).fetchone()
        assert tuple(usage) == (10, 26), tuple(usage)
        assert (
            db.connection.execute(
                "SELECT count(*) FROM assistant_daily WHERE model_calls>0 OR estimated_cost_pence>0"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.connection.execute(
                "SELECT coalesce(sum(model_calls),0)+coalesce(sum(estimated_cost_pence),0) "
                "FROM assistant_daily WHERE session!='lucy'"
            ).fetchone()[0]
            == 0
        )
        print("One shared billing account:", 10, "calls and", 26, "estimated pence")
        print("Purchases and stock reservations:", 0)
        print("Architecture decision: retain the function for this fixed calculation")
        db.close()


if __name__ == "__main__":
    child() if len(sys.argv) > 1 and sys.argv[1] == "child" else main()
