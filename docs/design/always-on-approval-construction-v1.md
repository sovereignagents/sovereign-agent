**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** FINDING

# Current approval must cover the current exact proposal

Chapter 8 follows the unattended-draft construction in 40bef87. The full book
overhaul remains active. This increment contains the approval chapter, two
reproduced authority repairs, a forward migration, and the prior increment's
actual Linux service evidence.

## Reproduced behavior

On a fresh database, approve six vanilla tubs for 1500 pence automatically under
a 2000-pence automatic allowance. Execute under a new policy whose automatic
allowance is zero. The previous code called a controlled supplier once and
returned ACCEPTED: it retained the actor but not the basis of the grant.

On another fresh database, approve a six-tub proposal, then propose seven tubs
for the same product in the same assignment. The previous code retained the
1500-pence APPROVED proposal and reservation beside a new 1750-pence DRAFT.
The model-facing shop wrapper checks current need, but an observed inventory
change can legitimately produce the new quantity. The older approval must not
remain an independently eligible purchase merely because a revision has a
different digest.

## Decisions and implementation

Migration 25 adds approval_basis with UNKNOWN, OPERATOR and AUTOMATIC values.
Every new approve call records an explicit basis in the same transaction as
its reservation and expiration. Execution refuses UNKNOWN before a new send,
and an AUTOMATIC grant must fit the current automatic allowance. Operator
allowlist, aggregate ceiling, reservation, expiry, cancellation, destination
and current-worker checks continue to apply. Discovery of a previously accepted
effect remains possible after authority reduction.

Historical records default to UNKNOWN. The migration does not infer operator
consent from an actor label or assume a complete history. An eligible old grant
can be explicitly reapproved without reserving twice; an existing uncertain
effect can still be discovered. Stop workers before migration. Startup's
future-schema refusal is not protection for already-running older code.

A changed same-product proposal atomically revokes old DRAFT or APPROVED
versions, releases an old unsent reservation, records supersession, and creates
the replacement draft. An identical old request returns its old identifier
without restoring revoked authority. Existing SENDING, UNKNOWN, CONFIRMED or
DELIVERED effects prevent another same-product proposal in that assignment.
Different products remain independent proposals under the shared account
ceiling. This is not a general revision or supplier-cancellation protocol.

## Evidence and teaching scope

tests/test_approval_lifecycle.py exercises policy reduction across restart,
explicit operator reapproval, receipt discovery versus retransmission after
reduction, migration from schema 24, same-product supersession, different-product
independence, non-boolean basis refusal and transaction rollback when the
supersession event fails. The separate-process ch08.py checkpoint observes zero
remote orders during all refusals and one authorized seven-tub purchase after
reapproval, with zero reserved and 1750 spent pence.

Chapter 8 constructs the complete proposal, approval, revocation and send gate.
Receipt plumbing is explicitly identified as the next chapter's construction.
Chapter 9's displayed admission code now carries the same approval-basis checks.
Both remain drafts; scores describe structure, not publisher acceptance.

linux-scheduled-drafts-v1.json records the actual 40bef87 release switch and
systemd clock/stock work after the setup invocation exited. The isolated stock
fixture was temporarily changed and restored; orders and spending were retained.
This receipt belongs to schema 24. The new schema 25 still needs its own actual
guest upgrade observation after this increment is committed.
