"""The cumulative Lucy agent: one durable turn using the reader-owned loop."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from reference_organizations.store.agent import DraftArguments, draft_report, shop_dispatcher
from sovereign_agent import assistant_context, assistant_orders, assistant_work
from sovereign_agent.agent_loop import Limits, run_loop
from sovereign_agent.database import Database
from sovereign_agent.events import append_event
from sovereign_agent.model_turn import Model, ToolCall
from sovereign_agent.tool_dispatch import Dispatcher, ExecutableTool


def _orders(
    db: Database,
    work: assistant_work.Claim,
    supplier: assistant_orders.Supplier,
    policy: assistant_orders.SpendingPolicy | None,
    *,
    automatic: bool = False,
    should_stop: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    """Finish only when every persisted proposal has a conclusive disposition."""
    orders = db.connection.execute(
        "SELECT * FROM assistant_orders WHERE work_id=? ORDER BY created,id", (work.id,)
    ).fetchall()
    for order in orders:
        if should_stop():
            break
        if policy is None:
            continue
        if automatic and order["status"] == "DRAFT" and not order["revoked"]:
            if order["amount"] <= policy.automatic_order_pence:
                try:
                    assistant_orders.approve(
                        db,
                        order["id"],
                        order["digest"],
                        actor=sorted(policy.operators)[0],
                        policy=policy,
                        expires=time.time() + 3600,
                        automatic=True,
                    )
                except PermissionError:
                    # Insufficient aggregate allowance leaves an explicit pending draft.
                    continue
        current = db.connection.execute(
            "SELECT status FROM assistant_orders WHERE id=?", (order["id"],)
        ).fetchone()[0]
        if current in {"APPROVED", "SENDING", "UNKNOWN"}:
            if should_stop():
                break
            try:
                assistant_orders.execute(db, work, order["id"], supplier, policy=policy)
            except PermissionError:
                # Reconciliation can retain uncertainty after revocation. Preserve it;
                # a stale worker is rejected again by finish below.
                continue
    rows = db.connection.execute(
        "SELECT * FROM assistant_orders WHERE work_id=? ORDER BY created,id", (work.id,)
    ).fetchall()
    pending = any(row["status"] in {"DRAFT", "APPROVED", "SENDING", "UNKNOWN"} for row in rows)
    cancelled = db.connection.execute(
        "SELECT cancelled FROM assistant_work WHERE id=?", (work.id,)
    ).fetchone()[0]
    state = "BLOCKED" if pending else ("CANCELLED" if cancelled else "DONE")
    lines = ["Recorded order outcomes:"]
    for row in rows:
        lines.append(f"Order {row['id']}: {row['status']}, {row['amount']} pence.")
        if row["status"] == "DRAFT":
            lines.append(f"Approval required: /approve {row['id']} {row['digest']}")
    answer = "\n".join(lines)
    assistant_work.finish(db, work, state, answer)
    return {"status": state, "work": work.id, "answer": answer}


def run_once(
    db: Database,
    model: Model,
    *,
    owner: str | None = None,
    policy: assistant_orders.SpendingPolicy | None = None,
    supplier: assistant_orders.Supplier | None = None,
    limits: Limits | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    control_only: bool = False,
    extra_tools: tuple[ExecutableTool, ...] = (),
) -> dict[str, Any]:
    limits = limits or Limits()
    work = assistant_work.claim(
        db, owner or uuid.uuid4().hex, ttl=limits.seconds + 10, control_only=control_only
    )
    if work is None:
        return {"status": "IDLE"}
    try:
        row = db.connection.execute(
            "SELECT * FROM assistant_work WHERE id=?", (work.id,)
        ).fetchone()
        assert row
        # Commands come from an allowlisted adapter, never a model-selected tool.
        if row["channel"].startswith("telegram:") and work.prompt.startswith("/"):
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
                        "UPDATE assistant_work SET status='READY',available_after=0 "
                        "WHERE status='BLOCKED' "
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
            elif len(parts) == 2 and parts[0] == "/cancel":
                assistant_work.cancel(db, parts[1])
                answer = "Cancellation recorded; transmitted orders still need reconciliation."
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
        existing = db.connection.execute(
            "SELECT 1 FROM assistant_orders WHERE work_id=? AND status!='DRAFT' LIMIT 1",
            (work.id,),
        ).fetchone()
        if existing and supplier is not None:
            return _orders(db, work, supplier, policy, should_stop=should_stop)
        tools = shop_dispatcher(db, subject=work.subject)
        if supplier is not None:
            calculation = tools

            # Persisting a proposal has no remote effect and grants no permission.
            def proposal(args: DraftArguments) -> dict[str, Any]:
                assert supplier is not None
                checked = calculation.invoke(
                    ToolCall(id="validate-draft", name="draft_order", arguments=args.model_dump())
                )
                if not checked["ok"]:
                    raise ValueError("proposal must match the current deterministic stock need")
                identifier = assistant_orders.propose(
                    db, work, args.sku, args.quantity, target=supplier.identity
                )
                order = db.connection.execute(
                    "SELECT * FROM assistant_orders WHERE id=?", (identifier,)
                ).fetchone()
                assert order
                return {
                    "sku": args.sku,
                    "quantity": args.quantity,
                    "total_pence": order["amount"],
                    "currency": "GBP",
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
        if extra_tools:
            tools = Dispatcher(
                [*tools.tools.values(), *extra_tools],
                allowed=tools.allowed | frozenset(tool.name for tool in extra_tools),
            )
        messages = assistant_context.context(db, work.session, work.prompt, allowed=tools.allowed)
        with db.immediate():
            assistant_work.assert_current(db.connection, work)
            append_event(
                db,
                "assistant.context.assembled",
                {
                    "work": work.id,
                    "generation": work.generation,
                    "sha256": hashlib.sha256(
                        json.dumps(messages, sort_keys=True).encode()
                    ).hexdigest(),
                },
            )
        for message in messages:
            assistant_work.observe(db, work, message)
        result = run_loop(
            model,
            tools,
            messages,
            limits=limits,
            observe=lambda message: assistant_work.observe(db, work, message),
            check_current=lambda: assistant_work.assert_current(db.connection, work),
            should_stop=should_stop,
            reserve_call=lambda: assistant_work.reserve_model_call(
                db, work, limits.estimated_call_pence
            ),
        )
        if work.subject and result.status == "COMPLETED":
            requested = {
                call["id"]
                for message in result.messages
                for call in message.get("tool_calls", [])
                if call["function"]["name"] == "draft_order"
            }
            drafted = any(
                json.loads(message["content"]).get("ok") is True
                for message in result.messages
                if message["role"] == "tool" and message["tool_call_id"] in requested
            )
            stock = shop_dispatcher(db, subject=work.subject).invoke(
                ToolCall(id="outcome-check", name="list_stock", arguments={})
            )
            if (
                not stock["ok"]
                or not stock["value"]
                or (stock["value"][0]["needed"] > 0 and not drafted)
            ):
                answer = "Scoped replenishment stopped without the required successful draft."
                assistant_work.finish(db, work, "BLOCKED", answer)
                return {
                    "status": "BLOCKED",
                    "work": work.id,
                    "answer": answer,
                    "loop": asdict(result),
                }
        rendered = draft_report(result.messages) if result.status == "COMPLETED" else None
        answer = rendered or result.answer or "The agent stopped: " + result.status
        state = "DONE" if result.status == "COMPLETED" else "BLOCKED"
        if supplier is not None and result.status == "COMPLETED":
            has_orders = db.connection.execute(
                "SELECT 1 FROM assistant_orders WHERE work_id=? LIMIT 1", (work.id,)
            ).fetchone()
            if has_orders:
                outcome = _orders(
                    db, work, supplier, policy, automatic=True, should_stop=should_stop
                )
                return {**outcome, "loop": asdict(result)}
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


def reconcile_once(
    db: Database,
    supplier: assistant_orders.Supplier,
    policy: assistant_orders.SpendingPolicy,
    *,
    should_stop: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    """Read uncertain effects before new intake; never consult a model for recovery."""
    work = assistant_work.claim(db, uuid.uuid4().hex, recovery_only=True)
    if work is None:
        return {"status": "RECOVERY_WAIT"}
    try:
        return _orders(db, work, supplier, policy, should_stop=should_stop)
    except PermissionError:
        try:
            assistant_work.finish(
                db,
                work,
                "BLOCKED",
                "Reconciliation requires current authority or supplier evidence.",
            )
        except PermissionError:
            return {"status": "STALE", "work": work.id}
        return {"status": "BLOCKED", "work": work.id}
