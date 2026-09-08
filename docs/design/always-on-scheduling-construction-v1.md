**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** FINDING

# Unattended drafts require a correct displayed result

This construction increment follows the phone chapter and the stock-event
implementation. The full sixteen-chapter overhaul remains active.

## Observed defects and decisions

1. A paused clock pass consumed a due occurrence and advanced its next time.
   `assistant_work.tick` now checks pause in the admission transaction, leaving
   due work for the resumed pass. A deterministic test pauses at 139 with a due
   time of 100 and a ten-second interval, then resumes and checks one work record,
   next due 140 and three coalesced additional occurrences.
2. Schedule registration accepted an identity too long for the later work
   origin. Configuration now validates bounded identity, session, prompt and
   route before storage. Duplicate registration requires a new identity rather
   than replacing the old job. `unschedule` disables future ticks and retains
   prior work. Stock watches use the same route validator.
3. The first live Chapter 7 child produced a correct draft tool observation:
   seven vanilla tubs at 250 pence, total 1,750 pence. Its final model sentence
   said £15.00. The old checkpoint exited zero because it checked only tool
   evidence. That run is retained as `FAILED_EXPLANATION`, not a successful
   business result, in `ch07-live-construction-v1.json`.

The repair is a small `draft_report` renderer in the store reference organization.
It uses actual successful draft observations, validates quantity and GBP pence,
and renders the latest estimate per SKU. It does not sum repeated calculations
as extra orders. Product labels are JSON-quoted so a newline cannot create an
additional report line. The worker persists this report for completed draft
turns; its raw model answer and transcript remain available for evaluation.
Supplier workflows retain their separate ledger-derived receipts.

The regression deliberately keeps the model's wrong £15.00 narration and checks
the correct £17.50 result all the way through `deliver_one` to the bot adapter's
outgoing payload. A second live child run verifies both the tool observations
and the persisted report. This is bounded evidence about draft facts, not a
general guarantee that model prose is true.

## Chapter and operational scope

Chapter 7 constructs the route validator, job registration, disabling, bounded
clock pass, stock-condition registration, scanner and draft renderer. It states
fixed UTC intervals, coalescing, observation-based stock episodes, capacity
differences and immutable product scope. The actual checkpoint starts
`agent serve` without a prompt or supplier endpoint and requires it to discover
the second stock episode from persistent state.

The chapter includes the minimal Linux user-service path now; maintenance stays
in Chapter 15. Existing isolated-host receipts prove real service installation,
restart, reboot and release changes. A service observation on this increment's
committed release is the next operational check. The draft score is structural
evidence only; site synchronization, rendered review and publication acceptance
remain open. Eight chapters are drafted and eight remain planned.

The NanoClaw comparison is pinned to the inspected host-sweep source and
distinguishes the authors' documented periodic-rescan rationale from our
interpretation. It does not repeat the supplied feedback's unsupported claim
that the project conflates liveness and work.
