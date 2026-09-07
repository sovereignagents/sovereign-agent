"""Small command surface for the cumulative always-on teaching implementation."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from sovereign_agent import assistant_context, assistant_orders, assistant_service, assistant_work
from sovereign_agent.agent_loop import Limits
from sovereign_agent.database import Database
from sovereign_agent.model_turn import HTTPModel, Model
from sovereign_agent.telegram_channel import Telegram, deliver_one, poll


def handle(args: argparse.Namespace) -> int:
    from reference_organizations.store.agent import OfflineShopModel, seed_lucy
    from reference_organizations.store.assistant import reconcile_once, run_once
    from reference_organizations.store.supplier import SupplierClient

    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = Database(root / "agent.sqlite")
    seed_lucy(db)
    operators = frozenset(
        item for item in os.environ.get("SOVEREIGN_AGENT_OPERATORS", "lucy").split(",") if item
    )
    policy = assistant_orders.SpendingPolicy(
        operators, total_pence=args.total_pence, automatic_order_pence=args.automatic_pence
    )
    model: Model = OfflineShopModel()
    if args.live or os.environ.get("SOVEREIGN_AGENT_MODEL_MODE") == "live":
        model = HTTPModel(
            os.environ.get("SOVEREIGN_AGENT_LLM_BASE_URL", "http://localhost:11434/v1"),
            os.environ.get("SOVEREIGN_AGENT_LLM_MODEL", "qwen3"),
            os.environ.get("SOVEREIGN_AGENT_LLM_API_KEY", ""),
        )
    endpoint = args.supplier or os.environ.get("SOVEREIGN_AGENT_SUPPLIER", "")
    supplier = SupplierClient(endpoint) if endpoint else None
    limits = Limits(
        estimated_call_pence=args.estimated_call_pence, model_budget_pence=args.model_budget_pence
    )
    result: Any = {"status": "INITIALIZED", "root": str(root)}
    action = args.action
    if action == "ask":
        identifier = assistant_work.enqueue(
            db, args.id or "local:" + uuid.uuid4().hex, args.session, args.value
        )
        result = {"work": identifier, "status": "QUEUED"}
        if not args.enqueue_only:
            result = run_once(db, model, policy=policy, supplier=supplier, limits=limits)
    elif action == "work":
        assistant_work.tick(db)
        result = run_once(db, model, policy=policy, supplier=supplier, limits=limits)
    elif action == "schedule":
        assistant_work.schedule(
            db,
            args.id or "morning",
            args.session,
            args.value or "Prepare the morning replenishment brief.",
            first_due=args.first_due if args.first_due is not None else time.time(),
            interval_seconds=args.interval,
        )
        result = {
            "status": "SCHEDULED",
            "id": args.id or "morning",
            "timezone": "UTC",
            "missed_runs": "coalesce",
        }
    elif action == "status":
        result = assistant_service.health(db)
        result["items"] = [
            dict(row)
            for row in db.connection.execute(
                "SELECT id,status,result FROM assistant_work ORDER BY created DESC LIMIT 20"
            )
        ]
        result["orders"] = [
            dict(row)
            for row in db.connection.execute(
                "SELECT id,digest,amount,status,approved_until,revoked FROM assistant_orders "
                "ORDER BY created DESC LIMIT 20"
            )
        ]
    elif action in {"approve", "revoke"}:
        actor = args.actor or "lucy"
        if action == "approve":
            assistant_orders.approve(
                db,
                args.value,
                args.digest,
                actor=actor,
                policy=policy,
                expires=time.time() + args.approval_seconds,
            )
            with db.immediate() as connection:
                connection.execute(
                    "UPDATE assistant_work SET status='READY',available_after=0 "
                    "WHERE status='BLOCKED' "
                    "AND id=(SELECT work_id FROM assistant_orders WHERE id=?)",
                    (args.value,),
                )
        else:
            assistant_orders.revoke(db, args.value, actor=actor, policy=policy)
        result = {"status": action.upper(), "order": args.value}
    elif action == "retry":
        with db.immediate() as connection:
            changed = connection.execute(
                "UPDATE assistant_work SET status='READY',available_after=0 "
                "WHERE id=? AND status='BLOCKED'",
                (args.value,),
            ).rowcount
        result = {"status": "READY" if changed else "UNCHANGED"}
    elif action == "cancel":
        assistant_work.cancel(db, args.value)
        result = {"status": "CANCELLED"}
    elif action == "remember":
        result = {
            "revision": assistant_context.remember(
                db, args.session, args.key, args.value, "local-operator:" + (args.actor or "lucy")
            )
        }
    elif action == "forget":
        assistant_context.forget(db, args.session, args.key)
        result = {"status": "FORGOTTEN"}
    elif action == "backup":
        result = {"backup": str(assistant_service.backup(db, Path(args.value)))}
    elif action == "restore":
        assistant_service.restore(db, Path(args.value))
        result = {
            "status": "PAUSED",
            "reason": "Restored state requires external reconciliation and renewed authority.",
        }
    elif action == "service":
        result = assistant_service.service(
            args.value, root, Path(sys.executable).with_name("sovereign-agent")
        )
    elif action == "serve":
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        token = os.environ.get("SOVEREIGN_AGENT_TELEGRAM_TOKEN", "")
        bot = Telegram(token) if token else None
        numeric = frozenset(int(actor) for actor in operators if actor.isdigit())
        if bot and (not numeric or len(numeric) != len(operators)):
            raise ValueError("Telegram requires numeric SOVEREIGN_AGENT_OPERATORS")
        failures = 0
        while not stop.is_set():
            try:
                uncertain = db.connection.execute(
                    "SELECT count(*) FROM assistant_orders WHERE status IN ('UNKNOWN','SENDING')"
                ).fetchone()[0]
                if uncertain:
                    item = (
                        reconcile_once(db, supplier, policy, should_stop=stop.is_set)
                        if supplier
                        else {"status": "RECOVERY_NEEDS_SUPPLIER"}
                    )
                    # An unresolved supplier must not make the operator's revoke
                    # and cancel commands unreachable. Ordinary turns stay held.
                    if bot and not stop.is_set():
                        poll(db, bot, numeric)
                        if not stop.is_set():
                            run_once(
                                db,
                                model,
                                policy=policy,
                                supplier=supplier,
                                limits=limits,
                                should_stop=stop.is_set,
                                control_only=True,
                            )
                else:
                    if bot:
                        poll(db, bot, numeric)
                    if stop.is_set():
                        break
                    assistant_work.tick(db)
                    item = run_once(
                        db,
                        model,
                        policy=policy,
                        supplier=supplier,
                        limits=limits,
                        should_stop=stop.is_set,
                    )
                if bot and not stop.is_set():
                    deliver_one(db, bot, numeric)
                # Logs describe work state, never prompts or channel credentials.
                print(json.dumps({"status": item["status"], "work": item.get("work")}), flush=True)
                failures = 0
            except OSError, ValueError:
                failures = min(failures + 1, 5)
                print(json.dumps({"status": "RETRY_WAIT", "attempt": failures}), flush=True)
            stop.wait(min(60, 2**failures) if failures else 1)
        result = {"status": "STOPPED"}
    print(json.dumps(result, indent=2, default=str))
    return 0


def register(subparsers: Any, shared: argparse.ArgumentParser) -> None:
    parser = subparsers.add_parser(
        "agent", parents=[shared], help="build and operate Lucy's always-on teaching agent"
    )
    parser.add_argument(
        "action",
        choices=[
            "init",
            "ask",
            "work",
            "schedule",
            "status",
            "approve",
            "revoke",
            "retry",
            "cancel",
            "remember",
            "forget",
            "backup",
            "restore",
            "service",
            "serve",
        ],
    )
    parser.add_argument("value", nargs="?", default="")
    parser.add_argument("--session", default="lucy")
    parser.add_argument("--id", default="")
    parser.add_argument("--key", default="")
    parser.add_argument("--actor", default="")
    parser.add_argument("--digest", default="")
    parser.add_argument("--approval-seconds", type=int, default=3600)
    parser.add_argument("--total-pence", type=int, default=20_000)
    parser.add_argument("--automatic-pence", type=int, default=0)
    parser.add_argument("--interval", type=int, default=86400)
    parser.add_argument("--first-due", type=float)
    parser.add_argument("--supplier", default="")
    parser.add_argument("--enqueue-only", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--estimated-call-pence", type=int, default=0)
    parser.add_argument("--model-budget-pence", type=int, default=100)
    parser.set_defaults(handler=handle)
