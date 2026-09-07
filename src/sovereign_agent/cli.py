"""The stdlib-only command-line entry point."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from sovereign_agent import __version__
from sovereign_agent.errors import Refusal
from sovereign_agent.models import Outcome, Role
from sovereign_agent.organization import Organization
from sovereign_agent.providers import PROVIDERS
from sovereign_agent.supervisor import run as run_supervisor


def _installed_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _root(namespace: argparse.Namespace) -> Path:
    return Path(namespace.root).resolve()


def _doctor(_: argparse.Namespace) -> int:
    python_ok = sys.version_info >= (3, 14)
    pydantic_version = _installed_version("pydantic")
    pydantic_ok = pydantic_version != "not installed"
    print("Sovereign Agent doctor")
    print(f"  Python:   {platform.python_version()} {'OK' if python_ok else 'NEEDS 3.14+'}")
    print(f"  Pydantic: {pydantic_version} {'OK' if pydantic_ok else 'MISSING'}")
    print("  Network:  not required")
    print("  Tokens:   not required")
    print("  Providers:")
    for name, provider in PROVIDERS.items():
        caps = provider.probe()
        if caps.available:
            state = f"available {caps.version}".rstrip()
            if caps.degraded_reason:
                state += f"; degraded: {caps.degraded_reason}"
        elif caps.degraded_reason:
            state = f"degraded: {caps.degraded_reason}"
        else:
            state = "missing executable"
        extra = []
        if caps.streaming:
            extra.append("streaming")
        if caps.resume:
            extra.append("resume")
        if caps.workspace_selection:
            extra.append("workspace-selection")
        if caps.workspace_write:
            extra.append("workspace-write")
        if caps.sandbox:
            extra.append("sandbox")
        suffix = f" ({', '.join(extra)})" if extra else ""
        print(f"    {name:8} {state}{suffix}")
    if python_ok and pydantic_ok:
        print("Ready for the offline curriculum. Live providers are optional.")
        return 0
    if not python_ok:
        print("Next: install Python 3.14, then rerun `sovereign-agent doctor`.")
    else:
        print("Next: reinstall sovereign-agent so its sole runtime dependency is present.")
    return 1


def _init(namespace: argparse.Namespace) -> int:
    org = Organization.init(_root(namespace))
    print(f"Initialized {org.root}")
    return 0


def _actor_list(namespace: argparse.Namespace) -> int:
    org = Organization(_root(namespace))
    for actor in org.actors.values():
        print(f"{actor.id}\t{actor.role}\t{actor.provider}")
    return 0


def _outcome_new(namespace: argparse.Namespace) -> int:
    org = Organization(_root(namespace))
    outcome = org.create_outcome(
        namespace.title, namespace.desired, namespace.checks, namespace.owner, namespace.subject
    )
    print(outcome.id)
    return 0


def _plan(namespace: argparse.Namespace) -> int:
    org = Organization(_root(namespace))
    org.activate(namespace.outcome_id, namespace.actor)
    sow = org.create_sow(
        namespace.outcome_id, namespace.scope, Role(namespace.role), namespace.actor
    )
    org.ready_sow(sow.id)
    print(sow.id)
    return 0


def _run(namespace: argparse.Namespace) -> int:
    org = Organization(_root(namespace))
    assignment = org.assign(namespace.sow_id, namespace.actor, namespace.planner)
    assignment = org.run_assignment(assignment.id)
    print(f"{assignment.id} {assignment.state}")
    return 0


def _status(namespace: argparse.Namespace) -> int:
    print(Organization(_root(namespace)).status_text(namespace.outcome_id))
    return 0


def _inspect(namespace: argparse.Namespace) -> int:
    """Show the operational facts a reader needs to audit an ACCEPTED claim.

    Auditing an outcome should not require the `sqlite3` binary or any SQL. The
    quickstart told a learner they needed "Python and a terminal" and then asked
    for a database client they may not have. Checking whether the organization
    told the truth is the central act of this book; it gets a first-class
    command.
    """
    org = Organization(_root(namespace))
    connection = org.db.connection
    print("inventory")
    for row in connection.execute(
        "SELECT sku, on_hand, reserved, reorder_point FROM inventory ORDER BY sku"
    ):
        enough = (
            "OK "
            if int(row["on_hand"]) - int(row["reserved"]) >= int(row["reorder_point"])
            else "LOW"
        )
        print(
            f"  {enough} {row['sku']}: on_hand={row['on_hand']} "
            f"reserved={row['reserved']} reorder_point={row['reorder_point']}"
        )
    print("cash")
    total = 0
    for row in connection.execute("SELECT id, amount_cents FROM cash_entries ORDER BY rowid"):
        total += int(row["amount_cents"])
        print(f"  {int(row['amount_cents']):>8}  {row['id']}")
    print(f"  {total:>8}  = balance")
    print("events")
    for row in connection.execute(
        "SELECT kind, COUNT(*) AS n FROM events GROUP BY kind ORDER BY kind"
    ):
        print(f"  {int(row['n']):>3}  {row['kind']}")
    print("outcomes")
    for row in connection.execute("SELECT record FROM outcomes"):
        outcome = Outcome.model_validate_json(row["record"])
        print(f"  {outcome.state} {outcome.id}  {outcome.title}")
    return 0


def _inbox(namespace: argparse.Namespace) -> int:
    for message in Organization(_root(namespace)).inbox(namespace.actor_id):
        print(f"{message.id} {message.state} {message.subject}")
    return 0


def _ruling_decide(namespace: argparse.Namespace) -> int:
    ruling = Organization(_root(namespace)).rule(
        namespace.question, namespace.decision, namespace.actor, namespace.applies_to
    )
    print(ruling.id)
    return 0


def _verify(namespace: argparse.Namespace) -> int:
    org = Organization(_root(namespace))
    results = org.verify_outcome(namespace.outcome_id, namespace.actor)
    for result in results:
        print(f"{result.check_id} {'PASS' if result.success else 'FAIL'} {result.detail}")
    return 0 if all(result.success for result in results) else 1


def _accept(namespace: argparse.Namespace) -> int:
    org = Organization(_root(namespace))
    # No --evidence and no --performer. Acceptance derives both from the ledger:
    # a caller that supplies its own proof is not being checked.
    acceptance = org.accept(namespace.outcome_id, namespace.actor)
    print(f"ACCEPTED {acceptance.outcome_id}")
    for reference in acceptance.evidence_refs:
        print(f"  evidence {reference}")
    return 0


def _supervisor(namespace: argparse.Namespace) -> int:
    """The reconciliation loop: leases, expired mailbox claims, hard-kill recovery.

    `--once` runs a single deterministic tick and exits -- the shape a script
    or a test uses. Without it, this loops in the foreground, sleeping
    between ticks, until an ordinary interruption (Ctrl-C / SIGINT) asks it
    to stop -- caught cleanly, not left to crash with a traceback. No hidden
    daemonization: this never forks, never detaches from its terminal, and
    never installs itself as an OS service. Distinct from the not-yet-built
    `service` (future OS-level install/status/uninstall, unimplemented) and
    from `pulse` (Unit 9's own separate proactive-wake mechanism, implemented
    below but never called from here -- see
    docs/rulings/2026-08-29-unit9-pulse-is-separate-from-supervisor.md) --
    this command is the supervisor itself, and it still never reads a Pulse
    signal or fires a wake gate.
    """
    org = Organization(_root(namespace))
    return run_supervisor(org, once=namespace.once)


def _pulse(namespace: argparse.Namespace) -> int:
    """Unit 9: sale -> signal -> deterministic wake gate -> proactive work.

    A distinct mechanism from `supervisor`, never called from it and never
    calling it (see the governing ruling). `--once` is the only shape this
    unit builds: one deterministic pass over durable signals, then exit --
    no looping, no scheduling, no OS service.
    """
    from reference_organizations.store.pulse_gate import store_wake_gate
    from sovereign_agent.pulse import run_pulse_once

    org = Organization(_root(namespace))
    report = run_pulse_once(org, store_wake_gate)
    for item in report.items:
        print(
            f"{item.signal_id} {item.status}"
            + (f" sow={item.sow_id} assignment={item.assignment_id}" if item.sow_id else "")
            + (f" ({item.detail})" if item.detail else "")
        )
    print(f"pulse: {len(report.created)} created, {len(report.items)} signal(s) evaluated")
    return 0


def _heartbeat(namespace: argparse.Namespace) -> int:
    """Record or read durable liveness beats. NOT the Pulse: creates no work.

    Default: append one beat and print its id. `--status`: read the newest
    beat and print the honest verdict — ALIVE within `--stale-after` seconds,
    STALE beyond it (which proves silence, not death), NO_BEATS when none
    exist. `--status` exits 0 only on ALIVE, so a cron or watchdog can use
    the exit code directly.
    """
    from sovereign_agent.heartbeat import heartbeat_status, record_heartbeat

    org = Organization(_root(namespace))
    if namespace.status:
        status = heartbeat_status(org, stale_after_seconds=namespace.stale_after)
        print(status.line())
        return 0 if status.verdict == "ALIVE" else 1
    beat_id = record_heartbeat(org, source=namespace.source)
    print(f"beat recorded: {beat_id}")
    return 0


def _mechanisms(namespace: argparse.Namespace) -> int:
    """Run the six advanced mechanisms without a provider or network."""
    from reference_organizations.store.advanced_demo import run_advanced

    print(run_advanced(_root(namespace)))
    return 0


def _demo(namespace: argparse.Namespace) -> int:
    from reference_organizations.store.demo import run_simulated

    if namespace.target != "store" or namespace.mode != "simulated":
        print("Only `demo store --mode simulated` is implemented in this unit.")
        return 1
    text = run_simulated(_root(namespace))
    print(text)
    if "ACCEPTED" in text:
        print("outcome ACCEPTED")
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--root", default=".", help="organization directory")
    parser = argparse.ArgumentParser(
        prog="sovereign-agent",
        description="Learn how outcomes become governed, evidence-backed work.",
        parents=[shared],
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser(
        "doctor", parents=[shared], help="check the offline learning environment"
    )
    doctor.set_defaults(handler=_doctor)

    init = subparsers.add_parser(
        "init", parents=[shared], help="create sovereign.toml and the local ledger"
    )
    init.set_defaults(handler=_init)

    actor = subparsers.add_parser("actor", parents=[shared], help="inspect actors")
    actor_sub = actor.add_subparsers(dest="actor_command", required=True)
    listed = actor_sub.add_parser("list", parents=[shared])
    listed.set_defaults(handler=_actor_list)

    outcome = subparsers.add_parser("outcome", parents=[shared], help="define outcomes")
    outcome_sub = outcome.add_subparsers(dest="outcome_command", required=True)
    created = outcome_sub.add_parser("new", parents=[shared])
    created.add_argument("title")
    created.add_argument("--desired", default="The outcome's acceptance checks pass.")
    created.add_argument("--checks", nargs="*", default=["inventory_at_or_above_reorder_point"])
    created.add_argument("--owner", default="principal-human")
    created.add_argument("--subject", default="SKU-TEA")
    created.set_defaults(handler=_outcome_new)

    plan = subparsers.add_parser("plan", parents=[shared], help="activate an outcome and add a SOW")
    plan.add_argument("outcome_id")
    plan.add_argument("--scope", default="Advance the outcome by one bounded assignment")
    plan.add_argument("--role", default="operator")
    plan.add_argument("--actor", default="master-course")
    plan.set_defaults(handler=_plan)

    run = subparsers.add_parser("run", parents=[shared], help="assign and invoke one actor")
    run.add_argument("sow_id")
    run.add_argument("--actor", default="operator-course")
    run.add_argument("--planner", default="master-course")
    run.set_defaults(handler=_run)

    status = subparsers.add_parser("status", parents=[shared], help="explain outcome and SOW state")
    status.add_argument("outcome_id")
    status.set_defaults(handler=_status)

    inspect_parser = subparsers.add_parser(
        "inspect", parents=[shared], help="show inventory, cash, events and outcomes"
    )
    inspect_parser.set_defaults(handler=_inspect)

    inbox = subparsers.add_parser("inbox", parents=[shared], help="list an actor's durable mailbox")
    inbox.add_argument("actor_id")
    inbox.set_defaults(handler=_inbox)

    ruling = subparsers.add_parser("ruling", parents=[shared], help="record a decision")
    ruling_sub = ruling.add_subparsers(dest="ruling_command", required=True)
    decide = ruling_sub.add_parser("decide", parents=[shared])
    decide.add_argument("question")
    decide.add_argument("--decision", required=True)
    decide.add_argument("--actor", default="principal-human")
    decide.add_argument("--applies-to", dest="applies_to", default="organization")
    decide.set_defaults(handler=_ruling_decide)

    verify = subparsers.add_parser(
        "verify", parents=[shared], help="run deterministic verification"
    )
    verify.add_argument("outcome_id")
    verify.add_argument("--actor", default="verifier-course")
    verify.set_defaults(handler=_verify)

    accept = subparsers.add_parser(
        "accept", parents=[shared], help="accept an outcome under authority"
    )
    accept.add_argument("outcome_id")
    accept.add_argument("--actor", default="principal-human")
    accept.set_defaults(handler=_accept)

    demo = subparsers.add_parser("demo", parents=[shared], help="run a scripted teaching scenario")
    demo.add_argument("target", choices=["store"])
    demo.add_argument("--mode", default="simulated", choices=["simulated"])
    demo.set_defaults(handler=_demo)

    supervisor = subparsers.add_parser(
        "supervisor",
        parents=[shared],
        help=(
            "reconcile leases, expired claims, and hard-killed assignments "
            "(the runtime loop; not 'service' [future OS hosting, "
            "unimplemented] or 'pulse' [the separate proactive-wake command "
            "below, never called from here])"
        ),
    )
    supervisor.add_argument(
        "--once",
        action="store_true",
        help="run a single deterministic reconciliation tick and exit, instead of looping",
    )
    supervisor.set_defaults(handler=_supervisor)

    heartbeat = subparsers.add_parser(
        "heartbeat",
        parents=[shared],
        help=(
            "record or read durable liveness beats (NOT the pulse: proves the "
            "runtime was alive at a moment, never that work happened)"
        ),
    )
    heartbeat.add_argument("--status", action="store_true", help="read the newest beat and verdict")
    heartbeat.add_argument(
        "--stale-after",
        type=int,
        default=900,
        help="seconds before the last beat counts as STALE (with --status)",
    )
    heartbeat.add_argument("--source", default="cli", help="who is beating (recorded verbatim)")
    heartbeat.set_defaults(handler=_heartbeat)

    pulse = subparsers.add_parser(
        "pulse",
        parents=[shared],
        help=(
            "sale -> signal -> deterministic wake gate -> proactive governed "
            "work, created without a human prompt (distinct from 'supervisor'; "
            "'--once' is the only shape this command has)"
        ),
    )
    pulse.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="run a single deterministic pulse pass and exit (the only supported mode)",
    )
    pulse.set_defaults(handler=_pulse)

    mechanisms = subparsers.add_parser(
        "mechanisms",
        parents=[shared],
        help="run the isolation, scheduling, context, fencing, tool, and memory lesson",
    )
    mechanisms.set_defaults(handler=_mechanisms)
    from sovereign_agent.assistant_cli import register

    register(subparsers, shared)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    try:
        return int(namespace.handler(namespace))
    except Refusal as error:
        print(error)
        print(f"Next: {error.next_command}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
