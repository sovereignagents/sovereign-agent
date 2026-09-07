# Changelog

All notable changes to sovereign-agent.

Repository: [`profrodai/sovereign-agent`](https://github.com/profrodai/sovereign-agent).

## Unreleased

- Replace the core-only source gate with a versioned gate counting all installed
  teaching code: 55 core modules / 11,000 lines and 80 installed modules / 14,000
  lines, under the measured 2026-09-07 budget ruling. Historical gates are retained.

- Authorize the self-contained always-on teaching scope: a reader-owned model
  loop, Telegram, bounded MCP, local skills, explicit service hosting and one
  isolated tool. ZeoCore remains optional. The 1.x non-goals are amended by the
  dated ruling; published 0.x contracts remain unchanged.

## [1.4.0] — 2026-09-05

Sovereign Agent 1.4.0 is a correctness release for two boundaries the
executable book teaches learners to distrust: replacing durable files and
selling inventory already promised elsewhere. It turns both claims into
behavioral guarantees without adding a runtime dependency.

- Make `atomic_write` safe under concurrent writers by using a unique
  same-directory temporary file, syncing its contents before replacement, and
  cleaning it on both success and failure. Parent-directory durability remains
  an explicit boundary rather than an implied guarantee.
- Make sales honor reserved inventory and reject non-positive quantities before
  any ledger write. Low-stock severity now derives from post-sale available
  inventory, with adversarial and concurrent-buyer regression coverage.
- Reconcile the executable manuscript with those runtime contracts, add a
  digest time-of-check/time-of-use diagram, and remove the final two declared
  implementation gaps from the book coverage manifest.

## [1.3.0] — 2026-09-05

Sovereign Agent 1.3.0 turns six patterns from current agent systems into small,
offline mechanisms that learners can inspect, break, and repair. It also brings
the complete executable book to a deterministic 90+ editorial score on every
chapter. The score is a prioritization instrument, not a publisher endorsement.

- Integrate all six advanced mechanisms into the canonical thirteen-chapter
  manuscript: hybrid memory in Chapter 1; recoverable context and bounded tool
  discovery in Chapter 3; five-plane isolation in Chapter 4; session
  incarnations in Chapter 5; and durable condition automation in Chapter 7.
  Each treatment includes an implementation-grounded diagram, a runnable
  chapter extension, an adversarial mutation, precise expected invariants, and
  a coverage-manifest binding to production symbols and tests.
- Add six self-contained advanced teaching mechanisms: honest four-plane
  isolation policy and explanation, persistent condition scheduling distinct
  from heartbeat and Pulse, append-only transcript compaction, multi-host
  session incarnations with durable delivery attempts, bounded tool discovery
  separated from authorization, and hybrid memory ranking with pre-ranking
  access control and score provenance.
- Add `sovereign-agent mechanisms`, an offline reference scenario exercising
  all six against the real package and SQLite schema.
- Add the Advanced Mechanisms book companion and adversarial regression suite.
  Runtime dependencies remain exactly `pydantic`; all new machinery uses the
  Python standard library and the existing SQLite ledger.
- Deepen the executable manuscript with front matter, conventions, a summary in
  every chapter, course-derived mechanism traces, 38 implementation-grounded
  Mermaid diagrams, and adversarial exercises. The canonical thirteen chapters
  now contain 102 executed Python blocks and 92 byte-matched output pairs; all
  thirteen companion labs remain deterministic across two fresh runs.
- Add a hostile-`PATH` onboarding proof that runs the README's documented
  `uv run` commands from a clean archive and refuses stale global `python` or
  `sovereign-agent` shims. The proof is part of both `make verify` and CI.
- Harden the six-stage release-candidate verifier by bootstrapping its clean
  virtual environment in a fresh Python process. Environment-creation failures
  are now reported as named gate findings instead of unclassified tracebacks.
- Establish `profrod-site` as the derived rendered home while keeping this
  repository's `book/` tree canonical. The site imports an exact commit and
  reports per-chapter editorial scores without writing derived metadata back
  into the public manuscript.

## [1.2.0] — 2026-09-02

- **New `heartbeat` mechanism, deliberately separate from work.**
  `sovereign-agent heartbeat` records or reads a durable liveness beat: an
  append-only `heartbeats` table (a plain `INSERT`, no update path — history
  of beats is a record, not a mutable "last seen" field) that lives apart
  from the `events` ledger by design, so "the process is running" can never
  masquerade as "governed work happened." Default invocation appends one
  beat (`--source <name>`, default `cli`) and prints its id; `--status`
  reads the newest beat and prints a verdict — `ALIVE` (a beat within
  `--stale-after` seconds, default 900), `STALE` (no beat recorded in the
  window — proof of silence, not of death), or `NO_BEATS` (the table is
  empty) — and exits `0` only on `ALIVE`, so a cron or watchdog can key off
  the exit code directly. This is explicitly **not** the Pulse: the book's
  chapters use "heartbeat" informally for the organization waking itself to
  create work (`sovereign-agent pulse`); this mechanism creates no work,
  ever, under any circumstance.
- **Book pedagogy deepened with implementation-grounded diagrams.** Every
  finished chapter (ch00–ch12, both `full`-depth and guided-`tour`-depth) now
  carries at least one conceptual Mermaid diagram showing the real mechanism,
  not a rendering of a transcript — the book depth verifier's finished-chapter
  gate (`scripts/verify_book_depth.py::check_depth_gates`) now refuses any
  finished chapter that has no such diagram, or one that is empty, backed by
  new regression tests in `tests/test_book_verifiers.py`. Chapter 7's Pulse
  narrative is sharpened into explicit stages (signal, wake gate, wake
  decision, execution) with a "four clocks" table distinguishing Signal, Pulse
  tick, Supervisor tick, and Heartbeat so the mechanisms are never mistaken
  for one another. Chapter 0's coverage manifest entry was corrected from an
  absolute "the organization has no heartbeat yet" to the narrower,
  still-accurate "this demo does not run an unattended scheduler or a
  heartbeat," now that a heartbeat module exists elsewhere in the package. A
  `known_gap` was added to Chapter 9's manifest entry documenting that its
  acceptance check models a stronger sale contract (reserved-stock aware) than
  production `record_sale` currently implements.
- **Modernized the public repository surface** (carried over from the prior
  Unreleased entry): complete community-health files, canonical project
  metadata, a complete Apache-2.0 license, typed-package signaling, and
  current 1.x architecture and API documentation. An obsolete pre-1.0
  manifest is no longer tracked as public project source.
- **Adopted fleet canon `zeo.yml` v2.2** (org issue #276): both CI jobs now
  pin `actions/checkout@v7` (up from `v4`), and the workflow file's own
  header now carries the canon marker recording byte-identical adoption.

## [1.1.1] — 2026-09-01

The curriculum release. The installed package's runtime behavior is
**identical to 1.1.0** — no source changes beyond the version string itself.
What this release versions is everything around the code: the book was
rewritten to executable depth, companion labs were added for every chapter,
and the repository gained the verification instruments that keep both honest.
Run it with uv (`uvx sovereign-agent@latest doctor`); read it by cloning
the repository, where the book and labs live (`uv sync && uv run
sovereign-agent doctor`).

- **The book, rewritten to build-break-repair depth.** All thirteen chapters
  (ch00–ch12) now construct each mechanism inline in small, cumulative,
  annotated increments; deliberately break a naive version and show the
  failure verbatim; then repair it into the shape the production package
  uses. Every python fence in every chapter is executed by CI and its
  printed output is byte-matched — 92 executed blocks, 82 verified output
  pairs. Each chapter maps its claims to exact production symbols and test
  node ids, shows the real refusal and recovery transcripts, and states
  plainly what it does *not* prove — ending with Chapter 12's boundary:
  internal consistency is not authenticity.
- **Thirteen runnable companion labs** (`book/labs/`). One per chapter: an
  intentionally incomplete starter, behavioral checks that grade observable
  invariants (not code shape), adversarial mutations, a verified reference
  solution, and machine-readable production source/test references. The lab
  gate executes every reference solution twice from fresh roots and compares
  observations against checked-in expected results.
- **Verification instruments, mutation-tested.** Three disjoint book gates
  now run in CI and `make verify`: `verify_book_snippets.py` (executes every
  chapter's python fences, byte-matches outputs, hardened against silent
  early-stop false-greens), `verify_book_depth.py` (coverage manifest:
  AST-verified symbol references, precise test node ids, per-chapter limits
  and break-evidence anchors, an explicit known-gap register, and identity
  binding of each chapter to its companion lab), and `verify_book_labs.py`
  (the lab gate above). The three instruments are pinned to one shared
  chapter denominator by test, and the false-green paths found during
  adversarial review are each held closed by a regression suite.
- **Fleet gate workflow.** The repository adopted the fleet-standard `zeo`
  check (governance lint fast lane on PRs, full-gate certify lane on main
  and nightly), alongside branch protection requiring an independent
  reviewing seat.
- **uv-first instructions everywhere current.** README, quickstart, and all
  thirteen chapters' runnable commands now use `uv` (`uvx
  sovereign-agent@latest` for zero-install runs, `uv sync` + `uv run` for
  the cloned repository) — every documented flow verified live against
  real PyPI and a fresh clone before being written. The quickstart's stale
  "PyPI still serves 0.x" warning, false since 1.0.0 published, is
  corrected. Legacy v0.x documents are deliberately unchanged.
- **Chapter 0 index correction.** The top-level book index now names the
  protagonist consistently with the chapter it links to.

## [1.1.0] — 2026-09-01

Adds a first-class **OpenAI-compatible provider** and makes the local-model
configuration documentation true.

- **New `ollama` provider.** A first-class provider that talks to any OpenAI
  `/v1/chat/completions` endpoint — a local Ollama by default, or vLLM, LM
  Studio, or OpenAI. Unlike the CLI-agent providers it speaks HTTP, but obeys
  the same contract: the model only *proposes* an `ActorReport`, which the
  organization re-validates against the ledger before anything commits. An
  unreachable or malformed endpoint yields an honest `failed` report, never a
  fabricated success. Bind an actor to it with `provider = "ollama"`.
- **Real, documented configuration.** The provider reads exactly
  `SOVEREIGN_AGENT_LLM_BASE_URL` (default `http://localhost:11434/v1`),
  `SOVEREIGN_AGENT_LLM_MODEL` (default `qwen3`, with
  `SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL` accepted as an alias), and
  `SOVEREIGN_AGENT_LLM_API_KEY` (optional; blank for local Ollama). These
  variables were previously documented but implemented by no source file; the
  documentation in `configuration.md`, `deployment.md`, `troubleshooting.md`,
  and `.env.example` now matches the code, and the stale v0.x
  `_PLANNER_MODEL` / `_API_KEY_ENV` variables are gone.
- **Source-line budget raised 6,250 → 6,400** to fit the new provider
  (~154 lines), sanctioned on the same precedent as the 6,000 → 6,250 raise.

## [1.0.0] — 2026-08-31

First stable release. The package is an executable textbook: Chapters 0-12
build a Zero-Employee Organization end to end — outcomes, statements of work,
assignments, atomic commit, independent verification, and principal
acceptance, with refusal as a first-class result. Intelligence is a bounded
actor, never the authority: a provider proposes, and every proposal is
re-validated against the governed ledger before it can commit. The
`reference_organizations.store` organization is fully worked, including live
provider tool-calling against a typed capability. Python 3.14; depends only on
`pydantic>=2`. The Unit 12 release-evaluation machinery below (redacted proof
pack, extended Andrea evaluation, and the installed-wheel release-candidate
gate) ships in this release; the previously-deferred publication is this
release itself.

### Release evaluation, redacted proof pack, Andrea protocol extension (Unit 12)

Builds the redacted proof-pack manifest and its field-schema-aware verifier,
extends the Andrea evaluation to the full 13-chapter curriculum with three
new scored tasks, builds a distinct release-candidate gate covering the
installed-wheel path, wires conditional truthful provider-status reporting,
and additively corrects two stale passages. This document's own status
stays `PROPOSED`; the Andrea live evaluation, the release-candidate
publication, and the final release are later, separately-authorized steps
outside this unit's implementation-acceptance scope.

- **The redacted proof-pack manifest and verifier.**
  `docs/evidence/unit12/proof-pack.json` (schema in
  `scripts/proof_pack_schema.py`) records source/release-candidate commits,
  versions, artifact digests, deterministic gate and installed-wheel
  results, local disposable pilot-mechanism evidence, the Andrea
  live-evaluation result, one status row per provider (exactly one of
  `LIVE_PASS`, `NOT_RUN_UNAVAILABLE`, `NOT_RUN_UNAUTHENTICATED`, `FAIL`),
  redactions, non-claims, and evidence digests. `scripts/verify_proof_pack.py`
  rejects missing fields, unknown statuses, digest mismatches, path escapes,
  and secret-shaped content -- **field-schema-aware**: known-shape fields
  (commit SHAs, SHA-256 digests, semver, paths) validate against their own
  shape and are never rejected for being long; free-text fields are scanned
  for exactly two narrow patterns (a credential env-var `NAME=value`
  assignment, or a literal `Bearer <token>` shape), no entropy heuristic.
  This unit's own gate produced a real, genuinely partial manifest: real
  evidence for everything this unit's own implementation can produce,
  honest `NOT_RUN` for the Andrea live evaluation and all three providers.
- **The Andrea evaluation, extended to Chapters 0-12.**
  `docs/andrea-chapters-0-12-evaluation.md` retains Tasks 1-7 verbatim
  (maximum 14) and adds Task 8 (multi-SKU isolation), Task 9 (pilot-start
  structured evidence, replay, refusal), Task 10 (local mechanism vs. a
  real deployment; identifying ZEO Go as the production path). New maximum
  20; pass at >=17/20 with no zero on Tasks 2, 7, 8, 9, or 10.
  `scripts/evaluate_andrea_chapters_0_12.py` covers Tasks 8-9's own
  machine-checkable reachability/evidence portions, declining to score
  Task 10.
- **A distinct release-candidate gate.** `scripts/verify_release_candidate.py`
  runs all 13 exercises twice from fresh roots, builds and installs the
  wheel into a clean Python 3.14 venv outside the source tree and runs
  every exercise against it (proving isolation directly by asking the
  venv's own interpreter where the package resolves from, not assuming
  it), validates the new Andrea rubric's machine-checkable portions,
  confirms the proof pack verifies, confirms no unbacked `LIVE_PASS`
  claim, and confirms no committed evidence claims the real pilot-start act
  occurred. `scripts/verify_curriculum.py`'s own scope is unchanged.
- **Truthful provider-status reporting.** Reuses the existing
  non-submitting capability probe and `tests/test_providers_live.py` (9
  tests, still deselected by default). This environment holds all three
  provider executables but no credentials, so the manifest honestly records
  `NOT_RUN_UNAUTHENTICATED` for Claude, Codex, and Cursor.
- **Two additive terminology/documentation corrections.**
  `docs/andrea-chapters-0-7-evaluation.md`'s stale "Unit 12 Andrea soak"
  phrasing is preserved unedited with a dated correction note naming
  "Andrea live evaluation" as current terminology.
  `docs/sows/sovereign-agent-v1-educational-control-plane.md` carries a
  dated correction note identifying its `done_when` clause and sequencing
  amendment 6 as superseded by
  `docs/rulings/2026-08-31-unit12-scope.md`'s Holding 1 replacement text
  ("local, learner-controlled Sovereign Store release evaluation ->
  redacted Unit 12 proof pack accepted"); both original passages remain
  intact.
- **Zero `src/sovereign_agent/` changes.** Budget unchanged at
  `27/40 modules, 6208/6250 nonblank lines, 7/30 root exports`. Every
  deliverable lives in `scripts/`, `docs/`, and `docs/evidence/unit12/`.

### Store expansion, Chapters 8-12, pilot-start mechanism (Unit 11)

Expands the Store's single-SKU walking skeleton into a genuine multi-SKU
catalog, proves the existing `inventory.changed -> wake gate -> Pulse ->
replenishment` pipeline generalizes with **zero new signal kinds, effect
kinds, or core organizational primitives**, lands five new chapters
teaching that expansion, and builds -- but never invokes against the real
named pilot organization -- an atomic, idempotent pilot-start mechanism.
This document's own status stays `PROPOSED`; the real pilot-start act and
its governance receipt are a later, separately-authorized step outside this
unit's implementation-acceptance scope.

- **A genuine multi-SKU catalog, additive.** `seed()` is untouched (still
  seeds exactly `SKU-TEA`; every pre-Unit-11 chapter and test depends on
  it). A new `seed_catalog` seeds at least two independently-tracked SKUs
  (`SKU-TEA` and `SKU-COFFEE` by default), each with its own product row,
  inventory row, stock level, and reorder point. `record_sale`,
  `store_wake_gate`, and `apply_restock` needed no code change -- they were
  already SKU-parametric.
- **The multi-SKU isolation matrix, a binding acceptance requirement.**
  `tests/test_store_multi_sku.py` proves all six named surfaces (sales,
  signal, wake-decision, Pulse-origin, assignment/replenishment isolation,
  and replay/restart/concurrency) with real tests, including a REAL
  two-connection race for two different SKUs' canonical creation,
  extending `tests/test_pulse.py`'s own single-SKU concurrency precedent
  rather than forking it.
- **Five new chapters** (`ch08_the_store_becomes_a_catalog` through
  `ch12_the_pilot_begins_with_a_receipt`), each with a `solution.py` that
  imports and runs real production code and a `README.md` with real,
  executed command output. Chapter 7's closing gesture now forward-links
  to Chapter 8; Chapters 8-11 each carry their own forward link; Chapter
  12, now the last chapter, carries none.
- **The pilot-start mechanism**, `reference_organizations.store.pilot.
  start_pilot`, backed by a new migration (16: `pilots`, `active_pilot`) in
  `src/sovereign_agent/database.py`. One atomic transaction writes a
  structured `pilots` row and an append-only `pilot.started` event, or
  neither. Idempotent replay and fail-closed refusal are both plain
  `INSERT`s racing a `UNIQUE`/`PRIMARY KEY` constraint at the SQLite
  boundary, matching `create_pulse_work`'s own `pulse_wake_decisions`
  precedent -- never a preflight `SELECT`. Proven in `tests/test_pilot.py`
  with real two-connection concurrency for both the same-identity replay
  case and the different-identity refusal case, plus a dedicated
  fabrication-detection test. **Never invoked against the real named pilot
  organization by this unit** -- Chapter 12's own exercise uses a
  disposable, exercise-scoped identity (`book-ch12-exercise-pilot`),
  mechanically enforced by a new `verify_curriculum.py` guard
  (`check_pilot_disposable_identity`) that refuses if the chapter's own
  exercise ever writes a `pilots` row without the reserved prefix.
- **`REQUIRED_CHAPTERS` extended to 13**, following the exact pattern Unit
  10 already established growing from 4 to 8. Every existing mechanical
  guarantee (chapter-scoped Pulse guard, instructor-note structure,
  chapter-sequence coherence, frontmatter absence, import-not-copy,
  execute-not-merely-import) applies unchanged to all 13 chapters.

Every new mechanical guarantee and test suite was mutation-checked before
this unit was reported complete: the new disposable-identity guard (a
non-reserved pilot id); the multi-SKU isolation matrix (a dropped
`subject == sku` filter in `store_wake_gate`, causing cross-SKU
contamination); the pilot-start idempotency discipline (`INSERT OR
REPLACE` in place of the CAS-driven plain `INSERT`); and a fabricated
`pilot.started` event bypassing the mechanism entirely -- each reproduced,
confirmed landed via diff, confirmed caught, restored byte-identical,
reconfirmed green. See
[docs/v1-unit11-store-expansion-pilot-start.md](docs/v1-unit11-store-expansion-pilot-start.md)
for the full contract and proof matrix.

**Not claimed:** the real pilot-start act, a governance receipt, this
document's `ACCEPTED` status or Unit 11's closure, credentialed provider
evidence (9 tests remain deselected and unrun), the Andrea live
evaluation, pilot completion or proof-pack acceptance, release, or any
Unit 12 work. Budget: `src/sovereign_agent/` grew by 69 nonblank lines
(migration 16 only) to 6208/6250 -- 42 lines of headroom remain; no
amendment requested or needed. Runtime dependency surface unchanged
(`pydantic` only).

### Curriculum completion, Chapters 0-7 (Unit 10)

Completes the promised curriculum range: four new chapters, each teaching
one already-ACCEPTED production concept from Units 7-9, instructor-note
machinery covering the whole completed range, a chapter-scoped (not
removed) Pulse-claim guard, and a genuine post-Unit-9 Andrea evaluation
task. **Zero new production behavior** -- every chapter exercise imports and
runs existing, already-ACCEPTED code; nothing was added to
`src/sovereign_agent/` or `src/reference_organizations/`.

- **Four new chapters**, each with a `solution.py` that imports and runs
  real production code (no teaching fork) and a `README.md` with real,
  executed command output:
  - `ch04_work_stays_inside_its_boundary` -- `safe_join`,
    `snapshot_boundary`/`diff_boundary`, `reclaim_workspace` and
    `workspace_policy` branching (Unit 7).
  - `ch05_authority_needs_a_fence` -- `acquire_actor_lease`,
    `acquire_execution_attempt`, and the stale-worker refusal path through
    the real `run_assignment` path with two genuinely separate
    `Organization` instances (Unit 8).
  - `ch06_the_organization_recovers` -- a REAL child process, REAL
    `SIGKILL` (the same fixture and polling discipline
    `tests/test_supervisor.py`'s own proof matrix uses), then
    `supervisor.tick` recovery -- never a guessed success (Unit 8).
  - `ch07_the_organization_wakes_itself` -- `run_pulse_once` end to end, no
    manual `create_sow`/`ready_sow`/`assign` call anywhere in the
    exercise, with the resulting `pulse.work_created` event and
    `pulse_origins`/`pulse_wake_decisions` rows read back from the ledger
    (Unit 9). The only chapter permitted to claim the organization woke
    itself, and only because its own run earns that claim.
- **Instructor-note machinery**, wholly new: `book/INSTRUCTOR.md` indexes
  every chapter's own `INSTRUCTOR.md` (all eight, including retroactively
  for Chapters 0-3), each carrying seven required sections -- teaching
  intent, prerequisite knowledge, likely misconceptions, observation
  checkpoints, discussion prompts, facilitation timing, exercise debrief
  and assessment guidance.
- **The Pulse guard becomes chapter-scoped, not removed.**
  `scripts/verify_curriculum.py`'s prior guard applied identically to
  every chapter regardless of number. Chapters 0-6 keep the exact
  unconditional prohibition. Chapter 7 may claim Pulse fired ONLY when its
  own already-executed exercise leaves durable, structured evidence in
  that run's own database: a real `pulse.*` event AND a traceable
  `pulse_origins` -> `pulse_wake_decisions` chain naming a real source
  signal -- re-derived by the gate itself from a fresh `sqlite3`
  connection, never trusted from the exercise's own printed summary. A
  claim with no such chain fails identically whether Pulse was never
  invoked or its evidence was fabricated by a direct `append_event` call.
- **New mechanical checks**: `REQUIRED_CHAPTERS` extended to 8; every
  chapter's `INSTRUCTOR.md` structurally checked for its seven sections;
  chapter forward/backward links and `book/README.md`'s own index checked
  for one coherent sequence (the prior gate only checked individual link
  resolution); no `book/**/*.md` file may begin with a site frontmatter
  block. Additive-only editing of Chapters 0-3 is explicitly left as a
  review-discipline requirement, not a mechanical check -- no heuristic
  here would actually prove the property it claims to.
- **Andrea evaluation extended.** `docs/andrea-alpha-evaluation.md` is
  preserved exactly as the historical Units 0-6.5 record (title, Task 7,
  and scoring key untouched), plus one additive link to the new document.
  `docs/andrea-chapters-0-7-evaluation.md` is new, with its own complete,
  replacement Task 7 assessing whether Andrea can explain and
  *independently verify* genuine proactive Pulse behaviour --
  mechanically validated by the new
  `scripts/evaluate_andrea_chapters_0_7.py`. Does not authorize or perform
  the Unit 12 Andrea soak.

Every new mechanical guarantee mutation-checked before this unit was
reported complete (a fabricated Pulse event; a Pulse claim in an early
chapter; a missing `INSTRUCTOR.md` section; a wrong-pointing forward link;
injected frontmatter -- each reproduced, confirmed caught, confirmed
landed via diff, restored byte-identical, reconfirmed green) -- see
[docs/v1-unit10-curriculum-completion.md](docs/v1-unit10-curriculum-completion.md)
for the full contract and proof matrix.

**Not claimed:** Chapters 8-12, any Unit 11 Store expansion or 30-day
pilot, any Unit 12 release work or the Andrea soak itself, credentialed
provider evidence, a mechanical check for additive-only Chapters 0-3
editing, any new runtime dependency, or any change to
`src/sovereign_agent/`'s own budget (unchanged: 27/40 modules, 6139/6250
lines, 7/30 exports).

### Pulse and proactive governed work (Unit 9)

Closes the gap between the manually dispatched Unit 5 Store pipeline and
sequencing amendment 5's proactive milestone: "sale → inventory signal →
deterministic wake gate → pulse → replenishment work created without a
human prompt." Pulse is a **distinct mechanism from the supervisor**, per
[the governing ruling](docs/rulings/2026-08-29-unit9-pulse-is-separate-from-supervisor.md):
`supervisor.tick()` is unchanged, still never reads a Pulse signal or fires
a wake gate.

- **Signal stability.** A committed sale signal was previously replaced,
  not appended, when a later sale happened to leave inventory at the same
  level (`INSERT OR REPLACE`, keyed implicitly on a `dedupe_key` with no
  per-occurrence component) -- a source row Pulse origin could not safely
  reference durably. Now a plain, append-only `INSERT`, with a genuinely
  unique key per occurrence.
- **The canonical creation transaction, genuinely atomic.**
  `Organization.create_pulse_work` composes the wake-decision claim
  (`UNIQUE(source_signal_id)` at the SQLite boundary, not a preflight scan),
  the SOW's creation and transitions, the assignment, the genuine
  `pulse.work_created` event, and the origin row inside ONE `db.immediate()`
  transaction -- corrected from an original five-separate-commit shape
  (Sparring's finding F-U9-1 on PR #35, confirmed by independent Principal
  reproduction) that could durably strand a wake decision with no recovery
  path if an ordinary exception landed between any two commits. `create_sow`,
  `ready_sow`, and `assign` reuse connection-taking `_on` helpers shared with
  their own unchanged public, single-call form -- manual dispatch calls the
  exact same production methods it always did, never a copied or Pulse-only
  fork. In-transaction revalidation (re-asking the wake gate under the
  write lock, not merely before it) prevents stale work from a condition
  that resolved between the caller's read and the lock being acquired. A
  concurrent loser still returns the same SOW and assignment identifiers,
  never a second, competing pair, re-proven under the atomic design with a
  REAL two-connection `threading.Barrier` race.
- **The Pulse component and the Store's own wake gate.**
  `sovereign-agent pulse --once --root PATH` reads durable signals, asks a
  caller-supplied wake gate, and invokes the existing production
  `run_assignment()` path for qualifying work -- never bypassing Unit 8's
  actor-lease or execution-attempt fencing. The Store's own gate (a genuine
  sale-origin signal, still below reorder when re-checked live, mapped to
  exactly one active outcome) lives outside `sovereign_agent`'s own module
  budget, in `reference_organizations/store`.
- **Structured, durable origin.** Every SOW -- manual or Pulse-created, new
  or migrated -- carries an explicit `pulse_origins` row (`origin_kind`,
  `wake_decision_id`, `pulse_event_id`, `sow_id`, `assignment_id`). Absence
  of a row is never the definition of manual: `create_sow` inserts one for
  every SOW at creation time, and migration 15 backfills one for every
  pre-existing SOW.
- Migration 15: `pulse_wake_decisions`, `pulse_origins`, both append-only.

Tests grow from 281 to 332 (33 new in `tests/test_pulse.py` from the
initial implementation, 8 new migration tests in `tests/test_persistence.py`,
10 more in `tests/test_pulse.py` from the F-U9-1 correction below),
including a mutation-checked proof for every decisive property this unit
exists to protect (the fix reverted, the specific test confirmed red,
restored byte-identical, re-confirmed green) -- see
[docs/v1-unit9-pulse-proactive-work.md](docs/v1-unit9-pulse-proactive-work.md)
for the full contract and proof matrix.

**Review correction (PR #35, F-U9-1).** Sparring found, and the Principal
independently reproduced, that the canonical creation transaction was not
actually atomic: a fault between any two of its five original separate
commits durably stranded the wake decision, and `source_signal_id`'s own
`UNIQUE` constraint then made every retry impossible -- the signal was
orphaned permanently. Closed by composing all five writes into one
`db.immediate()` transaction (see above); the source-line budget was raised
from 6000 to 6250 to accommodate the honest cost of that composition
(`scripts/verify_source_budget.py`'s own comment records the ruling; module
and export ceilings are unchanged).

**Not claimed:** credentialed Claude/Codex/Cursor provider tests remain
deselected and unrun. No OS service, scheduling, cron, or webhooks. No
automatic retry policy for failed governed work.

### Supervisor, fencing, and hard-kill recovery (Unit 8)

A worker that no longer holds the current lease could still commit
completion, mutate canonical execution state, acknowledge mailbox work, or
reclaim the active workspace -- Unit 4's mailbox proved actor-level
idempotency, never process-level exclusivity, and named the gap rather than
build a supervisor to close it
([deferral ruling](docs/rulings/2026-08-26-deferral-unit4-fencing.md),
[one-process-per-actor ruling](docs/rulings/2026-08-26-one-process-per-actor.md)).
A hard-killed worker also left its assignment stuck `RUNNING` forever, since
"a process cannot record its own death" (Unit 5). This unit closes both.

- **Process identity and actor-hosting leases.** A fresh, random process
  identity (never a PID -- PIDs are reused by the operating system) and an
  exclusive, renewable lease per actor, both compare-and-set against SQLite
  with the same discipline `relay.claim()` already used. `organization.
  run_assignment` acquires (or renews) the actor's lease as the FIRST thing
  it does, before the workspace_policy check, before any symlink check,
  before the SOW or assignment state is touched -- the same validate-
  before-anything-touched slot Unit 7 established. A competing live process
  for the same actor is refused there, before workspace allocation, before
  the provider is ever invoked, proven with a REAL two-process test: two
  genuinely separate `Organization` instances, two different assignments
  for the same actor, the second process's provider invocation spied on
  with a counter and shown to fire zero times.
- **Execution-attempt fencing bound to the `RUNNING` transition, and bound
  to the actor lease.** A distinct fencing token per invocation, checked
  atomically inside the same SQLite transaction that commits
  `COMPLETED`/`BLOCKED`/`FAILED`, so a stale worker's subprocess -- fencing
  is not an OS sandbox, so it can still run to completion -- cannot make its
  result canonical. The execution attempt now records and re-verifies the
  actor lease's own fencing token at acquisition time, connecting the two
  CAS mechanisms rather than leaving them independent.
- **F-U4-1 closed.** `relay.claim()`'s same-owner short-circuit used to fire
  even when that owner's own lease had expired, so the CAS's expired-lease
  branch was unreachable by the owner. Now it only short-circuits when
  unexpired; an expired same-owner reclaim wins the CAS and mints a fresh
  token. `complete()`/`dead_letter()` verify that token atomically.
- **Hard-kill recovery, by the supervisor, never the dead process.** A new
  reconciliation loop (`sovereign-agent supervisor --root PATH [--once]`)
  detects a `RUNNING` assignment whose execution attempt expired with no
  valid current worker and recovers it: a durable `FAILED` receipt naming
  the expired attempt and `failure_category="worker_lost"` -- never a
  guessed success, however far the orphaned subprocess actually got --
  idempotent, and workspace reclaim applied only after the terminal write
  is durable. No new assignment or SOW state. Proven against a REAL child
  process and a real `SIGKILL`, never a preclassified refusal injection.
  Clean `SIGINT` handling in the long-running loop; no hidden
  daemonization. Distinct from `service` (future OS hosting, not
  implemented) and `pulse` (Unit 9's proactive wake, not implemented).
- Migration 13: `lease_tokens`, `actor_leases`, `execution_attempts`,
  `assignments.current_execution_attempt`, `messages.fencing_token`.

Tests grow from 230 to 274, including a mutation-checked proof for every
decisive property (the fix reverted, the specific test confirmed red,
restored byte-identical, re-confirmed green) -- see
[docs/v1-unit8-supervisor-fencing-recovery.md](docs/v1-unit8-supervisor-fencing-recovery.md)
for the full contract and proof matrix.

**Not claimed:** credentialed Claude/Codex/Cursor provider tests remain
deselected and unrun -- no live-provider evidence exists anywhere in this
unit. Fencing is a ledger guarantee, not a filesystem one: a worker that has
lost its lease can still write bytes to disk if its subprocess is still
running; only the ledger commit is refused.

### Cumulative conformance (Unit 6.5)

The simulated store now performs a **real** replenishment. Previously the demo
printed `ACCEPTED` while `SKU-TEA` sat at `on_hand=2` against a
`reorder_point=3`, with no purchase and no replenishment event: the governance
records were complete and the business claim was false.

- The store gains a validated `apply_restock` effect. Inventory increase,
  purchasing cash entry, signal resolution, and the `replenishment.committed`
  event commit in one SQLite transaction, and are idempotent per assignment.
  A provider may *propose* a bounded quantity; deterministic Python validates
  it and reads the unit cost from the product record, never from the provider.
- `verify_outcome` executes every declared acceptance check instead of only
  advancing a status field. Unknown, malformed, and erroring checks fail closed.
- Acceptance re-derives its own authority. It **re-executes** the declared
  checks against current state, requires successful evidence for every declared
  check bound to this outcome and execution, and refuses stale evidence. The
  caller-supplied `performer_id` argument is **removed**: performers are derived
  from assignments in the ledger, so separation cannot be satisfied by naming a
  convenient stranger.
- A small explicit check registry replaces the previous single evidence record
  whose name (`inventory_non_negative`) described inventory while its value was
  computed from cash. `cash_reconciles` now reconciles the purchase against the
  replenishment event rather than testing solvency.
- Events are append-only **at the database boundary, from any connection**:
  triggers refuse `UPDATE`, `DELETE`, and an `INSERT` whose id already exists.
  The first attempt closed the `INSERT OR REPLACE` bypass with
  `PRAGMA recursive_triggers`, which is per-connection — so a plain `sqlite3`
  shell, the tool Chapter 1 teaches, still silently overwrote events while the
  verifier reported "ACCEPTED and true". Migration 3 replaces that with a
  `BEFORE INSERT` guard needing no pragma, and a test that opens its own
  connection proves it. Evidence gains a foreign key, so a fabricated evidence
  id cannot be inserted at all.
- Named limits rather than silent ones: `docs/persistence-boundary.md` records
  that `outcomes` has no triggers, so an attacker with raw database write access
  can retarget `outcome.subject` and make all three checks pass coherently. The
  durable fix (binding subject into the evidence digest) is identified as the
  next step, not claimed as done.
- Migrations become forward-only and numbered. Migration 1 is unchanged;
  migration 2 adds the guards and evidence binding. Fresh-database and
  upgrade-from-v1 paths are both tested.
- Chapters 1 and 2 are written, Chapters 0 and 3 gain the required structure,
  and `scripts/verify_curriculum.py` detects missing sections, broken solution
  imports, and references to scripts that do not exist.
- New verification: `scripts/verify_store_outcome.py`,
  `scripts/verify_projections.py`, `scripts/evaluate_andrea_alpha.py`.

Tests grow from 59 to 98, including a falsification suite that proves acceptance
is refused for missing, failed, unrelated, unbound, stale, and fabricated
evidence, and a fault-injection suite that proves rollback after a partial write.

**Not claimed:** the credentialed provider smokes for Claude, Codex, and Cursor
have **not** been run. They remain a Unit 12 release gate. Installed is not
authenticated.

### Branch policy correction

`main` became the 1.x educational integration line when Units 0–6 merged. The
earlier holding that "`main` remains the 0.7 line" is superseded. Tag `v0.7.0`
remains immutable at `be2a41bbee202c52a40b2e87c00215827be302a0`; pin
`sovereign-agent<1` for the 0.x framework. No claim is made that 1.0 has met its
release gates. See
[docs/rulings/2026-08-25-main-is-the-1x-line.md](docs/rulings/2026-08-25-main-is-the-1x-line.md)
and [docs/persistence-boundary.md](docs/persistence-boundary.md).

### Providers (Unit 6)

Claude, Codex, and Cursor adapters implement `probe` / `build_invocation` /
`parse_event`. One provider-neutral envelope supplies actor identity,
authority, SOW, workspace/output boundaries, and the exact report schema.
Capability claims retain probe evidence and fail closed. Terminal events,
sessions, usage, malformed streams, reports, canonical receipts, and receipt
digests are validated by fake-executable integration tests. Credentialed live
assignments remain explicitly opt-in and outside default CI. Chapter 3 lands
with a runnable provider-rebinding exercise. Codex receives an authority-bound
writable sandbox, Claude receives `acceptEdits`, and Cursor receives `--force`
for the mandatory report; refusals and timeouts finalize durable failed
receipts; provider credentials use explicit environment allowlists.

### 1.x educational reset (authorization only)

Principal ruling 2026-08-25 authorizes Sovereign Agent 1.x as an executable
textbook. The v0.7 public API promise ends at the 0.x line. Tag `v0.7.0` is
not moved. Pin `sovereign-agent<1` for the old framework.

The 0.x non-goal “no governance decisions in this package” remains true for
v0.7 and is superseded for 1.x: the package may include the minimum
governance needed to teach and run one outcome. See
[docs/rulings/2026-08-25-educational-reset.md](docs/rulings/2026-08-25-educational-reset.md),
[docs/migration-v0.7-to-v1.md](docs/migration-v0.7-to-v1.md), and
[docs/non-goals.md](docs/non-goals.md).

No runtime or public-API code changes in this entry.

## [0.7.0] — 2026-08-23

Bounded production execution fleet on the v0.6 coordinator. Docker and
rootless Podman workers, authenticated SSH workers, fail-closed placement,
reservations, secret leases, network enforcement with evidence,
content-addressed artifacts, and reconciliation that forbids last-write-wins.
`DockerWorker` is no longer a stub. ZeoCore remains the capability contract
layer, not a scheduler. A git tag is not a public release until
`make verify-pypi`.

## [0.6.0] — 2026-08-23

Capability-native single-node default. `run_task` projects ZeoCore capabilities
and Sovereign runtime commands through a frozen per-execution catalog.
Approvals, durable concurrency leases, and invocation evidence survive restart.
`@register_tool` remains compatibility-only through 2027-02-23. Fleet work
stays in v0.7. A git tag is not a public release until `make verify-pypi`.

## [0.5.1] — 2026-08-23

Packaging and documentation truth for the v0.5 capability migration. Python
3.13 floor, `zeocore>=0.5,<0.6`, capability-first README, contract fixtures in
the wheel, and a ZeoCore min/newest CI job. Git tag `v0.5.0` is not moved and
is not announced as the PyPI line.

## [0.5.0] — 2026-08-23

Capability migration toward ZeoCore. Python 3.13 floor. Runtime evidence
types renamed to `RuntimeCapabilityManifest`. Reusable actions go through
ZeoCore; runtime commands stay in Sovereign. Legacy `register_tool` remains
through the compatibility window.

The 152-symbol v0.4 `__all__` surface is preserved; v0.5 adds 9 capability
symbols for 161 total.

## [0.4.0] — 2026-08-22

Durable local execution service on top of the v0.3 harness. HMAC-authenticated
Unix-socket API, serialized Zero Employee connector, relay v2 directory states,
seat supervision, durable approvals, webhook/Slack/email-draft channels,
allowlisted plugins, coordinator fencing, backup/restore, and copy-on-write
migration from v0.3 runtime roots. No Sandcastle. No multi-host workers.

The 152-symbol v0.3 `__all__` surface is preserved.

## [0.3.0] — 2026-08-22

The package, documentation, API manifest, wheel, and sdist declare v0.3.0.
Publishing remains a separate tag-triggered action; `make ready-to-ship` never
publishes or uses live credentials.

### Added

Landed on `main` on 2026-08-22 via
[PR #1](https://github.com/zeroemployeeorg/sovereign-agent/pull/1) and
[PR #2](https://github.com/zeroemployeeorg/sovereign-agent/pull/2). See
`docs/branch-consolidation-2026-08-22.md` for branch tips, merge commits, and a
correction to the `archive/pre-v0.3-runtime-stack-20260822` tag, which points at
a feature-branch tip rather than the pre-v0.3 state of `main`.

- Channel adapters: `ChannelAdapter` protocol, CLI adapter, inbound router. Only
  `CHANNEL_REGISTRY` is exported in `__all__`.
- Generic `Plugin` protocol and `Registry[T]`.
- Orchestrator dispatch routed through `WorkerBackend` via
  `make_worker_backend()`.
- Unit 3 worker lifecycle: provider-independent prepare/execute/close contracts,
  forward-only states, cancellation and bounded teardown, timeout reasons,
  fail-closed native isolation, allowlisted subprocess environments, and
  redacted diagnostics. See `docs/v0.3-unit3-worker-lifecycle.md`.
- Unit 4 native CLI providers: Codex CLI JSONL and Claude Code stream-json
  adapters, evidence-bearing version/help probes, capability-gated fresh and
  resumed sessions, capability-gated Claude session fork, strict normalized
  event parsing, observer containment, and execution through the Unit 3 backend
  seam without Sandcastle or `shell=True`. Default tests use committed fixtures
  and fake backends; zero-token live help/version probes are opt in and do not
  run in CI. See `docs/v0.3-unit4-cli-providers.md`.
- Unit 5 governed repository execution: configured `RepositoryId` resolution,
  fail-closed dirty policies, isolated execution branches and worktrees,
  durable fenced repository leases, deterministic redacted Git evidence, and
  opt-in non-force delivery with exact remote-SHA verification. See
  `docs/v0.3-unit5-repository.md`.
- Unit 6 persistent seat registry and durable local relay: immutable
  registration identity (including sovereign-session and provider-session
  bindings), atomic heartbeats, liveness inspection, validated local
  addressing, conversation/reply envelopes, artifact references, expiry,
  idempotent enqueue, ordered fenced claims, ack/nack, bounded backoff,
  lease recovery, dead letters, acknowledgement records and explicit
  corruption quarantine. See `docs/v0.3-unit6-registry-relay.md`.
- Unit 7 governed execution handshake: typed `GovernedExecutionRequest` /
  `ExecutionReceipt` fields, admission that refuses before invocation,
  repository execution under lock, provider/worker composition, and CLI
  `seat`/`execute`/`execution`/`receipt`/`relay` commands (with `governed`
  aliases). See `docs/v0.3-unit7-governed-execution.md`.
- `LivenessMonitor` — stalled-session detection and heartbeat. Importable but not
  in `__all__`.
- Move to `src/` layout.

`sovereign_agent.__all__` now has 152 public symbols, up from the 67 that shipped
in 0.2.0. Every v0.2 symbol remains and the 85 additions enter the v0.3
compatibility contract.

### Release readiness

- Added machine-readable v0.2 and v0.3 API manifests and a gate comparing them
  with `__all__`.
- Added a v0.2 migration guide, threat model, explicit teaching-surface decision,
  release-note fragments, and a no-deprecations declaration.
- `make ready-to-ship` now runs deterministic CI, strict docs, distribution
  content checks, and a clean core-only wheel install. The smoke test validates
  packaged schemas and rejects import-time filesystem, network, and process side
  effects.

### Documentation and truth repair

- Repository identity updated to `zeroemployeeorg` across `README.md`,
  `pyproject.toml` URLs, `mkdocs.yml`, and the docs tree. Old
  `sovereignagents/...` links still resolve by GitHub redirect but are no longer
  canonical.
- Corrected test-count claims: the suite collects **500** tests (497 pass, 3
  opt-in/platform skips), including skipped-by-default live provider probes.
  Previous docs claimed 267, 220, and 120 in different places.
- Corrected public-API claims: **152** symbols in `__all__`, of which 67 are the
  stable 0.2.0 surface. `docs/API.md` now lists both sets separately, and names
  the v0.3 symbols that are importable but not in `__all__`.
- Removed links to files that do not exist: `docs/class-slides.md`,
  `CONTRIBUTING.md`, and a root `SOW.md`.
- Replaced the "authoritative SOW in the repo root" framing in
  `docs/architecture.md` with the work-repo/corpus boundary: this repository is
  `work_repo` and holds code; scoping and reporting live in a separate
  `sow_repo`. No corpus path is hard-coded here, by design.
- Docker is labelled unavailable everywhere it appears. `DockerWorker` docstrings
  now say "unimplemented stub" rather than "v0.4 stub", and the raised
  `NotImplementedError` states that no container code path exists.
- Corrected the install instructions: dev tooling is a PEP 735 dependency
  *group*, so `pip install "sovereign-agent[dev]"` was never a real extra.
- Added `docs/v0.3-non-goals.md` — normative scope boundaries for v0.3,
  including an explicit prohibition on introducing Sandcastle in any form.
- Added `docs/branch-consolidation-2026-08-22.md`.

### Packaging

- **`docker` removed from the `all` meta-extra.** `pip install
  "sovereign-agent[all]"` no longer pulls the Docker SDK, because there is no
  Docker code path for it to support. The `docker` extra itself is retained so
  the dependency stays declared in one place. Install it explicitly if you need
  the SDK for your own reasons: `pip install "sovereign-agent[docker]"`.

### Not implemented, despite having a name

Recorded here so the gap is documented rather than inferred:

- `DockerWorker` — stub; `run_session()` raises `NotImplementedError`.
- Evidently and OpenTelemetry observability backends — import-gated stubs.
- Voice pipeline — protocol only.
- `MemoryRetrieval` / `MemoryConsolidation` — class shells, no behaviour.
- `lessons/` — a template and a rationale README; no lesson has been written.

## [0.2.0] — 2026-04-24

Released to PyPI as the only published release. Tag `v0.2.0` →
`9d934cf53ff223175d01ebf07483fd608fae66a0`.

Contents are as described under `[0.2.0-alpha]` below; the alpha entry was the
working record and was never rewritten at tag time. Two claims in that entry were
accurate when written and are no longer accurate for the current tree — the test
count (220 then, 370 now) and the public-symbol count (67 then, 76 now).

## [0.2.0-alpha] — 2026-04-24

Historical record, kept as written. Counts and claims in this entry describe the
tree at 0.2.0 and are not a description of `main` today; see `[Unreleased]` above.

v0.2 focuses on five capabilities students asked about in the first-cohort
class: parallel tool calls, process isolation without Docker, session
resume, pluggable rule verifiers, and human-in-the-loop approval. All
five ship as additive features — every v0.1.0 scenario still works
unchanged.

### Module 1 — Parallelism

- `_RegisteredTool.parallel_safe: bool = True` declares whether a tool
  may run concurrently with other tools in the same ReAct turn.
- `DefaultExecutor(parallelism_policy=...)` accepts `"respect_tool_flags"`
  (default), `"never"`, or `"always"`.
- Execution groups contiguous `parallel_safe=True` calls into an
  `asyncio.gather`; unsafe calls (writes, handoffs, `complete_task`)
  break the batch and run alone.
- Output ordering is preserved regardless of completion order, so the
  LLM sees tool results in the order it requested them.
- `_RegisteredTool.verify_args` is a new optional hook that runs before
  the tool body and can reject bad arguments with a structured reason.

### Module 2 — Process isolation (no Docker)

- New `WorkerBackend` protocol (`sovereign_agent.orchestrator.worker`)
  decouples "how a step runs" from "where a step runs". `BareWorker`
  (in-process), `SubprocessWorker` (separate Python process), and any
  future backend share the same shape.
- `sovereign_agent.orchestrator.worker_entrypoint` — a small standalone
  module invoked as `python -m ...` — is the common target. It
  advances exactly one step and prints a JSON summary as its last line
  of stdout.
- **`LandlockPolicy`** (Linux ≥ 5.13) wraps the command in a shim that
  calls `landlock_create_ruleset` / `add_rule` / `restrict_self` via
  `ctypes` before `exec`ing the real payload. No pypi dependency on a
  Landlock library, no daemon, no container runtime. Kernel-enforced
  filesystem isolation.
- **`SandboxExecPolicy`** (macOS) generates a `.sb` profile and wraps
  the command in `sandbox-exec -f`. Uses Apple's own sandbox framework
  — the same one confining App Store apps.
- `detect_best_policy()` picks the strongest available primitive for
  the host and falls back to `NoOpPolicy` (with a loud warning) on
  unsupported platforms.
- Fail-closed by design: the Landlock shim exits non-zero if Landlock
  isn't available rather than running the child unprotected.

### Module 3 — Session resume

- `SessionState.resumed_from: str | None` records a pointer from child
  to parent session. Parent is untouched (forward-only rule).
- `resume_session(parent_id, task, ...)` creates a linked child
  session, refusing to resume from non-terminal parents unless
  `allow_unfinished_parent=True`.
- `Session.parent_session()` returns a handle for the parent or `None`
  if it has been archived/deleted.
- `find_ancestor_chain(session)` walks multi-level resume chains
  oldest-first and is defensive against cycles and missing ancestors.
- Parent context summary (trace tail, tickets, final result) is
  auto-inlined at the top of the child's `SESSION.md` so the planner
  sees it on first read.
- New CLI command: `sovereign-agent sessions resume <parent_id>`.

### Module 4 — Verifier protocol

- New `Verifier` protocol (`sovereign_agent.halves.verifiers`) with
  a single async `evaluate(data) -> VerifierResult` method.
- Three concrete implementations: `LambdaVerifier` (wraps any callable),
  `ClassifierVerifier` (sklearn `predict_proba` or transformers
  pipeline `__call__`), `LLMJudgeVerifier` (uses an LLM with defensive
  JSON parsing).
- `Rule.condition` and `Rule.escalate_if` now accept either a callable
  (legacy) or a `Verifier` (new). Backward-compatible.
- `VerifierResult` carries a `reason` and optional numeric `score` that
  surface in `HalfResult.output` — the structured audit trail for
  probabilistic rule decisions.

### Module 5 — Human-in-the-loop

- `ToolResult.requires_human_approval: bool = False` makes any tool
  able to pause the session.
- Executor writes `ipc/awaiting_approval/<request_id>.json` and exits
  cleanly when it sees the flag. No coroutine holds state across the
  wait — the session can idle for hours or days.
- `ApprovalRequest` includes a SHA-256 of the tool arguments so the
  approver is granting a specific invocation, not a general action.
- `ApprovalResponse.override_output` lets approvers modify the tool's
  proposed output instead of just accepting or denying it.
- Double audit trail: ephemeral IPC files plus permanent
  `logs/approvals/`.
- New CLI commands: `sovereign-agent approvals {list,grant,deny}`.
- `resume_from_approval(executor, subgoal, session, request_id)` runs a
  fresh ReAct turn whose opening user message includes the decision,
  letting the LLM adapt on denial or continue on grant.

### Tests

100 new unit tests across the five modules — 9 parallelism, 14
approval, 23 verifier, 23 resume, 11 worker, 20 isolation — bringing
the total to **220 tests**, all passing.

### Examples

One end-to-end example per module, each self-contained (no real LLM
credentials required by default) and wired into the Makefile:

- `examples/parallel_research/` — five arXiv lookups; 0.33s parallel
  vs 1.54s sequential (~4.7× speedup). `make example-parallel-research`.
- `examples/isolated_worker/` — subprocess worker under
  `detect_best_policy()`; probe shows session-dir writes succeed and
  `/etc/shadow` / `/etc/hosts` reads are denied on a working sandbox.
  `make example-isolated-worker`.
- `examples/session_resume_chain/` — three-generation parent →
  child → grandchild chain with auto-prepended parent context in
  SESSION.md and forward-only rule verification.
  `make example-session-resume-chain`.
- `examples/classifier_rule/` — StructuredHalf rule driven by a
  `ClassifierVerifier`; six manager-reply strings classified correctly;
  verifier score and reason surface in the audit trail.
  `make example-classifier-rule`.
- `examples/hitl_deposit/` — full grant-and-deny flow through the real
  CLI (`sovereign-agent approvals grant|deny`) with
  `resume_from_approval()` on the other side. `make example-hitl-deposit`.

### Sessions and artifacts

- Demos and `--real` examples now write session artifacts to the platform's
  user-data directory (`~/.local/share/sovereign-agent/...` on Linux,
  `~/Library/Application Support/sovereign-agent/...` on macOS,
  `%LOCALAPPDATA%\sovereign-agent\...` on Windows) instead of either the repo
  root or a tempdir. Override with `SOVEREIGN_AGENT_DATA_DIR=<path>`.
- New `sovereign_agent._internal.paths.example_sessions_dir(name, persist=)`
  context manager encapsulates the policy: `persist=True` yields a stable
  user-data path, `persist=False` yields a tempdir. Four built-in examples
  (`research_assistant`, `code_reviewer`, `pub_booking`, `parallel_research`)
  use it to route `--real` runs to persistent storage and offline runs to
  tempdirs.
- Offline examples continue to use tempdirs (no change).
- Production (`sovereign-agent run`, `sovereign-agent serve`) continues to
  honour `Config.sessions_dir` / `SOVEREIGN_AGENT_SESSIONS_DIR` (no change).
- README adds a "Where things live" section documenting this.

### Documentation

- `chapters/README.md` now explicitly frames the Raschka pattern (chapters
  in-tree, `solution.py` re-exports from `sovereign_agent/`, drift-checked by
  CI) versus the Howard pattern (separate course repo using the published
  library). Clarifies why chapters live here while homework lives elsewhere.
- `docs/API.md` clarifies the public-API contract: 67 symbols in
  `sovereign_agent.__all__`, semver applied to that surface, everything under
  `sovereign_agent._internal/` may change between patch releases.

### Packaging

- First pypi release of `sovereign-agent` (pypi package name matches repo name;
  import path `sovereign_agent`). Trusted publisher via GitHub Actions OIDC;
  no API tokens in the repo.
- `pip install sovereign-agent[all]` installs evidently, otel, voice, and
  docker extras. `[rasa]` is intentionally NOT in `all` because `rasa-pro`'s
  pin set conflicts with several other extras. (Superseded: `docker` was later
  removed from `all` too — see `[Unreleased]`.)
- Python 3.12+ required.

### Breaking changes

None. Every public API from v0.1.0 still works with the same signature.

---

## [0.1.0] — unreleased (alpha)

Initial scaffold. This is the first working implementation of the architecture specified in `docs/architecture.md`.

### Implemented

- **Session substrate** (`sovereign_agent.session`): atomic `session.json` writes, traversal-safe `path()`, trace-event append, subdirectory layout.
- **Session queue** (`sovereign_agent.session.queue`): per-session serialization, global concurrency cap, retry with exponential backoff, idle preemption via `_close` sentinel, graceful shutdown (detach, do not kill).
- **Tickets** (`sovereign_agent.tickets`): explicit state machine (pending/running/success/skipped/error), sha256 manifest verification ("no manifest, no success"), LLM-readable summaries.
- **IPC** (`sovereign_agent.ipc`): filesystem IPC with atomic rename, `IpcWatcher` polling loop, per-session error isolation, quarantine of malformed files.
- **Errors** (`sovereign_agent.errors`): structured taxonomy (SYS / VAL / IO / EXT / TOOL) with machine-readable codes.
- **Discovery** (`sovereign_agent.discovery`): Discoverable protocol with schema validation.
- **Scheduler** (`sovereign_agent.scheduler`): drift-corrected recurring tasks, interval and cron, skip-ahead on missed intervals.
- **Tools** (`sovereign_agent.tools`): `@register_tool` decorator with auto-discovery from signature, builtin read/write/list/search/write-memory/handoff/complete tools.
- **Planner and Executor** (`sovereign_agent.planner`, `sovereign_agent.executor`): two-stage ReAct with real OpenAI-compatible client, `FakeLLMClient` for tests.
- **Loop half** (`sovereign_agent.halves.loop`): planner + executor composition.
- **Handoff** (`sovereign_agent.handoff`): file-based protocol with fail-closed on duplicate files and archive to audit log.
- **Orchestrator** (`sovereign_agent.orchestrator`): state dispatch, resume-from-disk, SIGTERM handling.
- **CLI** (`sovereign_agent.cli`): `run`, `serve`, `doctor`, `report`, `sessions`, `version`.
- **Config** (`sovereign_agent.config`): env loading, TOML loading, validate().

### Skeletons (API stubbed, behavior TODO)

- **Memory subsystem** (`sovereign_agent.memory`): MemoryStore/Retrieval/Consolidation class shells.
- **Structured half** (`sovereign_agent.halves.structured`): minimal rule-list evaluator.
- **Observability** (`sovereign_agent.observability`): JSONL trace reader and session-report generator; Evidently and OTel backends are import-gated stubs.
- **Voice** (`sovereign_agent.voice`): protocol definition only; Speechmatics/ElevenLabs implementation is a stub.
- **Mount allowlist** (`sovereign_agent.orchestrator.mounts`): default patterns and validate() scaffold.
- **Credential gateway** (`sovereign_agent.orchestrator.credentials`): basic env loading; per-tool scoping TODO.

### Not yet started

- Full mkdocs site beyond the architecture copy (quickstart, deployment, API reference).
- Docker worker spawning in `orchestrator/main.py` (the containerized execution path mentioned in `bare_mode` config).
- Per-tool credential scoping in `orchestrator/credentials.py` (the gateway scaffolds the env-loading; the per-tool allowlist is the TODO).

### Verified working in this release

- `ruff check sovereign_agent/ tests/ chapters/ examples/` — clean.
- `pytest` — 148 tests pass in ~7 s.
- `python tools/verify_chapter_drift.py` — all 5 chapters match production.
- All 5 chapter demos (`python -m chapters.<N>_*.demo`) run end-to-end.
- All 3 example scenarios (`research_assistant`, `code_reviewer`, `pub_booking` with both default and `--oversize`) run end-to-end.
- `sovereign-agent doctor --skip-llm` passes with a fake API key.
