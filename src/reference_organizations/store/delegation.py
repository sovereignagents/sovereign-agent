"""One read-only catering worker; compare its result with the ordinary function."""

from __future__ import annotations

import json
import math
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from pydantic import Field

from reference_organizations.store.agent import NoArguments
from sovereign_agent import assistant_work as work_records
from sovereign_agent.agent_loop import Limits, run_loop
from sovereign_agent.database import Database
from sovereign_agent.events import append_event
from sovereign_agent.model_turn import Message, Model, ModelTurn, ToolCall
from sovereign_agent.tool_dispatch import Dispatcher, ExecutableTool


class Inquiry(NoArguments):
    sku: str = Field(min_length=1, max_length=100)
    guests: int = Field(ge=1, le=200)


def quote(db: Database, inquiry: Inquiry) -> dict[str, Any]:
    """Ten portions per tub is Lucy's authored catering fixture, not a model estimate."""
    row = db.connection.execute(
        "SELECT record FROM products WHERE sku=?", (inquiry.sku,)
    ).fetchone()
    if row is None:
        raise ValueError("unknown catering product")
    price = json.loads(row[0])["price_cents"]
    if type(price) is not int or price <= 0:
        raise ValueError("invalid catalog selling price")
    tubs = (inquiry.guests + 9) // 10
    return {
        "sku": inquiry.sku,
        "guests": inquiry.guests,
        "portions_per_tub": 10,
        "tubs": tubs,
        "total_pence": tubs * price,
        "currency": "GBP",
        "status": "DRAFT_QUOTE",
        "stock_reserved": False,
    }


def delegate(
    db: Database,
    parent: str,
    inquiry: Inquiry,
    *,
    deadline: float,
    model_calls: int = 4,
    estimated_call_pence: int = 0,
    budget_pence: int = 100,
) -> str:
    if (
        not math.isfinite(deadline)
        or not time.time() < deadline <= time.time() + 3600
        or type(model_calls) is not int
        or not 1 <= model_calls <= 8
        or type(estimated_call_pence) is not int
        or estimated_call_pence < 0
        or type(budget_pence) is not int
        or not 1 <= budget_pence <= 1000
    ):
        raise ValueError("bounded delegation contract required")
    encoded = inquiry.model_dump_json()
    with db.immediate() as connection:
        source = connection.execute("SELECT * FROM assistant_work WHERE id=?", (parent,)).fetchone()
        if (
            source is None
            or source["role"] != "shop"
            or source["cancelled"]
            or source["status"] == "REJECTED"
            or connection.execute("SELECT paused FROM assistant_control").fetchone()[0]
        ):
            raise PermissionError("eligible shop parent required; delegation cannot recurse")
        quote(db, inquiry)
        existing = connection.execute(
            "SELECT d.*,w.prompt FROM assistant_delegations d JOIN assistant_work w "
            "ON w.id=d.work_id WHERE d.parent_id=?",
            (parent,),
        ).fetchone()
        if existing:
            if (
                existing["prompt"],
                existing["deadline"],
                existing["model_calls_limit"],
                existing["estimated_call_pence"],
                existing["budget_pence"],
            ) != (encoded, deadline, model_calls, estimated_call_pence, budget_pence):
                raise ValueError("parent already has a different immutable assignment")
            return str(existing["work_id"])
        child = work_records._enqueue(
            connection,
            "delegation:" + parent,
            "research:" + parent,
            encoded,
            time.time(),
            source["channel"],
            source["recipient"],
            require_admission=True,
            role="research",
            billing_session=source["billing_session"] or source["session"],
        )
        connection.execute(
            "INSERT INTO assistant_delegations(work_id,parent_id,deadline,model_calls_limit,"
            "estimated_call_pence,budget_pence) VALUES (?,?,?,?,?,?)",
            (child, parent, deadline, model_calls, estimated_call_pence, budget_pence),
        )
        append_event(db, "assistant.delegation.created", {"parent": parent, "child": child})
        return child


def expire(db: Database) -> None:
    """Cancel expired contracts even when no worker claimed them or a model failed."""
    with db.immediate() as connection:
        rows = connection.execute(
            "SELECT w.id FROM assistant_work w JOIN assistant_delegations d ON d.work_id=w.id "
            "JOIN assistant_work p ON p.id=d.parent_id WHERE "
            "w.status IN ('READY','RUNNING','BLOCKED') AND (d.deadline<=? OR p.cancelled=1)",
            (time.time(),),
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE assistant_work SET status='CANCELLED',cancelled=1,"
                "generation=generation+1,result='Delegation expired or parent cancelled.' "
                "WHERE id=?",
                (row[0],),
            )
            append_event(db, "assistant.delegation.expired", {"work": row[0]})


class OfflineCateringModel:
    def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn:
        if messages[-1]["role"] != "tool":
            return ModelTurn(
                calls=(
                    ToolCall(
                        id="quote-1",
                        name="catering_quote",
                        arguments=json.loads(messages[1]["content"]),
                    ),
                )
            )
        return ModelTurn(content="The draft quote is ready; no stock or purchase was committed.")


def run_once(
    db: Database,
    model: Model,
    *,
    identifier: str = "",
    should_stop: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    expire(db)
    if should_stop():
        return {"status": "STOPPED"}
    work = work_records.claim(db, uuid.uuid4().hex, role="research", identifier=identifier)
    if work is None:
        return {"status": "IDLE"}
    contract = db.connection.execute(
        "SELECT * FROM assistant_delegations WHERE work_id=?", (work.id,)
    ).fetchone()
    if contract is None:
        raise ValueError("research work has no assignment contract")
    inquiry = Inquiry.model_validate_json(work.prompt)
    baseline_start = time.monotonic()
    baseline = quote(db, inquiry)
    baseline_seconds = time.monotonic() - baseline_start
    observations: list[dict[str, Any]] = []

    def calculate(arguments: Inquiry) -> dict[str, Any]:
        if arguments != inquiry:
            raise PermissionError("quote differs from immutable inquiry")
        value = quote(db, inquiry)
        observations.append(value)
        return value

    dispatcher = Dispatcher(
        [
            ExecutableTool(
                "catering_quote",
                "Calculate this assignment's read-only draft quote.",
                Inquiry,
                calculate,
            )
        ],
        allowed=frozenset({"catering_quote"}),
    )
    started = time.monotonic()
    try:
        remaining = contract["deadline"] - time.time()
        if remaining <= 0:
            raise PermissionError("delegation expired")
        result = run_loop(
            model,
            dispatcher,
            [
                {
                    "role": "system",
                    "content": "Prepare a catering draft using catering_quote. "
                    "You cannot reserve stock, buy supplies, or delegate.",
                },
                {"role": "user", "content": work.prompt},
            ],
            limits=Limits(
                model_calls=contract["model_calls_limit"],
                tool_calls=4,
                seconds=min(60, remaining),
                estimated_call_pence=contract["estimated_call_pence"],
                model_budget_pence=contract["budget_pence"],
            ),
            check_current=lambda: work_records.assert_current(db.connection, work),
            reserve_call=lambda: work_records.reserve_model_call(
                db, work, contract["estimated_call_pence"]
            ),
            observe=lambda message: work_records.observe(db, work, message),
            should_stop=should_stop,
        )
        if result.status == "STOP_REQUESTED":
            with db.immediate() as connection:
                work_records.assert_current(connection, work)
                connection.execute(
                    "UPDATE assistant_work SET status='READY',owner=NULL,expires=NULL WHERE id=?",
                    (work.id,),
                )
            return {"status": "STOPPED", "work": work.id}
        passed = (
            result.status == "COMPLETED" and bool(observations) and observations[-1] == baseline
        )
        report = {
            "passed": passed,
            "quote": observations[-1] if observations else None,
            "model_answer": result.answer,
            "loop": asdict(result),
            "baseline": {"quote": baseline, "model_calls": 0, "seconds": baseline_seconds},
            "seconds": time.monotonic() - started,
            "decision": "Retain the function for this fixed calculation; model prose is ungraded.",
            "assignment_usage": dict(
                db.connection.execute(
                    "SELECT d.model_calls,w.estimated_cost_pence FROM assistant_delegations d "
                    "JOIN assistant_work w ON w.id=d.work_id WHERE d.work_id=?",
                    (work.id,),
                ).fetchone()
            ),
        }
        status = "DONE" if passed else "BLOCKED"
        # Channel delivery uses a deterministic statement of the validated observation.
        answer = (
            (
                f"Catering draft: {baseline['tubs']} tubs for {inquiry.guests} guests, "
                f"GBP {baseline['total_pence'] / 100:.2f}. No stock reserved."
            )
            if passed
            else ("Catering research did not produce verified quote evidence.")
        )
        with db.immediate():
            work_records.assert_current(db.connection, work)
            append_event(db, "assistant.delegation.evaluated", {"work": work.id, "report": report})
        work_records.finish(db, work, status, answer)
        return {"status": status, "work": work.id, "report": report}
    except PermissionError:
        expire(db)
        # A stale worker must never finish or cancel a replacement's claim.
        try:
            work_records.finish(db, work, "BLOCKED", "Delegation authority or allowance exhausted.")
        except PermissionError:
            pass
        return {"status": "AUTHORITY_STOP", "work": work.id}
