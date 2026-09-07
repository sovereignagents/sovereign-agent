"""Resume a restored shop only after a fenced account export and current stock observations."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Self

from pydantic import Field, model_validator

from reference_organizations.store.agent import NoArguments
from reference_organizations.store.supplier import Proposal, SupplierClient
from sovereign_agent.assistant_orders import SpendingPolicy
from sovereign_agent.database import Database
from sovereign_agent.events import append_event


class StockCount(NoArguments):
    on_hand: int = Field(ge=0, le=100_000)
    reserved: int = Field(ge=0, le=100_000)

    @model_validator(mode="after")
    def bounded_reservation(self) -> Self:
        if self.reserved > self.on_hand:
            raise ValueError("reserved physical stock exceeds the recount")
        return self


class DeliveryObservation(NoArguments):
    received: bool
    reference: str = Field(max_length=200)

    @model_validator(mode="after")
    def exact_observation(self) -> Self:
        if self.received != bool(self.reference.strip()):
            raise ValueError("received deliveries need a reference; pending deliveries need none")
        return self


class ModelGrant(NoArguments):
    calls: int = Field(ge=0, le=100)
    estimated_pence: int = Field(ge=0, le=1000)


class RecoveryPlan(NoArguments):
    authority_epoch: str = Field(pattern="^[a-f0-9]{32}$")
    account: str = Field(pattern="^[a-f0-9]{32}$")
    observed_at: float = Field(gt=0, allow_inf_nan=False)
    inventory: dict[str, StockCount]
    deliveries: dict[str, DeliveryObservation]
    model_grants: dict[str, ModelGrant]


def configured_supplier(db: Database, endpoint: str) -> SupplierClient:
    client = SupplierClient(endpoint)
    row = db.connection.execute(
        "SELECT * FROM assistant_supplier_bindings WHERE target=?", (client.identity,)
    ).fetchone()
    if row:
        return SupplierClient(endpoint, account=row["account"], epoch=row["epoch"])
    if db.connection.execute("SELECT count(*) FROM assistant_supplier_bindings").fetchone()[0]:
        raise ValueError("the teaching shop supports one bound supplier account")
    if db.connection.execute("SELECT paused FROM assistant_control").fetchone()[0]:
        raise PermissionError("restored state cannot invent a missing supplier binding")
    info = client.account_call()
    account, epoch = info.get("account"), info.get("epoch")
    if (
        not isinstance(account, str)
        or not re.fullmatch("[a-f0-9]{32}", account)
        or type(epoch) is not int
    ):
        raise ValueError("invalid account metadata")
    client = SupplierClient(endpoint, account=account, epoch=epoch)
    snapshot = client.account_call("/account/snapshot")
    if (
        snapshot.get("complete") is not True
        or snapshot.get("receipts") != []
        or snapshot.get("account") != account
        or snapshot.get("epoch") != epoch
    ):
        raise PermissionError("initial binding requires an empty supplier account")
    with db.immediate() as connection:
        if (
            connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0]
            or connection.execute("SELECT paused FROM assistant_control").fetchone()[0]
        ):
            raise PermissionError("historical orders require their original account binding")
        connection.execute(
            "INSERT OR IGNORE INTO assistant_supplier_bindings VALUES (?,?,?)",
            (client.identity, account, epoch),
        )
        row = connection.execute("SELECT * FROM assistant_supplier_bindings").fetchall()
        if len(row) != 1 or tuple(row[0]) != (client.identity, account, epoch):
            raise PermissionError("supplier binding changed during discovery")
    return client


def paused_epoch(db: Database, expected: str = "") -> str:
    row = db.connection.execute("SELECT epoch,paused FROM assistant_control WHERE id=1").fetchone()
    if (
        not row["paused"]
        or (expected and row["epoch"] != expected)
        or db.path.with_suffix(".authority").read_text() != row["epoch"]
    ):
        raise PermissionError("matching paused restored authority is required")
    return str(row["epoch"])


def inspect_account(
    db: Database,
    supplier: SupplierClient,
    *,
    actor: str,
    policy: SpendingPolicy,
    expected_epoch: str = "",
) -> dict[str, Any]:
    if actor not in policy.operators:
        raise PermissionError("operator is not allowlisted")
    epoch = paused_epoch(db, expected_epoch)
    binding = db.connection.execute(
        "SELECT * FROM assistant_supplier_bindings WHERE target=?", (supplier.identity,)
    ).fetchone()
    if binding is None or binding["account"] != supplier.account:
        raise PermissionError("supplier differs from the restored account binding")
    fence = supplier.account_call(
        "/account/fence",
        data={"account": supplier.account, "rotation": epoch},
    )
    provider_epoch = fence.get("epoch")
    if (
        fence.get("account") != supplier.account
        or type(provider_epoch) is not int
        or provider_epoch < 1
    ):
        raise ValueError("invalid account fence")
    snapshot = supplier.account_call("/account/snapshot", epoch=provider_epoch)
    receipts = snapshot.get("receipts")
    if (
        snapshot.get("account") != supplier.account
        or snapshot.get("epoch") != provider_epoch
        or snapshot.get("complete") is not True
        or not isinstance(receipts, list)
        or len(receipts) > 1000
    ):
        raise ValueError("complete fenced account export required")
    seen = set()
    for receipt in receipts:
        if (
            not isinstance(receipt, dict)
            or set(receipt) != {"operation", "proposal", "status"}
            or not isinstance(receipt["operation"], str)
            or not re.fullmatch("[a-f0-9]{32}", receipt["operation"])
            or receipt["operation"] in seen
            or receipt["status"] not in {"ACCEPTED", "REJECTED"}
        ):
            raise ValueError("invalid or duplicate account receipt")
        Proposal.model_validate(receipt["proposal"], strict=True)
        seen.add(receipt["operation"])
    paused_epoch(db, epoch)
    return {
        "authority_epoch": epoch,
        "account": supplier.account,
        "provider_epoch": provider_epoch,
        "receipts": receipts,
        "plan_template": {
            "authority_epoch": epoch,
            "account": supplier.account,
            "observed_at": None,
            "inventory": {
                row[0]: {"on_hand": None, "reserved": None}
                for row in db.connection.execute("SELECT sku FROM inventory ORDER BY sku")
            },
            "deliveries": {
                r["operation"]: {"received": None, "reference": ""}
                for r in receipts
                if r["status"] == "ACCEPTED"
            },
            "model_grants": {},
        },
    }


def recover(
    db: Database,
    supplier: SupplierClient,
    raw_plan: bytes,
    digest: str,
    *,
    actor: str,
    policy: SpendingPolicy,
) -> dict[str, Any]:
    if actor not in policy.operators:
        raise PermissionError("operator is not allowlisted")
    if len(raw_plan) > 262_144 or hashlib.sha256(raw_plan).hexdigest() != digest:
        raise ValueError("recovery requires the exact bounded reviewed plan bytes")
    plan = RecoveryPlan.model_validate_json(raw_plan)
    control = db.connection.execute("SELECT * FROM assistant_control").fetchone()
    if (
        control["epoch"] != plan.authority_epoch
        or db.path.with_suffix(".authority").read_text() != control["epoch"]
    ):
        raise PermissionError("plan describes another restored state")
    prior = db.connection.execute(
        "SELECT * FROM assistant_recovery_runs WHERE epoch=?", (plan.authority_epoch,)
    ).fetchone()
    if prior:
        if prior["plan_digest"] != digest or control["paused"]:
            raise PermissionError("recovery identity already has another result")
        return {"status": "ACTIVE", "duplicate": True, "account": prior["account"]}
    if plan.account != supplier.account or not 0 <= time.time() - plan.observed_at <= 3600:
        raise ValueError("current observations of the bound account are required")
    snapshot = inspect_account(
        db, supplier, actor=actor, policy=policy, expected_epoch=plan.authority_epoch
    )
    receipts = {r["operation"]: r for r in snapshot["receipts"]}
    accepted = {key for key, r in receipts.items() if r["status"] == "ACCEPTED"}
    if set(plan.deliveries) != accepted:
        raise ValueError("explicit delivery observations for every accepted order are required")
    spent = sum(
        r["proposal"]["quantity"] * r["proposal"]["unit_cost_pence"]
        for r in receipts.values()
        if r["status"] == "ACCEPTED"
    )
    with db.immediate() as connection:
        paused_epoch(db, plan.authority_epoch)
        if not 0 <= time.time() - plan.observed_at <= 3600:
            raise ValueError("inventory observations expired during recovery")
        skus = {row[0] for row in connection.execute("SELECT sku FROM inventory")}
        if set(plan.inventory) != skus or any(
            r["proposal"]["sku"] not in skus for r in receipts.values()
        ):
            raise ValueError("complete known-catalog inventory observations are required")
        known = {row["id"]: row for row in connection.execute("SELECT * FROM assistant_orders")}
        for identifier, row in known.items():
            receipt = receipts.get(identifier)
            if row["target"] != supplier.identity:
                raise ValueError("restored state includes another supplier account")
            if (
                receipt is not None
                and json.dumps(receipt["proposal"], sort_keys=True, separators=(",", ":"))
                != row["proposal"]
            ):
                raise ValueError("supplier proposal differs from durable local intent")
            expected = {
                "CONFIRMED": "ACCEPTED",
                "DELIVERED": "ACCEPTED",
                "REJECTED": "REJECTED",
            }.get(row["status"])
            if expected and (receipt is None or receipt["status"] != expected):
                raise ValueError("account contradicts previously conclusive evidence")
        for row in connection.execute("SELECT * FROM assistant_deliveries"):
            observation = plan.deliveries.get(row["order_id"])
            if (
                observation is None
                or not observation.received
                or observation.reference != row["reference"]
            ):
                raise ValueError("delivery observation contradicts previously recorded receiving")
        imported_work = uuid.uuid5(
            uuid.NAMESPACE_URL, "account-recovery:" + plan.authority_epoch
        ).hex
        connection.execute(
            "INSERT INTO assistant_work(id,origin,session,prompt,created,status,result,delivery) "
            "VALUES (?,?, 'account-recovery','Import external account evidence',?,'DONE',?,'SENT')",
            (
                imported_work,
                "account-recovery:" + plan.authority_epoch,
                time.time(),
                "Recovered supplier evidence; original assignments absent from this backup "
                "remain unknown.",
            ),
        )
        for identifier in known:
            if identifier not in receipts:
                connection.execute(
                    "UPDATE assistant_orders SET status='REVOKED',revoked=1,approved_until=0 "
                    "WHERE id=?",
                    (identifier,),
                )
        for identifier, receipt in receipts.items():
            proposal = receipt["proposal"]
            encoded = json.dumps(proposal, sort_keys=True, separators=(",", ":"))
            if identifier not in known:
                connection.execute(
                    "INSERT INTO assistant_orders"
                    "(id,work_id,proposal,digest,amount,created,target) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        identifier,
                        imported_work,
                        encoded,
                        hashlib.sha256((supplier.identity + "\n" + encoded).encode()).hexdigest(),
                        proposal["quantity"] * proposal["unit_cost_pence"],
                        time.time(),
                        supplier.identity,
                    ),
                )
            observation = plan.deliveries.get(identifier)
            status = (
                "REJECTED"
                if receipt["status"] == "REJECTED"
                else ("DELIVERED" if observation and observation.received else "CONFIRMED")
            )
            connection.execute(
                "UPDATE assistant_orders SET status=?,receipt=?,revoked=1,approved_until=0 "
                "WHERE id=?",
                (status, json.dumps(receipt), identifier),
            )
            if observation and observation.received:
                connection.execute(
                    "INSERT OR IGNORE INTO assistant_deliveries VALUES (?,?,?,?,?)",
                    (
                        identifier,
                        observation.reference,
                        actor,
                        proposal["quantity"],
                        plan.observed_at,
                    ),
                )
        for sku, count in plan.inventory.items():
            connection.execute(
                "UPDATE inventory SET on_hand=?,reserved=?,"
                "record=json_set(record,'$.on_hand',?,'$.reserved',?) WHERE sku=?",
                (count.on_hand, count.reserved, count.on_hand, count.reserved, sku),
            )
        connection.execute(
            "INSERT INTO assistant_spending VALUES (1,?,0,?) ON CONFLICT(id) DO UPDATE SET "
            "reserved_pence=0,spent_pence=excluded.spent_pence,"
            "limit_pence=min(assistant_spending.limit_pence,excluded.limit_pence)",
            (policy.total_pence, spent),
        )
        connection.execute(
            "UPDATE assistant_work SET status='CANCELLED',cancelled=1,generation=generation+1,"
            "owner=NULL,expires=NULL WHERE status IN ('READY','RUNNING','BLOCKED')"
        )
        connection.execute(
            "UPDATE assistant_work SET delivery='UNKNOWN' WHERE delivery IN ('PENDING','SENDING')"
        )
        connection.execute("UPDATE assistant_orders SET revoked=1,approved_until=0")
        connection.execute("UPDATE assistant_stock_conditions SET armed=1")
        # The supplier export says nothing about model calls newer than the backup.
        # Close the old remaining allowance; the exact plan grants fresh exposure.
        sessions = {
            row[0]
            for row in connection.execute(
                "SELECT session FROM assistant_daily UNION SELECT "
                "coalesce(nullif(billing_session,''),session) FROM assistant_work "
                "WHERE session!='account-recovery'"
            )
        }
        if not set(plan.model_grants) <= sessions:
            raise ValueError("model grants must name known billing sessions")
        day = int(time.time() // 86400)
        for session in sessions:
            grant = plan.model_grants.get(session, ModelGrant(calls=0, estimated_pence=0))
            connection.execute(
                "INSERT OR IGNORE INTO assistant_daily(session,day) VALUES (?,?)", (session, day)
            )
            connection.execute(
                "UPDATE assistant_daily SET call_limit=model_calls+?,"
                "cost_limit=estimated_cost_pence+?,history_complete=0 WHERE session=? AND day=?",
                (grant.calls, grant.estimated_pence, session, day),
            )
        connection.execute("UPDATE assistant_jobs SET next_due=max(next_due,?)", (time.time(),))
        connection.execute(
            "UPDATE assistant_supplier_bindings SET epoch=? WHERE target=?",
            (snapshot["provider_epoch"], supplier.identity),
        )
        connection.execute(
            "INSERT INTO assistant_recovery_runs VALUES (?,?,?,?,?)",
            (plan.authority_epoch, digest, plan.account, snapshot["provider_epoch"], time.time()),
        )
        append_event(
            db,
            "assistant.account.recovered",
            {
                "actor": actor,
                "authority_epoch": plan.authority_epoch,
                "plan_digest": digest,
                "account": plan.account,
                "provider_epoch": snapshot["provider_epoch"],
                "orders": len(receipts),
                "spent_pence": spent,
                "observations": plan.model_dump(),
            },
        )
        connection.execute("UPDATE assistant_control SET paused=0 WHERE id=1")
    return {"status": "ACTIVE", "duplicate": False, "orders": len(receipts), "spent_pence": spent}
