**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** FINDING

# From governed assignments to an always-on agent

This reconnaissance supports a major book and runtime update. It records the
current implementation, a proposed teaching sequence, and the observable
conditions the new promise must satisfy. It does not claim that the revised
book or runtime has been implemented or accepted by a publisher.

## Direction and reader promise

Working title: **Build Your Always-On AI Agent From Scratch**.
Working subtitle: **Tools, memory, permissions, and reliable operation in Python**.

The reader is a Python-capable builder. Lucy owns the ice-cream shop and is
their customer. By the end, the reader's agent accepts requests from Lucy's
phone, remembers appropriate preferences, wakes for scheduled work, requests
permission, and recovers without blindly repeating purchases.

The Operator's 7 September direction settles the product boundary: Sovereign
Agent remains self-contained and educational. Telegram, MCP, and other taught
integrations belong in this repository and installable distribution. Zeocore
is an optional route to broader capabilities, never a prerequisite for the
main lessons. A simpler implementation means fewer supported cases and more
explanation; it must still enforce the safety properties the chapter claims.

Recommendation: the reader implements and retains a small model/tool loop.
Models supply inference; they do not supply the loop being taught. Existing
CLI-agent providers remain an alternative worth comparing after the reader
understands the components. Building a tiny loop and then discarding it in
favor of an opaque CLI would weaken the proposed central promise.

“Always-on” means unattended availability while the host and dependencies are
available, with explicit durable intake, restart, and recovery behavior. Idle
waiting must not call a model. It does not promise uninterrupted service.

## Ground and verification

The survey uses these immutable source states. File:line references below are
against these states, not an unspecified future main branch.

| Repository | Inspected source |
| --- | --- |
| Sovereign Agent released main | `3ad8e52788b9c10902e166cf3ddc6fa108e22a12`, version 1.4.0 |
| Sovereign Agent preserved editorial candidate | `3f7634eae84ebfeb0fbcd5dafed4862bc7157bde`, two commits ahead, no divergent main commits |
| Prof Rod site | `351dc3f585b7818499a85785ef5126b2028549a1` |
| Zeocore | `0a65423154c0d25384c19f534e88ee3598fef89e` |

The runtime is unchanged between the first two states. The second retains
PR #86's source-owned book manifest, part openers, figure captions, listing
titles, ecosystem material, and structure gate. Preservation is not a claim
that PR #86 received independent review: its review state was REVIEW_REQUIRED.

Fresh checks against the editorial candidate:

| Check | Observed result |
| --- | --- |
| `make verify` | Exit 0; Ruff formatting/lint, strict mypy, dependency and size gates, curriculum, snippets, depth, structure, labs, demo, and onboarding |
| Main pytest run | 476 passed, 10 live tests deselected |
| Source budget | 35/40 modules; 7,207/7,250 nonblank lines; 7/30 root exports |
| Executable chapters | 13 exercises; 102 Python blocks; 92 expected-text pairs |
| Companion labs | 13 labs; solutions deterministic twice |
| Clone-equivalent onboarding test run | 471 passed, 5 Git-checkout checks skipped, 10 live tests deselected |
| Site's committed chapter report | Reproduced by `make check-book-ready`; 13/13 at least 90; range 93–99, average 96; bound to source `decff5e6150e01d001bcb28b4d20819e57b8e30a` |
| Fresh projection of editorial candidate | In an isolated site snapshot, sync and readiness passed; 13/13 at least 90; range 93–99, average 96; bound to `3f7634eae84ebfeb0fbcd5dafed4862bc7157bde` |

No live model, Telegram, supplier, service installation, browser render, or
human comprehension acceptance was performed. The site checks used its
current committed scripts and the existing installed Node dependencies;
this was a book-gate run, not a clean-install or full-site verification.

The manuscript inventory covered all 13 chapter structures and targeted
mechanism passages. It is not a line-by-line editorial assessment of every
paragraph. Passage-level migration still needs author review.

## Corrections to the supplied feedback

1. **The size claim is stale.** `scripts/verify_source_budget.py:42` sets
   7,250 nonblank lines; the measured runtime occupies 7,207. There are five
   module slots but only 43 lines of remaining headroom. Do not put “under
   6,500 lines” in a proposal. The counter includes comments and docstrings
   and excludes `src/reference_organizations`, tests, and labs; it is not the
   size of everything the learner must read.
2. **The HTTP provider has no tool loop.**
   `src/sovereign_agent/providers/openai_compatible.py:104` posts messages and
   extracts response content. `:137` calls it once, parses an `ActorReport`,
   and writes artifacts. There is no tool-request dispatch or observation
   round-trip here. “Raw HTTP loop” is an inaccurate description of this file.
3. **Discovery is not dispatch.** `src/sovereign_agent/tools.py:15` describes a
   tool by name, description, and keywords. `:36` ranks tools and `:52`
   authorizes a selected name. Argument schemas, executable handlers, model
   tool-call parsing, and result routing still need to be built.
4. **Existing mechanisms are useful seeds, not a connected assistant.**
   `src/reference_organizations/store/advanced_demo.py:8` imports memory,
   context, tools, automation, isolation, and coordination for its separate
   demonstration. The model request at `providers/openai_compatible.py:151`
   contains the assignment scope; it does not consume retrieved preferences
   or the session-context builder. Component tests do not establish that pipe.
5. **Local effects do not prove ambiguous remote-effect recovery.**
   `src/reference_organizations/store/__init__.py:481` commits inventory,
   cash, effect identity, and an event inside SQLite. This is valuable local
   idempotency. A supplier accepting an HTTP order before dropping its reply
   is a separate failure boundary and needs a separate teaching implementation.
6. **The three alleged non-goal reversals are different cases.**
   `docs/non-goals.md` refuses channels as core features, plugin marketplaces,
   container workers, and silent background daemons. A local skill file is not
   a marketplace. `docs/v1-removal-manifest.md` explicitly says to replace
   `service/` with an explicit service command; `src/sovereign_agent/cli.py:203`
   calls that command not yet built. Service work is an unfinished declared
   intention, not evidence of a blanket hosting prohibition. Record the
   precise updated boundary, authorization, and CHANGELOG entry when the
   implementation packet changes it; do not invent three identical blockers.
7. **The book-home fork has prior decisions.** The source is already
   `sovereign-agent/book`; Prof Rod's site derives it from an exact commit.
   Keep that one-way relationship. No second editable manuscript is needed.
8. **Comparative superiority remains unproven.** Claims that no reference
   project handles injection as a layer, that none has equivalent fencing,
   or that two projects conflate liveness with work require a bounded source
   audit. CVE details, malicious-package counts, code-size comparisons,
   acquisition odds, and SEO gains are not established by this recon.

The first feedback provides the stronger reader progression. The second
correctly values the existing reliability mechanisms, but preserving their
current sequence would defer the new reader's useful agent too long. Reuse
the mechanisms while changing the learning sequence.

## One behavioral gap reproduced

Hypothesis: a process exit inside an automation payload leaves its due slot
claimed without a resumable delivery record. Evidence: `automation.py:95`
persists a RUNNING row and `:108` advances the schedule before `:116` invokes
the payload. The failure and success updates occur only after that call.

Falsifier: reopen the database after the payload process exits and demonstrate
that the same scheduled occurrence resumes or receives an explicit durable
recovery disposition.

A fresh-database probe created a 60-second automation due at
`2026-09-07T12:00:00+00:00`. Its child process called `os._exit(23)` inside
the payload. On reopening the database and calling `run_due` at the same due
instant, the observed result was:

```text
child exit:                 23
persisted automation run:   RUNNING
restart result:             NOT_DUE
restart payload calls:      0
```

This proves the specific `run_due` restart gap. It does not claim to simulate
every host failure or all supervisor paths. The implementation requirement is
to create durable work atomically with consumption of the due slot, then let
the worker recovery mechanism own that work. Replaying an arbitrary callback
would reintroduce uncertain external effects.

## Proposed cumulative curriculum

Numbering below is the new book's numbering. It is not a rename already
applied to the current `ch00`–`ch12` directories. Every checkpoint must work
offline with deterministic model and supplier fixtures; the live paths use
the same interfaces.

| Chapter | Decision and useful result | Build and falsify |
| --- | --- | --- |
| **Part I: Build a useful agent** | | |
| 1. An agent for Lucy's shop | What do the model, agent loop, and runtime each do? Produce a morning brief. | Several products from the first fixture; one model call; label the finished-system preview; missing credentials have a usable offline path. |
| 2. Give it tools | Which work belongs in deterministic Python? Ground a recommendation in stock and supplier records. | Typed arguments, handlers, results, read/write classification; reject unknown products, invalid quantities, and undeclared tools before handler invocation. |
| 3. Build the agent loop | How does a tool result become the next model input? Produce a replenishment draft. | Own model/tool/observation cycle; bounded calls, time, context and spending; reproducible transcripts; repeated requests cannot run forever. |
| **Part II: Give it continuity and initiative** | | |
| 4. Memory beyond the conversation | What should survive tomorrow? Remember Lucy's supplier preference. | Sessions, preferences, provenance, correction, forgetting, retrieval and context limits; authoritative stock stays in structured records. |
| 5. Reuse a procedure as a skill | How does guidance become reusable without granting authority? Reuse the opening check. | Local readable files, declared requirements, versions, examples, controlled activation; a hostile skill cannot widen tool permissions. |
| 6. Talk to it from your phone | Who is speaking, and which session owns the request? Lucy requests a brief remotely. | One Telegram adapter implemented here, offline transport, allowlisted sender/chat, durable update IDs, conflict serialization, bounded reconnect and output delivery. |
| 7. Wake for schedules and events | When should work be created? Produce unattended briefs and stock alerts. | Durable due-slot-to-work transaction, time-zone and missed-run semantics, bounded retries, minimal explicit service-manager recipe; reports and drafts only. |
| **Part III: Act with permission and recover** | | |
| 8. Ask before acting | Which exact purchase did Lucy authorize? Execute permitted simulated orders. | Digest-bound proposals, supplier/operation limits, cumulative budget reservation, expiration, revocation, persistent approval and execution-time revalidation. |
| 9. Survive an ambiguous order | Did the supplier accept it? Reconcile without blind duplicate purchasing. | Independent supplier process and database, stable operation ID, intent before call, receipt after discovery, unknown outcome and human resolution when discovery is unavailable. |
| 10. Recover work after a crash | Which worker owns the task now? Resume abandoned work safely. | Reuse claims, leases and execution fencing; real process failure; stale attempts cannot authorize writes; keep in-flight external uncertainty separate. |
| 11. Connect and isolate external tools | Where does untrusted execution stop? Call a bounded MCP tool and run one isolated report tool. | Small in-repo MCP transport and adapter, protocol negotiation and limits, hostile tool metadata/documents, mediated effects, one explicit container recipe with filesystem/network/resource restrictions. Split protocol details into an appendix if the measured chapter becomes overloaded. |
| **Part IV: Evaluate and operate it** | | |
| 12. Measure whether it helps | Does agent reasoning beat the scripted baseline? Produce a repeatable evaluation report. | Deterministic tests versus model evaluations; business correctness, unsupported claims, policy violations, cost and latency; held-out cases and run variation. |
| 13. Improve without losing control | Was Lucy's correction a fact, preference, skill, tool, prompt, or model problem? Activate a tested improvement. | Candidate versions, provenance, regression suite, explicit activation and rollback; do not imply model-weight training. |
| 14. Delegate one task and justify it | Does a second agent earn its cost? Research a catering request during stock work. | Bounded handoff, context, authority, deadline, cancellation, duplicate results and budget; compare against one agent and a plain function. |
| 15. Deploy, observe, and maintain | What survives the terminal closing and the host rebooting? Operate one Linux installation. | Standard service manager, graceful shutdown, pending-work age, secrets, SQLite-safe backup/restore, reboot, schema-aware upgrade and rollback; macOS appendix. |
| 16. Lucy leaves for a day | Can the whole system complete useful work unattended? Produce a reconciled daily report. | Accelerated business day with duplicate intake, stale memory, provider failure, ambiguous supplier response, expired approval, crash and restart; trace every reported result to evidence. |

MCP is part of the shipped teaching scope, not a requirement to install
Zeocore. A narrow standards-conforming client is preferable to a general
protocol framework: support one transport and a declared protocol version,
and refuse unsupported capabilities. Any new SDK dependency needs its own
review; the current lockfile and pydantic-plus-stdlib path remain the starting
point. The sandbox lesson requires an explicit change to the existing 1.x
container boundary; an application allowlist is not an OS sandbox.

## Migration of every current chapter

| Current source | Proposed destination | Preserve |
| --- | --- | --- |
| ch00 first shift | 1–3 and final acceptance preview | Observable result and adversarial verification; progressively expose the implementation. |
| ch01 organization remembers | 4, 9, 10 | SQLite atomicity, migrations, canonical/derived data, memory retrieval; separate preferences from recovery evidence. |
| ch02 work needs governance | 8, 12, 14, 16 | Authority, evidence/review/acceptance graph; introduce internal SOW vocabulary only when useful. |
| ch03 actor is not a model | 1, 3, 4, 10 | Actor/provider distinction, hostile response parsing, recoverable context and discovery versus authorization. |
| ch04 work stays inside its boundary | 8 and 11 | Workspace attacks, four policy planes, detection versus prevention, honest process-isolation limits. |
| ch05 authority needs a fence | 8 and 10 | Mailbox claims, execution attempts, session incarnations; distinguish human permission from worker ownership. |
| ch06 organization recovers | 9, 10 and 15 | Real hard-kill lab, liveness evidence, reconciliation, terminal-state consistency. |
| ch07 organization wakes itself | 7 and 15 | Signal-to-work transaction, condition/payload separation, heartbeat distinction, replay and correlation failures. |
| ch08 store becomes a catalog | 1–2 fixtures; 7 and 16 exercises | Batch validation, catalog migration and SKU isolation as demanding exercises. |
| ch09 product thresholds | 2, 7 and 16 | Stock arithmetic, per-product rules and concurrent sale invariants. |
| ch10 one signal wakes one need | 7, 9 and 16 | End-to-end identity, exact causal binding, live-state revalidation. |
| ch11 replenishment scales | 8–10 and 16 | Local transaction/idempotency and concurrent-effect exercises; explicitly distinguish remote orders. |
| ch12 pilot receipt | 12, 15 and 16 | Proof-pack lie detection, reproducibility, artifact identity and acceptance evidence. |

Keep existing labs runnable during migration. Add stable lesson/checkpoint
identities and an explicit legacy-to-new map before renumbering. Preserve old
URLs with redirects at the site. A chapter may reuse several legacy labs;
it need not pretend one old lab equals one new chapter. Rename chapters,
update manifests and links, and update gate discovery in one verified packet.

Concrete coupling to update includes `scripts/verify_curriculum.py:32`
(required chapters), `:54` (position-based Pulse restriction), `:64` (required
production entrypoints), `scripts/verify_book_labs.py:29` (lab list),
`scripts/verify_book_structure_v1.py:61` (exact 0–12 partition), chapter depth
and coverage manifests, and site derivation/navigation. Replace positional
assumptions with declared lesson capabilities; do not simply weaken checks
to accept arbitrary directories. The site chain checker already discovers
chapter directories: its “13 chapters” comment is not proof of a fixed count.

## Runtime architecture and the Zeocore boundary

Proposed data flow:

```text
Telegram / local input / due schedule / stock signal
  -> authenticated, deduplicated durable intake
  -> durable work and owned session
  -> bounded model loop + context + versioned skills
  -> typed tool dispatch
  -> current permission + budget + worker fence
  -> local Python tool / bounded MCP tool / optional Zeocore adapter
  -> tool observation + effect state + verifiable report
```

All taught adapters and orchestration stay in the Sovereign Agent
distribution. Separate modules by responsibility, but count all teaching
runtime and integration code. Do not create an uncounted edge package merely
to advertise a small core. Report both core and total installed teaching
source, dependencies, and per-chapter added concepts. Set a revised numeric
budget from measured Chapters 1–3 and adapter prototypes before accepting
their implementation; preserve readable code rather than compressing it to
fit the old 43-line headroom.

Keep the current provider contract for CLI-agent execution. Introduce a
separate thin model-completion interface for the reader-owned loop; a CLI
that completes an assignment and an API returning one turn are different
abstractions. Do not silently reinterpret `IntelligenceProvider` methods.

Zeocore's inspected main contains MCP server and tool-adapter code:
`src/zeo_core/adapters/mcp/server.py:92` creates the server;
`tool_adapter.py:158` registers tools; `:221` begins its lifecycle invocation.
`src/zeo_core/tools/catalog.py` contains typed representative capabilities.
This supports a candidate integration route, not an already verified bridge.
No Telegram references were found in Zeocore's inspected `src`, `tests`, or
`docs`; do not promise a ready-made robust Telegram replacement there.

The older `docs/reports/sovereign-agent-capability-replacement-readiness.md:7`
describes Zeocore 0.5 and the old Sovereign Agent API. Its replacement table
is historical evidence, not a current 1.4 migration recipe.

Prefer a separate Zeocore process reached through the same bounded MCP
adapter, if compatibility tests establish that seam. Otherwise document and
test a narrow versioned JSON/subprocess adapter. Required contract tests:
success, typed error, timeout, malformed output, cancellation, unknown
external outcome, artifact digest changes, and current approval/fence checks.
Installing or contacting Zeocore must never be necessary for offline lessons.
A capability result must not manufacture Sovereign Agent acceptance.

## Acceptance cases that define the new promise

| Boundary | Required falsification |
| --- | --- |
| Model loop | Zero tools, unknown tool, malformed arguments, repeated call IDs, multiple calls, refusal, oversized result, timeout, exhausted budget; no unauthorized handler invocation. |
| Memory and skills | Empty retrieval, contradictory preferences, actor/session separation, provenance correction and forgetting, poisoned guidance; authoritative records remain authoritative. |
| Telegram | Unauthorized sender and wrong chat, duplicate update, restart before/after acknowledgement, concurrent messages, oversized input, reconnect and rate limit. Separate inbound deduplication from uncertain outbound send delivery; do not promise exactly-once Telegram messages. |
| Scheduling | Not due, exact due instant, two schedulers racing, missed intervals, daylight-saving fold/gap, clock movement, failure threshold, crash before/after durable work creation; idle time makes zero model calls. |
| Purchasing permission | Exact spend threshold, cumulative reservation races, changed proposal, expired/revoked approval, restart with approval pending, supplier substitution; check current authority at execution. |
| Remote effect | Supplier commits then drops response; discovery finds existing order, discovery reports none, discovery unavailable; explicit UNKNOWN state prevents blind repeat. |
| Worker ownership | Process death and replacement, expired lease, stale worker and late result, cancellation during in-flight order; a fence cannot revoke a request already accepted by an external system. |
| MCP and isolation | Version mismatch, unknown method/tool, malformed/oversized frame, server exit, cancellation, hostile tool description, file traversal, forbidden egress and resource exhaustion. Unsupported sandbox capabilities refuse explicitly. |
| Operations | Reboot, pending approval/work recovery, disk failure, SQLite WAL-safe backup while active, restore into an empty location, upgrade and schema-compatible rollback, no credentials in prompts/logs/artifacts. |
| Zeocore seam | Same learner task works without Zeocore; adapter substitution preserves authority/effect semantics; unavailability and receipt/artifact tampering fail visibly. |

Test the expected result against independent business state, especially the
supplier's separate order ledger. A test baseline generated by the agent
under test is not sufficient. The final day must reconcile orders, spending,
pending approvals and unfinished work, including the empty-work day.

## Quality contract and execution order

Prof Rod's site already provides a useful mechanical gate. At the inspected
site commit, `Makefile:688` defaults `BOOK_SCORE_TARGET` to 90 and `:698`
defines `check-book-ready`. `scripts/content-lint/book-score.mjs:101` scores
depth, pedagogy, practice, visuals, SEO and craft. Its own header correctly
calls the score a prioritization instrument. The explicit readiness target
must be run for each candidate; do not assume general site verification
substitutes for it or edit `latest.json` manually.

For each chapter: useful result, one principal design decision, executable
increment, build/break/repair experiment, explained figures, prediction
exercise, expected observations, and independent learner verification. Gate
the source and exact derived commit, then review conceptual accuracy and
representative-reader comprehension. Publisher quality is not a score label.

| Packet | Concrete output and exit condition |
| --- | --- |
| 0. Preserve and establish ground | Existing editorial commits retained, obsolete local branches retired only after ancestry checks, current gates reproduced, this recon filed. |
| 1. Define contracts and migration | Record precise 1.x boundary changes and CHANGELOG entries; define model-turn versus assignment-provider interfaces, chapter/checkpoint identity, legacy routes, and complete-code accounting. |
| 2. Prove the opening | Build Chapters 1–3 together with runnable cumulative checkpoints. Measure code size, setup friction, explanation density and reader completion. Keep one provider in the main path. |
| 3. Prove the distinctive depth | Build Chapter 9's supplier with an independent durable ledger and lost-response experiment; integrate the Chapter 8 permission boundary before permitting writes. Draft the proposal sample from this proved mechanism. |
| 4. Prove unattended continuity | Connect memory, skills, Telegram, scheduled durable work and existing worker recovery; demonstrate Chapter 7 drafts unattended under a minimal supervisor. |
| 5. Prove external boundaries | Implement bounded MCP and sandbox lessons, protocol fixtures, and optional Zeocore substitution; extend threat-model documentation from tested behavior. |
| 6. Prove improvement and maintenance | Evaluation, controlled changes, justified delegation, Linux deployment/restore, and the integrated Chapter 16 day. |
| 7. Migrate and prepare the proposal | Complete passage-level migration, update source manifests and site projections together, retain legacy links, run all gates, review renders and learner trials, assemble proposal and sample chapters. |

These are dependency packets, not permission to call partial coverage a
finished book. Within them, chapter checkpoints must remain cumulative even
when the author prototypes Chapter 9 early. Numeric code/page budgets and a
publisher schedule should follow the sample measurements, not replace them.

## Comparative sources and publisher evidence

Keep OpenClaw, NanoClaw and Hermes as recurring examples; use NemoClaw and
OpenShell specifically for host enforcement/deployment. Organize the book by
decisions. Each finished comparison needs a release/commit, exact code/docs,
documented author rationale separated from our inference, and a trade-off
experiment. Retire any comparison whose evidence cannot support its claim.

Primary project pages checked on 7 September 2026:
[OpenClaw](https://github.com/openclaw/openclaw),
[NanoClaw](https://github.com/nanocoai/nanoclaw),
[Hermes](https://github.com/NousResearch/hermes-agent), and
[NemoClaw](https://github.com/NVIDIA/NemoClaw).
These landing-page checks establish research starting points, not a pinned
architectural audit. This document deliberately makes no “only project that”
claim from them.

[Manning's proposal guidance](https://www.manning.com/write-for-us) asks for
timeliness, differentiation, reader learning, and author suitability. Prepare
those answers with Chapters 1–3 and the ambiguous-order sample as evidence.
The new positioning is an editorial recommendation; neither acquisition odds
nor Raschka-equivalent teaching quality has been established by this recon.
