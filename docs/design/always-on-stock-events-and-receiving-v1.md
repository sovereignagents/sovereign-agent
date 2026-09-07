**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

# Stock episodes, scoped work and observed delivery

The full overhaul remains active. This checkpoint adds the stock-condition and receiving behavior required by the proposed scheduling and acceptance chapters. It does not mark those unwritten chapters as drafted.

## Decisions and implementation

Migration 21 adds a durable work subject, stock conditions, and delivery observations. Committed migrations 19 and 20 remain unchanged. The work subject is immutable and part of the current-claim check. The shop dispatcher filters stock observations and refuses another product's supplier/draft operations; the durable proposal boundary independently rejects another product for scoped work.

One active stock condition may watch a product. A partial unique index prevents aliases or another session from creating a second active watcher for the same need. A positive need admits one work item per condition episode. Repeated positive observations coalesce; a false observation rearms the condition. Disabling a watch preserves its history and already admitted work. Reenabling a disabled watch deliberately starts a fresh eligible observation. The teaching implementation permits at most one hundred stored condition definitions.

Condition state, intake, quota consumption and the triggering event commit together. If intake capacity is unavailable, the condition remains armed and no permanently rejected work item consumes its episode. A paused runtime does not consume conditions. Missing inventory is an explicit failure, not an inferred zero shortage.

`agent watch-stock SKU --id CONDITION` registers a watch; `agent unwatch-stock CONDITION` disables it. Both bounded `agent work` and unattended `agent serve` scan persisted conditions. Schedules and watches can specify `--channel telegram:BOT_ACCOUNT --recipient OPERATOR_CHAT_ID` with the appropriate session. Delivery still checks the current operator allowlist. Local output remains the default.

Scoped replenishment requires successful draft-tool evidence when current stock still has a positive need. A fluent completed model response without that evidence leaves the work `BLOCKED`. This is an outcome check for a defined stock task, not a general natural-language evaluator. A condition whose shortage disappeared before processing can finish without inventing an unnecessary draft.

`agent receive ORDER --delivery-ref REFERENCE --actor OPERATOR` records one operator-observed full delivery. It requires a confirmed order and current allowlisted operator, refuses paused restored state, and atomically updates physical stock, the delivery observation, and order status `DELIVERED`. Repeating the same reference returns an idempotent result; another reference for an already received order is a conflict. Receiving does not add spending again. Partial deliveries are not represented by this deliberately bounded interface; the caller must observe the complete order before using it.

Supplier acceptance continues to represent incoming stock. Only receiving moves the quantity into physical stock. Receipt reconciliation treats delivered orders as terminal and returns the stored acceptance without retransmission or another accounting transition. The existing inventory JSON record is updated alongside its authoritative physical-count column.

## Behavioral evidence

Fourteen focused tests cover cross-connection coalescing and rearming, atomic rollback, capacity deferral, immutable product scope through claims/tools/proposals, disabled and paused watches, CLI data flow, an actual unattended process, duplicate watcher refusal, configured channel delivery, and refusal of fluent output without draft evidence. Receiving cases prove physical/incoming counts of 2/6 before delivery and 8/0 afterwards, one spending entry, idempotent repetition, rejection before confirmation, and transaction rollback.

The channel-routing test uses a deterministic adapter fixture. It is not evidence of a live Telegram phone session. The unattended process test uses the actual offline service loop; Linux system-manager reboot and maintenance acceptance remain separate required work.

## Continue

Run the full gate before commit. Remaining runtime work includes bounded delegation, account-wide restore reconciliation with current inventory evidence, and Linux operational/integrated acceptance. Twelve manuscript chapters, publisher material, pinned comparison references, exact-source site migration and rendered review remain required. Restoring an old backup must also consider delivery observations lost after the snapshot; accepted-order receipts alone cannot reconstruct current physical stock.
