**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

# Recover the account, then resume the shop

The full overhaul remains active. Migration 23 and the account-recovery path implement the outstanding older-backup problem identified in both external reviews. The teaching supplier is one loopback-only account with durable idempotency records. This contract does not claim that arbitrary HTTP suppliers provide fencing or complete history.

## External evidence precedes local activation

The runtime binds a supplier endpoint to a durable random account identity and provider epoch before its first order. Initial binding requires an empty supplier account and no historical local orders; a missing historical binding cannot be invented from an endpoint string. Subsequent sends carry the bound identity and epoch. Lookups check account identity. Legacy unbound teaching clients work only while the supplier remains at epoch zero.

A restored database still starts paused with a new authority marker. Inspection uses that marker as an idempotent supplier rotation identity. The supplier commits the next account epoch and retains the rotation result. Requests bearing an earlier epoch are refused before purchase admission. Its serialized HTTP request handler means a request admitted before the fence is present in the subsequent export; one arriving after the fence is refused. A reply may still be lost. Repeating a rotation recovers the same result, and a later competing rotation makes the earlier snapshot request fail.

The export includes every retained accepted or rejected receipt, with an explicit completeness field. The server refuses exports exceeding one thousand orders instead of truncating them. The client bounds the response, validates operation identities, exact proposal shapes, outcomes and uniqueness, and checks the account and epoch. Previously conclusive local evidence must still exist with the same conclusion. A changed account, changed proposal, missing prior confirmation, duplicate receipt or incomplete export leaves the runtime paused.

## Purchase acceptance is not physical delivery

`agent inspect-account --supplier ENDPOINT` returns the fenced account and a recovery-plan template. Its counts, observation time and received/not-received booleans are null until the operator supplies observations. Every inventory SKU needs a current physical count and reserved count. Every accepted order needs an explicit delivery observation, with a reference if received. A previously recorded delivery cannot be silently reclassified as pending or given a different reference. The observation time must be within the preceding hour; that freshness check does not independently establish the truth of a human recount.

`agent recover-account PLAN.json --digest SHA256 --supplier ENDPOINT --actor OPERATOR` binds activation to the exact reviewed bytes, restored authority epoch and bound supplier account. Reading a changed file or supplying another epoch fails. Inside one local transaction, recovery rechecks paused authority and the external marker, imports missing operations, reconciles known orders, records observed deliveries, installs the recount, recomputes cumulative supplier spending and releases obsolete reservations.

Imported receipts preserve their external operation IDs. A synthetic work record explicitly identifies their provenance as account recovery; it does not pretend to reconstruct the lost original assignment. Receiving observations do not add stock again: the supplied physical recount is authoritative for this activation. Supplier acceptance that has not been observed as delivered remains incoming stock.

Old pending work is cancelled, old approvals are revoked, and potentially repeated outbound messages are marked uncertain. Enabled stock conditions rearm and schedules advance to fresh eligible times. New work uses current policy. Spending may already exceed the local ceiling after importing external history; recovery records that fact and the existing write gate refuses additional spending rather than erasing historical cost. Repeating the exact completed recovery is idempotent and cannot renew authority or grant money again.

## Lost model usage requires a new allowance

A supplier export cannot recover model calls newer than a backup. Recovery therefore marks the affected current-day model history incomplete and closes each known session's previously available allowance. The exact plan may explicitly grant additional calls and estimated monetary exposure through model_grants; an empty mapping grants none. For example, lucy's grant may contain calls: 5 and estimated_pence: 100. These are newly authorized additional bounds, not a claim that past missing usage was zero. The recorded known counters remain intact, and repeated recovery cannot replenish the grant. Normal UTC daily policy resumes on the next day. Estimated exposure is not a provider invoice cap.

## Operational evidence and limits

The first Linux proof uses Ubuntu 24.04.4 LTS aarch64 in the isolated sovereign-teaching-sap3 VM, Python 3.14.7 and the frozen runtime-only installation. Both actual user services installed and ran. A forced main-process kill increased the service restart count from zero to one. A real guest reboot changed the kernel boot ID; both enabled services returned and consumed persisted work. The main and research workers then completed separate stock and catering assignments. A SQLite backup was made through the actual maintenance function. Evidence: linux-operation-v1.json, based on the tested migration-22 tree. It is an offline-model operational proof, not a month of uptime, a live phone session, or the final migration-23 recovery acceptance.

Remaining required work includes final Linux upgrade/rollback and account-recovery acceptance, integrated business-day proof, twelve manuscript chapters, publisher material, pinned comparisons and exact-source site integration with rendered review. No completed-book or publication-acceptance claim is made at this checkpoint.
