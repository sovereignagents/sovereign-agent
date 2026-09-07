"""The cumulative Lucy agent: one durable turn using the reader-owned loop."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from typing import Any

from reference_organizations.store.agent import DraftArguments, shop_dispatcher
from sovereign_agent import assistant_context, assistant_orders, assistant_work
from sovereign_agent.agent_loop import Limits, run_loop
from sovereign_agent.database import Database
from sovereign_agent.model_turn import Model
from sovereign_agent.tool_dispatch import Dispatcher, ExecutableTool


def run_once(
    db: Database,
    model: Model,
    *,
    owner: str | None = None,
    policy: assistant_orders.SpendingPolicy | None = None,
    supplier: assistant_orders.Supplier | None = None,
    limits: Limits | None = None,
) -> dict[str, Any]:
    limits = limits or Limits()
    work = assistant_work.claim(db, owner or uuid.uuid4().hex, ttl=limits.seconds + 10)
    if work is None:
        return {"status": "IDLE"}
    try:
        row = db.connection.execute(
            "SELECT * FROM assistant_work WHERE id=?", (work.id,)
        ).fetchone()
        assert row
        # Commands come from an allowlisted adapter, never a model-selected tool.
        if row["channel"] == "telegram" and work.prompt.startswith("/"):
            if policy is None or row["recipient"] not in policy.operators:
                raise PermissionError("operator command is not authorized")
            parts = work.prompt.split(maxsplit=2)
            if len(parts) == 3 and parts[0] == "/approve":
                assistant_orders.approve(
                    db,
                    parts[1],
                    parts[2],
                    actor=row["recipient"],
                    policy=policy,
                    expires=row["created"] + 3600,
                )
                with db.immediate() as connection:
                    connection.execute(
                        "UPDATE assistant_work SET status='READY' WHERE status='BLOCKED' "
                        "AND id=(SELECT work_id FROM assistant_orders WHERE id=?)",
                        (parts[1],),
                    )
                answer = "Approved that exact order for the remainder of this one-hour window."
            elif len(parts) == 3 and parts[0] == "/remember":
                assistant_context.remember(db, work.session, parts[1], parts[2], row["origin"])
                answer = "Preference saved with its message source."
            elif len(parts) == 2 and parts[0] == "/forget":
                assistant_context.forget(db, work.session, parts[1])
                answer = "Preference revisions erased. Historical reports and backups are separate."
            elif len(parts) == 2 and parts[0] == "/revoke":
                assistant_orders.revoke(db, parts[1], actor=row["recipient"], policy=policy)
                answer = (
                    "Approval revoked. Any already transmitted order still needs reconciliation."
                )
            else:
                answer = (
                    "Commands: /remember name value, /forget name, "
                    "/approve order digest, /revoke order."
                )
            assistant_work.finish(db, work, "DONE", answer)
            return {"status": "DONE", "work": work.id, "answer": answer}
        tools = shop_dispatcher(db)
        if supplier is not None:
            # Persisting a proposal has no remote effect and grants no permission.
            def proposal(args: DraftArguments) -> dict[str, Any]:
                identifier = assistant_orders.propose(db, work, args.sku, args.quantity)
                order = db.connection.execute(
                    "SELECT * FROM assistant_orders WHERE id=?", (identifier,)
                ).fetchone()
                assert order
                return {
                    "sku": args.sku,
                    "quantity": args.quantity,
                    "total_cents": order["amount"],
                    "status": order["status"],
                    "order": identifier,
                    "digest": order["digest"],
                }

            replacements = [tool for name, tool in tools.tools.items() if name != "draft_order"]
            replacements.append(
                ExecutableTool(
                    "draft_order",
                    "Prepare an exact order proposal; never purchases.",
                    DraftArguments,
                    proposal,
                )
            )
            tools = Dispatcher(replacements, allowed=tools.allowed)
        messages = assistant_context.context(db, work.session, work.prompt, allowed=tools.allowed)
        for message in messages:
            assistant_work.observe(db, work, message)
        result = run_loop(
            model,
            tools,
            messages,
            limits=limits,
            observe=lambda message: assistant_work.observe(db, work, message),
            check_current=lambda: assistant_work.assert_current(db.connection, work),
        )
        answer = result.answer or "The agent stopped: " + result.status
        state = "DONE" if result.status == "COMPLETED" else "BLOCKED"
        if supplier is not None:
            orders = db.connection.execute(
                "SELECT * FROM assistant_orders WHERE work_id=? ORDER BY created", (work.id,)
            ).fetchall()
            for order in orders:
                if (
                    order["status"] == "DRAFT"
                    and policy
                    and order["amount"] <= policy.automatic_order_pence
                ):
                    assistant_orders.approve(
                        db,
                        order["id"],
                        order["digest"],
                        actor=sorted(policy.operators)[0],
                        policy=policy,
                        expires=time.time() + 3600,
                        automatic=True,
                    )
                current = db.connection.execute(
                    "SELECT * FROM assistant_orders WHERE id=?", (order["id"],)
                ).fetchone()
                assert current
                if current["status"] in {"APPROVED", "SENDING", "UNKNOWN"}:
                    receipt = assistant_orders.execute(db, work, order["id"], supplier)
                    answer += f"\nOrder {order['id']}: {receipt['status']}."
                    if receipt["status"] == "UNKNOWN":
                        state = "BLOCKED"
                elif current["status"] == "DRAFT":
                    state = "BLOCKED"
                    answer += (
                        f"\nApproval needed: {current['amount']} pence. "
                        f"/approve {order['id']} {order['digest']}"
                    )
                else:
                    answer += f"\nOrder {order['id']}: {current['status']}."
        assistant_work.finish(db, work, state, answer)
        return {"status": state, "work": work.id, "answer": answer, "loop": asdict(result)}
    except PermissionError:
        # A stale worker must not overwrite its replacement's state or result.
        try:
            assistant_work.finish(
                db,
                work,
                "BLOCKED",
                "Authority changed; inspect current approvals and work ownership.",
            )
        except PermissionError:
            return {"status": "STALE", "work": work.id}
        return {"status": "BLOCKED", "work": work.id}
    except ValueError, OSError:
        assistant_work.finish(
            db,
            work,
            "BLOCKED",
            "A bounded operation failed; inspect the recorded work and retry explicitly.",
        )
        return {"status": "BLOCKED", "work": work.id}
