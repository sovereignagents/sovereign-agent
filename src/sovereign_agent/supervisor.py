"""The reconciliation loop: leases, expired claims, and hard-kill recovery.

The supervisor is the ONE process allowed to decide that another process is
dead. `docs/units-0-6-contract.md`, Unit 5: "A hard kill cannot be caught and
belongs to Unit 8 recovery: a process cannot record its own death." This
module is that recovery, and nothing else -- see `docs/v1-unit8-supervisor-
fencing-recovery.md` for the full contract this implements.

A tick does four things, always in this order, always read-then-decide
against the durable ledger rather than any in-memory state:

1. Report actor leases past expiry (read-only; expiry alone is not a fault
   -- the lease simply becomes acquirable again, lazily, the next time
   something calls `fencing.acquire_actor_lease`).
2. Sweep expired mailbox claims back to `NEW` across every recipient (the
   proactive form of what `relay.inbox()` already does lazily, per actor,
   on read).
3. Recover assignments whose execution attempt has expired: a durable
   FAILED receipt naming the expired attempt and the failure category
   `worker_lost`, the assignment and its SOW moved out of RUNNING, the
   fence released, and -- only after all of that is durable -- workspace
   policy applied.
4. Nothing else. The supervisor never creates work, never reads a Pulse
   signal, never fires a wake gate, never installs itself as an OS service.
   See "Explicit non-scope" in the governing doc.

Every step is safe to re-run: a lease past expiry stays reportable until
something re-acquires it; a swept claim is simply `NEW` again, identical to
what a normal `claim()` would have produced; a recovered assignment's fence
is cleared as part of the SAME transaction that writes its terminal state,
so a second tick sees a terminal assignment with no current attempt and has
nothing left to recover.
"""

from __future__ import annotations

import json
import signal
import time
from dataclasses import dataclass, field

from sovereign_agent import fencing
from sovereign_agent.database import Database
from sovereign_agent.errors import Refusal
from sovereign_agent.events import append_event
from sovereign_agent.execution import canonical_receipt_json, write_receipt
from sovereign_agent.ids import new_id, utc_now
from sovereign_agent.models import Assignment, AssignmentState, Receipt, SowState
from sovereign_agent.organization import Organization
from sovereign_agent.policy import advance_sow
from sovereign_agent.relay import sweep_claims
from sovereign_agent.workspace import reclaim_workspace

# The one failure category this module ever writes. Named once, used
# everywhere, so nothing downstream (a receipt reader, a test, a future
# unit) has to reconcile two spellings of "the worker never came back."
WORKER_LOST = "worker_lost"

TICK_INTERVAL_SECONDS = 2.0


@dataclass(frozen=True)
class RecoveredAssignment:
    assignment_id: str
    attempt_id: str
    receipt_id: str


@dataclass(frozen=True)
class SupervisorReport:
    """What one tick observed and did. Printed by the CLI; asserted by tests."""

    expired_actor_leases: tuple[str, ...] = field(default_factory=tuple)
    swept_mailbox_claims: tuple[str, ...] = field(default_factory=tuple)
    recovered_assignments: tuple[RecoveredAssignment, ...] = field(default_factory=tuple)


def sweep_expired_mailbox_claims(db: Database, clock: fencing.Clock = utc_now) -> list[str]:
    """Reset every expired CLAIMED message to NEW, across every recipient.

    `relay.inbox()` already does this lazily, one recipient at a time, on
    read. This is the same reset applied proactively across the whole
    mailbox, which is what makes it a genuine SUPERVISOR act rather than
    something that only happens to run as a side effect of an actor
    checking its own inbox.
    """
    return sweep_claims(db, clock())


def _read_assignment(db: Database, assignment_id: str) -> Assignment:
    raw = db.get("assignments", "id", assignment_id)
    if raw is None:
        raise Refusal(
            f"Assignment {assignment_id!r} vanished mid-recovery.",
            "The execution_attempts row named it, but the assignments table "
            "no longer has it -- an append-only ledger should never lose a row.",
            "sovereign-agent status",
            "Investigate the ledger directly; this should not happen.",
            category="internal_error",
        )
    return Assignment.model_validate(raw)


def _read_sow(db: Database, sow_id: str) -> dict[str, object]:
    raw = db.get("sows", "id", sow_id)
    if raw is None:
        raise Refusal(
            f"SOW {sow_id!r} vanished mid-recovery.",
            "An assignment must reference a real SOW.",
            "sovereign-agent status",
            "Investigate the ledger directly; this should not happen.",
            category="internal_error",
        )
    return raw


def recover_abandoned_assignments(
    org: Organization, clock: fencing.Clock = utc_now
) -> list[RecoveredAssignment]:
    """Recover every RUNNING assignment whose execution attempt has expired.

    Never guesses success. The recovered receipt is always a FAILED receipt
    with `failure_category="worker_lost"` naming the expired attempt --
    there is no path here that infers the provider finished, however far its
    subprocess may actually have gotten, because inferring success from
    silence is exactly the guess Unit 5's own "nothing is ever a guessed
    success" rule forbids.

    Idempotent by construction: recovering an assignment releases its fence
    (`current_execution_attempt` back to NULL) in the SAME transaction as
    the terminal write, so `fencing.expired_execution_attempts` stops
    returning it on the next tick -- there is nothing left to recover.
    Workspace policy is applied only AFTER that transaction commits, never
    before: a crash between the two leaves a terminal, correct ledger and a
    workspace a future tick can still reclaim by policy, never a workspace
    reclaimed out from under a ledger that was not yet durable.
    """
    recovered: list[RecoveredAssignment] = []
    for attempt in fencing.expired_execution_attempts(org.db, clock=clock):
        assignment = _read_assignment(org.db, attempt.assignment_id)
        if assignment.state != AssignmentState.RUNNING:
            # Already moved on by the assignment's own worker between the
            # expiry check above and this read -- a real race this function
            # must lose gracefully, not double-recover.
            continue
        sow_raw = _read_sow(org.db, assignment.sow_id)
        now = clock()
        receipt = Receipt(
            id=new_id("rct"),
            assignment_id=assignment.id,
            actor_id=attempt.actor_id,
            provider=org.actor(attempt.actor_id).provider if attempt.actor_id in org.actors else "",
            provider_session_ref=None,
            provider_usage={},
            started_at=attempt.acquired_at,
            ended_at=now,
            status="failed",
            failure_category=WORKER_LOST,
            failure_message=(
                f"Execution attempt {attempt.id} (fencing token {attempt.fencing_token}) "
                f"expired at {attempt.expires_at.isoformat()} with no valid current worker. "
                "Recovered by the supervisor, not the process that held it -- a process "
                "cannot record its own death."
            ),
            evidence_refs=[],
        )
        receipt_json = canonical_receipt_json(receipt)
        workspace = org.root / ".sovereign" / "runs" / assignment.workspace_id
        # Written to disk too, matching every other receipt's durability --
        # `_require_deliverables`/`accept`/Chapter 3's own exercise all read
        # `receipt.json` straight from the workspace root, and a recovery
        # receipt is not exempt from that contract just because a process
        # was not there to write it in the ordinary path.
        if workspace.exists() and not workspace.is_symlink():
            write_receipt(workspace, receipt)
        assignment.state = AssignmentState.FAILED
        current_sow_state = sow_raw["state"]
        assert isinstance(current_sow_state, str)
        sow_state = advance_sow(SowState(current_sow_state), SowState.FAILED)
        with org.db.transaction() as connection:
            org.db.put_serialized("receipts", receipt.id, receipt_json)
            cursor = connection.execute(
                "UPDATE assignments SET record = ?, current_execution_attempt = NULL "
                "WHERE id = ? AND current_execution_attempt = ?",
                (
                    json.dumps(assignment.model_dump(mode="json"), default=str),
                    assignment.id,
                    attempt.id,
                ),
            )
            if cursor.rowcount != 1:
                # Lost the race to someone else's recovery (or the worker's
                # own late-arriving terminal write) between the read above
                # and this write. Not an error: the other writer's version
                # of events is now canonical, and this tick simply reports
                # nothing recovered for this assignment.
                continue
            fencing.release_execution_attempt(connection, assignment.id, attempt.id, "RECOVERED")
            sow_raw["state"] = sow_state.value
            connection.execute(
                "UPDATE sows SET record = ? WHERE id = ?",
                (json.dumps(sow_raw, default=str), assignment.sow_id),
            )
            append_event(
                org.db,
                "assignment.finished",
                {"id": assignment.id, "status": assignment.state},
            )
            append_event(
                org.db,
                "assignment.recovered",
                {
                    "assignment_id": assignment.id,
                    "attempt_id": attempt.id,
                    "fencing_token": attempt.fencing_token,
                    "failure_category": WORKER_LOST,
                },
            )
        outcome_id = sow_raw["outcome_id"]
        assert isinstance(outcome_id, str)
        org.reproject_outcome(outcome_id)
        # Applied only now, after the recovery transaction above is durable.
        # `reclaim_workspace` itself still enforces the same symlink/policy
        # refusals Unit 7 established; a fault here leaves a terminal,
        # correct ledger and a workspace a later tick can still reclaim.
        actor = org.actors.get(attempt.actor_id)
        policy = actor.workspace_policy if actor is not None else "temporary_directory"
        reclaim_workspace(workspace, policy)
        recovered.append(
            RecoveredAssignment(
                assignment_id=assignment.id, attempt_id=attempt.id, receipt_id=receipt.id
            )
        )
    return recovered


def tick(org: Organization, clock: fencing.Clock = utc_now) -> SupervisorReport:
    """Run one deterministic reconciliation pass. No sleeping, no looping."""
    expired_leases = tuple(
        lease.actor_id for lease in fencing.expired_actor_leases(org.db, clock=clock)
    )
    swept = tuple(sweep_expired_mailbox_claims(org.db, clock=clock))
    recovered = tuple(recover_abandoned_assignments(org, clock=clock))
    return SupervisorReport(
        expired_actor_leases=expired_leases,
        swept_mailbox_claims=swept,
        recovered_assignments=recovered,
    )


def run(org: Organization, *, once: bool, interval: float = TICK_INTERVAL_SECONDS) -> int:
    """The foreground supervisor CLI entry point's own logic, minus argparse.

    `once=True` runs a single deterministic tick and returns -- the shape
    every test in the proof matrix uses, since it needs no real sleeping and
    no signal handling to exercise the reconciliation logic itself.
    `once=False` loops, sleeping `interval` seconds between ticks, until an
    ordinary interruption (SIGINT / Ctrl-C, or `KeyboardInterrupt` raised
    directly) asks it to stop -- caught here, not left to crash with a
    traceback, because an operator stopping the supervisor is expected
    behaviour, not a defect. No hidden daemonization: this function never
    forks, never detaches from its controlling terminal, and never installs
    itself as an OS service -- that remains explicitly out of scope (see the
    governing doc's non-goals).
    """
    stop = False

    def _handle_sigint(signum: int, frame: object) -> None:
        nonlocal stop
        stop = True

    previous_handler = signal.signal(signal.SIGINT, _handle_sigint)
    try:
        report = tick(org)
        _print_report(report)
        if once:
            return 0
        while not stop:
            time.sleep(interval)
            if stop:
                break
            report = tick(org)
            _print_report(report)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        signal.signal(signal.SIGINT, previous_handler)


def _print_report(report: SupervisorReport) -> None:
    print(
        f"supervisor tick: {len(report.expired_actor_leases)} expired lease(s), "
        f"{len(report.swept_mailbox_claims)} swept claim(s), "
        f"{len(report.recovered_assignments)} recovered assignment(s)"
    )
    for recovery in report.recovered_assignments:
        print(f"  recovered {recovery.assignment_id} (attempt {recovery.attempt_id}, worker_lost)")
