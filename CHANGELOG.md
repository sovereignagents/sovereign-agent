# Changelog

All notable changes to sovereign-agent.

## [0.2.0] — unreleased

Placeholder for the stable v0.2.0 release. Promoted from `[0.2.0-alpha]`
once the test.pypi rehearsal is green and at least one external install
has been verified.

## [0.2.0-alpha] — 2026-04-??   <!-- fill in date at tag time -->

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
  pin set conflicts with several other extras.
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
