---
jupyter:
  jupytext:
    text_representation:
      extension: .md
      format_name: markdown
      format_version: '1.3'
  kernelspec:
    display_name: Python 3
    language: python
    name: python3
---

# Chapter 9, Unit A — Build durable intent and evidence

**Student edition v1 · 2026-09-09 · 75–90 minutes**

Lucy's supplier can accept an order and lose the reply. You will implement the local transitions around that uncertain interval, connect them to the real SQLite order schema and the simulated supplier, and save evidence for Unit B.

This unit starts only the repository's loopback supplier fixture. It cannot make a real purchase and uses no model, channel, or supplier credential.

## 1. Locate the cumulative code

```python tags=["setup"]
import json
import os
import runpy
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from reference_organizations.store.agent import seed_lucy
from sovereign_agent.assistant_orders import SpendingPolicy, approve, propose
from sovereign_agent.assistant_work import claim, enqueue
from sovereign_agent.database import Database

assert sys.version_info >= (3, 14)
start = Path(os.environ.get("SOVEREIGN_AGENT_REPO", Path.cwd())).resolve()
ROOT = next(
    (
        path
        for path in (start, *start.parents)
        if (path / "book/always_on/checkpoints/ch09.py").is_file()
    ),
    None,
)
if ROOT is None:
    raise RuntimeError("Set SOVEREIGN_AGENT_REPO to the Sovereign Agent checkout.")

independent_supplier = runpy.run_path(str(ROOT / "book/always_on/checkpoints/ch09.py"))[
    "independent_supplier"
]
```

Predict the two ledgers immediately after the supplier commits and drops the response. Which local amount remains reserved? How many remote orders exist?

## 2. Prepare one exact approved proposal

```python tags=["setup"]
POLICY = SpendingPolicy(frozenset({"lucy"}), total_pence=2_000)


def approved_order(root, *, target="fixture", sku="SKU-VANILLA", quantity=6):
    db = Database(root / "agent.sqlite")
    seed_lucy(db)
    enqueue(db, "chapter9:exercise", "lucy", "Replenish", subject=sku)
    work = claim(db, "chapter9-student")
    identifier = propose(db, work, sku, quantity, target=target)
    digest = db.connection.execute(
        "SELECT digest FROM assistant_orders WHERE id=?", (identifier,)
    ).fetchone()[0]
    approve(
        db,
        identifier,
        digest,
        actor="lucy",
        policy=POLICY,
        expires=time.time() + 60,
    )
    return db, work, identifier


def order_observation(db, identifier):
    row = db.connection.execute(
        "SELECT status,proposal,receipt FROM assistant_orders WHERE id=?", (identifier,)
    ).fetchone()
    money = db.connection.execute(
        "SELECT reserved_pence,spent_pence FROM assistant_spending WHERE id=1"
    ).fetchone()
    return {
        "status": row["status"],
        "proposal": json.loads(row["proposal"]),
        "receipt": json.loads(row["receipt"]) if row["receipt"] else None,
        "reserved_pence": money["reserved_pence"],
        "spent_pence": money["spent_pence"],
    }
```

## 3. Construct the durable transition

Implement three events:

- `ADMIT` changes one exact approved row to `SENDING` before the network call;
- `UNKNOWN` changes only `SENDING` to `UNKNOWN` while keeping the reservation;
- `RECEIPT` validates the operation, exact proposal, and conclusive status, then settles the reservation once.

Terminal receipt replay must be idempotent. Any unsupported transition, wrong prior state, mismatched receipt, or nonconclusive receipt must raise.

```python tags=["exercise", "learner-owned", "ch09-transition"]
def record_transition(db, work_id, identifier, event, receipt=None):
    """Record ADMIT, UNKNOWN, or RECEIPT and return the resulting observation."""
    return None
```

<details><summary>Hint 1 — the decision</summary>

Commit `SENDING` before any external call. A timeout changes knowledge to `UNKNOWN`; it does not release money. Only exact conclusive evidence can settle it.

</details>

<details><summary>Hint 2 — the evidence</summary>

Read `status`, `proposal`, `amount`, and `receipt` for the row whose `id` and `work_id` both match. Compare canonical JSON for the stored and returned proposals.

</details>

<details><summary>Hint 3 — the structure</summary>

Use `with db.immediate() as connection`. Branch on the event, reject invalid prior states, update the order, and for a first conclusive receipt subtract `amount` from reserved and add it to spent only when accepted.

</details>

## 4. Challenge the visible contract

```python tags=["assessment", "visible"]
def grade_transition(candidate):
    with tempfile.TemporaryDirectory(prefix="ch09-transition-visible-") as directory:
        db, work, identifier = approved_order(Path(directory))
        try:
            rows = []
            rows.append(candidate(db, work.id, identifier, "ADMIT"))
            rows.append(candidate(db, work.id, identifier, "UNKNOWN"))
            proposal = order_observation(db, identifier)["proposal"]
            receipt = {"operation": identifier, "proposal": proposal, "status": "ACCEPTED"}
            rows.append(candidate(db, work.id, identifier, "RECEIPT", receipt))
            rows.append(candidate(db, work.id, identifier, "RECEIPT", receipt))
            observed = [row["status"] for row in rows]
            money = rows[-1]["reserved_pence"], rows[-1]["spent_pence"]
            assert observed == ["SENDING", "UNKNOWN", "CONFIRMED", "CONFIRMED"]
            assert money == (0, 1500)
            mismatch = dict(receipt)
            mismatch["proposal"] = {**proposal, "quantity": 99}
            try:
                candidate(db, work.id, identifier, "RECEIPT", mismatch)
            except ValueError:
                pass
            else:
                raise AssertionError("mismatched receipt accepted")
            return {"status": "PASSED", "states": observed, "money": money}
        except Exception as error:
            return {"status": "NEEDS_WORK", "error": type(error).__name__}
        finally:
            db.close()


visible = grade_transition(record_transition)
VISIBLE_PASSED = visible["status"] == "PASSED"
print(json.dumps(visible, indent=2))
print("VISIBLE_CONTRACT", "PASSED" if VISIBLE_PASSED else "NEEDS_WORK")
```

## 5. Connect the transition to the supplier

The local `SENDING` commit happens first. The supplier then commits one remote receipt and closes the connection. Your `UNKNOWN` transition retains 1,500 pence. Reconciliation reads the supplier's existing receipt and records it without another order.

```python tags=["integration", "learner-path", "handoff"]
connected = None
if VISIBLE_PASSED:
    with tempfile.TemporaryDirectory(prefix="ch09-connected-") as directory:
        root = Path(directory)
        with independent_supplier(root) as (supplier, supplier_path):
            db, work, identifier = approved_order(root, target=supplier.identity)
            try:
                before_send = record_transition(db, work.id, identifier, "ADMIT")
                assert before_send["status"] == "SENDING"
                try:
                    supplier.order(identifier, before_send["proposal"])
                except OSError:
                    after_loss = record_transition(db, work.id, identifier, "UNKNOWN")
                else:
                    raise AssertionError("fixture did not drop the first response")
                with sqlite3.connect(supplier_path) as remote:
                    remote_count = remote.execute("SELECT count(*) FROM orders").fetchone()[0]
                found = supplier.lookup(identifier)
                final = record_transition(db, work.id, identifier, "RECEIPT", found)
                connected = {
                    "operation": identifier,
                    "proposal": final["proposal"],
                    "after_loss": after_loss,
                    "final": final,
                    "supplier_orders": remote_count,
                }
                assert after_loss["status"] == "UNKNOWN"
                assert (after_loss["reserved_pence"], after_loss["spent_pence"]) == (1500, 0)
                assert final["status"] == "CONFIRMED"
                assert (final["reserved_pence"], final["spent_pence"]) == (0, 1500)
                assert remote_count == 1
            finally:
                db.close()
    Path("ch09-unit-a-handoff-v1.json").write_text(
        json.dumps(connected, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("CONNECTED", connected["after_loss"]["status"], connected["final"]["status"])
else:
    print("CONNECTION_NOT_READY — repair record_transition, then run again.")
```

## Exit ticket

Explain why the local transaction cannot include the supplier commit, why `UNKNOWN` retains the reservation, and which exact evidence justifies `CONFIRMED`.

```python tags=["exercise-report"]
exercise_report = {
    "unit": "ch09-a",
    "attempted": 1,
    "completed": int(VISIBLE_PASSED),
    "failed": int(not VISIBLE_PASSED),
    "skipped": 0,
    "connection": "PASSED" if connected else "NOT_READY",
    "handoff": "WRITTEN" if connected else "NOT_WRITTEN",
}
print("EXERCISE_REPORT=" + json.dumps(exercise_report, sort_keys=True))
```
