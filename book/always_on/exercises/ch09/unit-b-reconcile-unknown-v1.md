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

# Chapter 9, Unit B — Survive the ambiguous order

**Student edition v1 · 2026-09-09 · 75–90 minutes**

Unit A preserved one exact intent and later settled it from supplier evidence. Now you will make a plausible retry bug create two remote purchases, repair the real order boundary, and adapt a second supplier's discovery shape without changing the meaning of its receipt.

This unit runs reviewed repository code in bounded local subprocesses and starts only in-memory or loopback supplier fixtures. A subprocess is not a security sandbox.

## 1. Verify the handoff and load the real experiment

```python tags=["setup", "handoff-consumer"]
import json
import os
import runpy
import sys
import tempfile
import time
from pathlib import Path

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

HANDOFF_PATH = Path("ch09-unit-a-handoff-v1.json")
handoff_status = "MISSING"
if HANDOFF_PATH.is_file():
    handoff = json.loads(HANDOFF_PATH.read_text(encoding="utf-8"))
    valid_handoff = (
        handoff.get("after_loss", {}).get("status") == "UNKNOWN"
        and handoff.get("final", {}).get("status") == "CONFIRMED"
        and handoff.get("supplier_orders") == 1
    )
    handoff_status = "VERIFIED" if valid_handoff else "INVALID"
print("UNIT_A_HANDOFF", handoff_status)

support = runpy.run_path(str(ROOT / "book/always_on/educator/runtime_labs_v1.py"))
RuntimeLab = support["RuntimeLab"]
```

Predict the broken observation before running it. If a retry invents a new operation ID, what can lookup of the original ID discover? How many supplier rows remain?

## 2. Break the real source copy

```python tags=["failure-experiment"]
lab = RuntimeLab(ROOT, 9)
baseline = lab.run("BASELINE", expected=lab.spec["expected_baseline"])
lab.break_source()
broken = lab.run("BROKEN", expected=lab.spec["expected_broken"])
print(json.dumps({"baseline": baseline["observation"], "broken": broken["observation"]}, indent=2))
assert baseline["status"] == "PASS"
assert broken["status"] == "PASS"
```

The fault replaces the stable operation ID at the actual `supplier.order` call. The supplier accepts two distinct effects while both local attempts remain `UNKNOWN`.

## 3. Construct the repair

Return the complete replacement for the one broken fragment. The starter preserves the unsafe fresh-ID send.

```python tags=["exercise", "learner-owned", "ch09-repair"]
def repair_fragment():
    return 'receipt = supplier.order(uuid.uuid4().hex, json.loads(row["proposal"]))'
```

<details><summary>Hint 1 — the decision</summary>

Retries for one intended purchase keep one operation identity. A new business purchase needs a new work item.

</details>

<details><summary>Hint 2 — the evidence</summary>

Compare `supplier_order_count` and `local_statuses` in the baseline and broken records. Read the marked line in `lab.source_excerpt()`.

</details>

<details><summary>Hint 3 — the structure</summary>

Call `supplier.order` with the existing `identifier` and the stored proposal. Do not generate another UUID or change the expected data.

</details>

```python tags=["integration", "learner-path"]
lab.repair(repair_fragment())
student_repair = lab.run("STUDENT_REPAIR", expected=lab.spec["expected_baseline"])
REPAIR_PASSED = student_repair["status"] == "PASS"
print(json.dumps(student_repair["observation"], indent=2))
print("REAL_SOURCE_REPAIR", "PASSED" if REPAIR_PASSED else "NEEDS_WORK")
lab.close()
```

State a diagnosis that this result could falsify. Printing the expected dictionary, changing expected data, or returning a canned tool result does not alter the independently observed supplier database.

## 4. Adapt another supplier's discovery evidence

The partner returns `order_ref`, `payload`, and `decision`. Implement the adapter boundary that converts `None`, `accepted`, or `declined` into the exact internal receipt shape. Reject unknown decisions rather than guessing.

```python tags=["exercise", "learner-owned", "ch09-adapter"]
def normalize_discovery(raw):
    return raw
```

<details><summary>Hint 1 — the decision</summary>

Normalize vocabulary at the integration boundary. Keep the stable operation and exact proposal unchanged.

</details>

<details><summary>Hint 2 — the evidence</summary>

Internal receipts use `operation`, `proposal`, and an uppercase conclusive `status`. An absent lookup stays `None`.

</details>

<details><summary>Hint 3 — the structure</summary>

Return `None` unchanged. Map `accepted` to `ACCEPTED` and `declined` to `REJECTED`; raise `ValueError` for any other decision.

</details>

```python tags=["assessment", "visible"]
partner_proposal = {
    "sku": "SKU-VANILLA",
    "quantity": 6,
    "unit_cost_pence": 250,
    "supplier": "lucy-local",
    "currency": "GBP",
}
expected_partner = {
    "operation": "partner-order-1",
    "proposal": partner_proposal,
    "status": "ACCEPTED",
}
try:
    VISIBLE_ADAPTER_PASSED = (
        normalize_discovery(None) is None
        and normalize_discovery(
            {
                "order_ref": "partner-order-1",
                "payload": partner_proposal,
                "decision": "accepted",
            }
        )
        == expected_partner
    )
except Exception:
    VISIBLE_ADAPTER_PASSED = False
print("VISIBLE_ADAPTER", "PASSED" if VISIBLE_ADAPTER_PASSED else "NEEDS_WORK")
```

## 5. Connect the adapter to the real order workflow

The partner makes its result discoverable only after `order` has been attempted. The second call to the real `execute` path must look up that evidence before considering another send.

```python tags=["setup", "integration", "learner-path"]
from reference_organizations.store.agent import seed_lucy
from sovereign_agent.assistant_orders import SpendingPolicy, approve, execute, propose
from sovereign_agent.assistant_work import claim, enqueue
from sovereign_agent.database import Database


class PartnerSupplier:
    idempotent = True
    identity = "partner-v2"
    timeout = 1.0

    def __init__(self, normalizer, decision):
        self.normalizer = normalizer
        self.decision = decision
        self.receipts = {}
        self.events = []

    def order(self, operation, proposal):
        self.events.append(("order", operation))
        self.receipts.setdefault(
            operation,
            {"order_ref": operation, "payload": proposal, "decision": self.decision},
        )
        raise OSError("partner committed but reply was lost")

    def lookup(self, operation):
        self.events.append(("lookup", operation))
        return self.normalizer(self.receipts.get(operation))


def run_partner_fixture(normalizer, decision):
    with tempfile.TemporaryDirectory(prefix="ch09-partner-") as directory:
        db = Database(Path(directory) / "agent.sqlite")
        supplier = PartnerSupplier(normalizer, decision)
        policy = SpendingPolicy(frozenset({"lucy"}), total_pence=2_000)
        try:
            seed_lucy(db)
            enqueue(db, "chapter9:partner", "lucy", "Replenish", subject="SKU-VANILLA")
            work = claim(db, "chapter9-partner-worker")
            identifier = propose(db, work, "SKU-VANILLA", 6, target=supplier.identity)
            digest = db.connection.execute(
                "SELECT digest FROM assistant_orders WHERE id=?", (identifier,)
            ).fetchone()[0]
            approve(
                db,
                identifier,
                digest,
                actor="lucy",
                policy=policy,
                expires=time.time() + 60,
            )
            first = execute(db, work, identifier, supplier, policy=policy)
            second = execute(db, work, identifier, supplier, policy=policy)
            status = db.connection.execute(
                "SELECT status FROM assistant_orders WHERE id=?", (identifier,)
            ).fetchone()[0]
            money = tuple(
                db.connection.execute(
                    "SELECT reserved_pence,spent_pence FROM assistant_spending WHERE id=1"
                ).fetchone()
            )
            return {
                "statuses": [first["status"], second["status"]],
                "local_status": status,
                "events": [event for event, _ in supplier.events],
                "supplier_orders": len(supplier.receipts),
                "money": money,
            }
        finally:
            db.close()


partner_result = None
if REPAIR_PASSED and VISIBLE_ADAPTER_PASSED:
    partner_result = run_partner_fixture(normalize_discovery, "accepted")
    print(json.dumps(partner_result, indent=2))
    assert partner_result == {
        "statuses": ["UNKNOWN", "ACCEPTED"],
        "local_status": "CONFIRMED",
        "events": ["order", "lookup"],
        "supplier_orders": 1,
        "money": (0, 1500),
    }
else:
    print("TRANSFER_NOT_READY — repair both learner-owned mechanisms.")
```

The event order is evidence: no receipt existed until after `order`; reconciliation then used `lookup`; no second `order` began.

## Exit ticket

Explain why a local transaction cannot guarantee exactly-once external effects. Name the supplier properties this result depends on, and state what the system must do if discovery is unavailable and retransmission is not idempotent.

```python tags=["exercise-report"]
exercise_report = {
    "unit": "ch09-b",
    "attempted": 2,
    "completed": int(REPAIR_PASSED) + int(VISIBLE_ADAPTER_PASSED),
    "failed": int(not REPAIR_PASSED) + int(not VISIBLE_ADAPTER_PASSED),
    "skipped": 0,
    "connection": "PASSED" if partner_result else "NOT_READY",
    "handoff": handoff_status,
}
print("EXERCISE_REPORT=" + json.dumps(exercise_report, sort_keys=True))
```
