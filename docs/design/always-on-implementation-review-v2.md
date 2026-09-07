# Always-on implementation: adversarial review repairs

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

This version follows [the first disposition](always-on-implementation-review-v1.md). The operator delegated implementation and project decisions. The full book/runtime overhaul remains active; this document records the second construction checkpoint. Review identifiers below refer to [issue 603](https://github.com/rodriveracom/org-zeroemployeeorg/issues/603), whose two reviews assessed the contract and earlier base, not this patch.

## Decisions now implemented

The order identity includes the supplier destination as well as the exact proposal and work ID. An SQLite trigger rejects mutation of those identity fields. Execution verifies that destination, current operator allowlist, aggregate reservation, installed spending ceiling, approval expiry, cancellation, ownership generation and remaining lease before committing SENDING. **That commit is the authorization point.** Revocation or process replacement after it cannot recall a transmitted request. An adapter's idempotency promise remains an external assumption; no local transaction provides exactly-once HTTP effects.

Unknown outcomes retain reserved spending. Reconciliation runs before new model work, including after SIGKILL between the supplier's independent commit and the local receipt. Every order in the task must receive a conclusive disposition before the task becomes DONE. DRAFT and APPROVED siblings cannot disappear behind the recovered order's success. Confirmed orders count as incoming stock until a separate receiving operation records delivery; accepted is not delivered.

SIGTERM requests shutdown and drains the current bounded request. The loop checks the stop flag before another model call and every tool call; the order workflow checks before every new send. The Linux service stop allowance is 90 seconds. A hard kill leaves durable SENDING, which is treated as uncertain. Recovery may require several bounded lookups and backoff while the supplier is still responding. The tests require one remote purchase and no new model work before reconciliation, not an immediate success-shaped first log line.

Ordinary sessions admit at most 20 pending requests and 50 requests per UTC day. Duplicate identities do not consume allowance. Rejected intake has a durable disposition and does not invoke the model. Authenticated Telegram approval/revocation/cancellation commands have their own 20-pending/200-daily allowance and priority. Recovery continues accepting those controls while ordinary work is held. Model calls reserve a daily allowance before transmission: at most 100 calls and 1,000 estimated pence per session/day. Estimated exposure survives lost responses. This is local accounting, not a provider invoice guarantee; zero configured estimate means no monetary estimate, not free inference.

Telegram cursor, intake identities, session IDs and exclusive polling leases include the bot account. Conflicting duplicate payloads fail the transaction. Only one poller may enter getUpdates for an account at a time. Outbound ambiguous delivery remains UNKNOWN rather than being silently retransmitted. A process-level transport sentinel test verifies that token-bearing URLs do not enter exception text.

Claims now carry the authority epoch directly. Restore changes both the durable control epoch and the separate host marker, and remains paused. A stale generation cannot regain authority through restored rows. **Account-wide post-snapshot reconciliation and an explicit reauthorization/resume procedure are still required.** A backup may omit orders accepted after its snapshot; checking only restored order IDs would be insufficient.

Legacy inbox and supervisor cleanup share an expiry-predicated update. Forced interleaving tests demonstrate that a fresh replacement claim survives a stale cleanup read. `Database.immediate()` refuses a pending transaction rather than implicitly committing it when changing connection mode. The old foreign-key rejection test now rolls back its deliberately failed transaction explicitly.

Context includes bounded excerpts of completed work from the same session, explicit preference provenance, immutable skill source/content digests and an assembled-context hash in the event log. These are evidence and guidance; they cannot grant tool authority. Erasing a preference does not erase historical transcripts or backups.

## Container evidence

The report runner uses a digest-pinned image, a read-only input mount, no network, no capabilities, a non-root user, a read-only root filesystem, bounded memory/processes/CPU, bounded output and a host deadline. There is no host-Python fallback. Docker container removal is checked after normal completion, timeout and excessive output.

Actual tests ran against `python@sha256:c6ead215bfd31f1e433d968853b7a769989117115b728874824e6c0a27cb96fc` in a separate Colima profile on the development Mac. Generated code observed UID 65534 and only loopback networking, could read its supplied data, could not modify the input or protected filesystem, and did not receive a Telegram credential. These observations support the stated narrow sandbox contract; they do not prove that a container solves prompt injection or that the host kernel has no vulnerabilities. The existing Docker context was preserved.

## Evidence mapping

| Review findings | Behavioral evidence |
| --- | --- |
| F-1 cleanup race and transaction semantics | `test_always_on_review_regressions.py`: forced interleaving for inbox and supervisor, pending transaction preserved |
| R1-1/2, F-4/5 identity and authority | Concurrent £70 approvals against £100; changed destination and expired ownership make zero supplier calls; process restart keeps the same remote operation ID |
| R1-3/F-11 uncertainty and shutdown | `test_assistant_shutdown.py`: SIGTERM and SIGKILL after remote commit; reservation retained, one supplier row, reconciliation precedes new queued work; no second purchase after stop |
| R1-5/F-6/7/8 intake and controls | Separate bot accounts, conflicting duplicate, exclusive poller, token sentinel, persistent quota, controls admitted despite a full ordinary backlog |
| R1-6/F-3 scheduling | Concurrent due passes create one occurrence, three-hour lateness coalesces, backwards clock creates no duplicate, transaction rollback preserves the due slot |
| R1-8/F-2 bounded transport and model exposure | Slow-drip and oversized HTTP responses, lost model reply retains estimated exposure, daily reservations persist after reopening |
| R1-9/F-10 execution boundary | Explicit MCP subprocess environment and allowlist, bounded server input, real container restriction/timeout/output tests |

## Remaining acceptance work

The remaining work includes the full supplier rejection/delay matrix, explicit restore reconciliation procedure, stock-event wiring, evaluated skill changes and rollback, bounded delegation, optional sandbox/MCP tools in the cumulative agent, and the integrated business day. Then all sixteen chapters, runnable checkpoints, pinned source comparisons, publisher proposal and Prof Rod publication gates must be completed. Existing thirteen-chapter scores are not evidence about the new manuscript. No independent reviewer has yet accepted the new implementation bytes.
