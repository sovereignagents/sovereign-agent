**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** FINDING

# The final report must answer to receipts

The sixteen-chapter construction draft now has a cumulative accelerated-day
checkpoint. Actual supplier and research/stock processes use a shared shop ledger
plus a separate supplier database. The fixture corrects a stale preference,
records a failed model reservation, retries explicit work, deduplicates private
messages across reopen, refuses an unauthorized sender, creates scoped shortages,
requires exact approvals through the adapter control path, loses each new order's
first reply, kills the vanilla worker, waits actual lease/backoff, reconciles both
operations, receives vanilla once despite repeated receipt entry, and completes
a read-only catering inquiry. Authored expectations establish two supplier orders
and2600pence,8 vanilla physical,1 strawberry physical plus4 pending,12 chocolate,
sevenDONE work items,15 reserved model calls and30 configured estimated pence.
This is deterministic fixture evidence, not live phone/model or continuous uptime.

New reference_organizations/store/operating_report.py reads one SQLite snapshot
and renders structured amounts, stocks, work counts and exceptions without a
model call. agent report exposes it. Work/orders/spending are all retained local
history; model estimates cover the current UTC day. It is not a historical-day
query, invoice, revenue/profit report or external account audit. Pending
replenishment includes approved and uncertain requests, distinct from physical
stock. Order totals and spending are compared locally; independent supplier
comparison belongs to the checkpoint. Detail rows are capped with omission counts.

Nine tests cover empty history, approved exposure, unknown effect and delivery,
fluent false completion text, mismatched accounting, incomplete model usage,
concurrent committed inventory changes within one read snapshot, nested/failing
transaction cleanup, CLI without model calls and detail truncation. Some tests
combine these assertions. Initial tests left deliberate mutations uncommitted;
those fixtures were repaired, not the report's transaction refusal. Earlier day
prototypes had an invalid timeout/lease and assumed only one global lost supplier
response. Versioned failure evidence records the corrections without weakening
runtime boundaries.

All16 drafts execute139 Python examples and131 matching output pairs before the
final explanatory figure addition. Chapter16's shape score100 has3figures2tables,
5025instrument words; no publication acceptance follows. Site main advanced to
949979a through unrelated editorial PR61, with no diff in derive-book.mjs or
book-score.mjs; source score binds the actual instrument commit. Main README now
routes readers to the unreleased construction draft and distinguishes published
PyPI/legacy curriculum commands from checkout-only work.

Remaining full scope: final repository gate and review, exact-source site
migration with preserved legacy history, publisher proposal/frontmatter/reference
appendices/page measurement, latest report release on Linux, live phone and human
manuscript/render acceptance. Whole task remains active; chapters remain DRAFT.
