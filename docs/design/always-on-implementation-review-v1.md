# Always-on implementation: first review disposition

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

This is an implementation checkpoint, not completion of the sixteen-chapter overhaul. It follows the operator's instruction to implement the merged recon in full. The existing manuscript and labs stay executable during migration.

External input: [org issue 603](https://github.com/rodriveracom/org-zeroemployeeorg/issues/603). Review 1 is contract-level; review 2 inspected base `a68da4b66be411f1d0b362bcefb0b1facf0b9bfb`, not these new local files. Neither is independent approval of this implementation.

Review receipts:

- [Review 1](https://github.com/rodriveracom/org-zeroemployeeorg/issues/603#issuecomment-5570906451): body SHA256 `7bc87d3a53916306616cf33fc48a2a2123c8bb5cf1339bd90ad0c1b05da7ebda`.
- [Review 2](https://github.com/rodriveracom/org-zeroemployeeorg/issues/603#issuecomment-5570991100): body SHA256 `abecccfc144816ddac23953e1827005db6c0664b7e12a7697894a4edc0616ae9`.

## Implemented construction checkpoint

The reader-owned model/tool/observation loop now reaches Lucy's actual SQLite inventory through `sovereign-agent agent ask`. It validates arguments, bounds calls and results, rejects repeated tool-call identities, and records transcripts. `HTTPModel` serves one model turn; the existing whole-assignment providers remain distinct.

`assistant_work` supplies one queue and one session claim for local intake, Telegram, and scheduled work. Due occurrence identity and schedule advancement commit with the work payload. Missed UTC intervals coalesce. Old organization-specific mailbox and execution mechanisms remain available for legacy labs; the new chapters will teach the single assistant work table.

`assistant_orders` binds a persisted operation ID to a work item and immutable proposal digest, independent of worker generation. Approval reserves cumulative spending. Unknown remote outcomes retain that reservation. The supplier runs in a separate process and database; the lost-response experiment proves discovery without duplicate purchasing. Receipt persistence rechecks current ownership.

Telegram intake commits its cursor and executable work together. Delivery records SENDING before transmission and preserves UNKNOWN instead of blindly resending. Local skill versions are immutable and require an explicit regression callback before activation. MCP has an explicit environment and tool allowlist, a protocol handshake, bounded POSIX pipes, and process cleanup.

HTTP requests now run in short-lived children with a parent deadline covering DNS, headers and body reads; the legacy HTTP provider uses the same transport. Credentials cross stdin, never command arguments or logs. Parent timeout does not cancel a remote effect or guarantee a provider stopped billing.

SQLite backup uses the online API. Restore prepares a checked image, pauses active authority, changes a separate authority marker, invalidates claims and approvals, and keeps restored state paused. It does not yet provide a reconciled resume workflow. The Linux service recipe is explicit; this macOS host has no running Docker engine, so no container execution or Linux service uptime claim has been made.

## Review disposition and remaining proof

| Finding | Implementation / evidence | Remaining work before acceptance |
|---|---|---|
| R1-1 / F-4 stable effect identity | Persisted UUID from work ID and proposal digest; replacement uses same order row; real supplier lost-response test | Hard-kill pause points and changed-target refusal |
| R1-2 atomic spending/admission | `BEGIN IMMEDIATE` approval reservation; fenced execution-time approval check before SENDING | Concurrent spend race, explicit authorization-point wording, immutable target binding |
| R1-3 / F-4 UNKNOWN exposure | Lost response and revoked-uncertain tests retain reservation, then convert to expenditure once | Delayed/refused supplier matrix and reservation invariants across all transitions |
| R1-4 restore | Backup/restore test rejects old worker and obsolete approval; restored control paused | Epoch bound directly to claim, full post-snapshot external-account reconciliation and reauthorization |
| R1-5 / F-7 intake | Complete payload and cursor in one transaction; malformed batch rolls back; replay creates one work item | Bot-account namespace, conflict and interleaved poller tests |
| R1-6 / F-3 scheduling | New UTC fixed-interval queue coalesces missed slots and persists occurrence identity atomically | Concurrent passes, rollback, stock-event conditions; legacy callback API remains a separate compatibility contract and must not be advertised as crash-recoverable work |
| R1-7 registry identity | MappingProxyType per dispatcher; duplicate names rejected | Target/schema-change regressions and MCP binding |
| R1-8 / F-2 resource bounds | Child-enforced total HTTP deadline; bounded response; slow-drip/oversize tests; legacy HTTP path repaired | Estimated model-exposure accounting, quota persistence, malformed protocol matrix |
| R1-9 hostile content | Tools remain allowlisted; skills have no approval API; known consequential tools need mediation | Injection attempts across every ingress and container-enforced restrictions |
| F-1 legacy mailbox cleanup | Both inbox and supervisor use one expiry-predicated UPDATE RETURNING in an explicit transaction | Forced stale-read regression and wider relay test receipt |
| F-5 lease duration | New claim lifetime exceeds loop budget; check before tools and mediated intent | Delayed-result/stale-before-send test, epoch continuity |
| F-6 Telegram credential/poller | Sanitized errors, no URL in evidence; immutable HTTP destination | Sentinel scan and exclusive poller lease; account binding |
| F-8 session/backlog | One live claimant per session; exact proposal digest approval; blocked work does not occupy a claim | Intake disposition table, queue and daily ceilings |
| F-9 skill provenance | Stored immutable version, source digest, selected skill content in transcript | Explicit content/system-prompt hashes and candidate/rollback evaluation receipt |
| F-10 MCP environment | Explicit environment parameter; sentinel subprocess test; stdio server killed on timeout | Shared allowlist review and bounded server-side input |
| F-11 shutdown | SIGTERM sets a stop event; current bounded pass drains | Real service-process termination during supplier wait, restart reconciliation before new intake |
| F-12 clocks | New durable times are epoch UTC; in-process deadlines monotonic | Nonfinite/naive-boundary matrix and legacy timestamp review |
| F-13 wording | Live output is replayable; offline fixtures reproducible | Apply distinction throughout new chapters and proposal |

## Work still required

Finish the review repairs, sandbox tool, cost/session quotas, contextual session history, controlled improvement, bounded delegation, and integrated acceptance. Then migrate and draft the complete sixteen-chapter manuscript with cumulative checkpoints, a pinned comparison appendix, proposal and sample chapters. Run the repository gates and the Prof Rod publication gates against the exact source commit, inspect the rendered sample, and obtain external review of pushed bytes. Current mechanical chapter scores apply to the preserved thirteen-chapter book only.
