# Chapter 1 — The session directory is the unit of everything

## What you'll build

A `Session` class, a `SessionState` dataclass, and three module-level helpers (`create_session`, `load_session`, `list_sessions`). By the end you'll be able to create a session directory on disk, update its state atomically, append trace events, and reload it later — everything the rest of the framework will build on.

## Why this comes first

Every other decision in sovereign-agent rests on this one. Before we can talk about queueing work, running tools, or handing off between halves, we need an agreed-upon place to put *one task's worth of state*. That place is a directory on disk, one per task, containing everything about that task and nothing about any other.

The alternative — and the thing almost every "v1" agent framework does first — is to use a database. SQLite, Postgres, Redis, doesn't matter. The database approach has five specific failure modes that ruin it in production, and by the time you've hit any of them you've already done the work to switch:

1. **Databases are opaque to humans.** When the agent does something weird at 2 AM, you want to `ls` its directory and read its files, not write a SQL query.
2. **Transactions across multiple writers are hard.** With files + atomic rename (POSIX `rename(2)`), each file is its own atomic unit.
3. **Database lifetime couples to agent lifetime.** Down database = down agent. `tar sessions/` is free.
4. **Schema lives in the database, not in your code.** Lose the code, lose the ability to read the data.
5. **Databases don't scale to multiple agent halves.** When a second half wants to share state, the database approach forces a schema negotiation. The filesystem approach lets both halves bind-mount the same directory and read each other's files.

The session directory is the workbench. Tools are the tool cabinet. Both halves walk up to the same cabinet and do their work on the same workbench.

## The layout (memorize this)

```
sessions/sess_<12hex>/
├── SESSION.md            Per-session system prompt + task description.
├── session.json          Machine-readable state. Atomic writes only.
├── memory/
│   ├── working.md
│   ├── semantic/
│   ├── episodic/
│   ├── procedural/
│   └── index.json
├── ipc/
│   ├── input/
│   ├── output/
│   ├── handoff_to_*.json (at most one)
│   └── session_complete.json
├── logs/
│   ├── trace.jsonl       Newline-delimited JSON event stream.
│   ├── handoffs/         Audit log of consumed handoffs.
│   └── tickets/
│       └── tk_<id>/
│           ├── state.json
│           ├── manifest.json
│           └── summary.md
├── extras/
└── workspace/            Tools' working directory.
```

Two things matter most at this stage:

- **Atomic writes to `session.json`.** Temp file, write, fsync, rename. POSIX guarantees the rename is atomic. Readers see either the old version or the new version, never a half-written one.
- **Forward-only state transitions.** `planning → executing → completed` is allowed; `completed → planning` is not. This is enforced by a small transition map in `sovereign_agent/session/state.py`.

## What you're implementing

Read `starter.py`. The interfaces you must fill in:

```python
class Session:
    def path(self, relative: str | Path) -> Path: ...
    def update_state(self, **changes) -> None: ...
    def append_trace_event(self, event: dict) -> None: ...
    def mark_complete(self, result: dict) -> None: ...

def create_session(scenario: str, task: str = "", ...) -> Session: ...
def load_session(session_id: str, ...) -> Session: ...
def list_sessions(state_filter=None, ...) -> list[Session]: ...
```

The key correctness requirements:

1. `Session.path("../../etc/passwd")` **must raise `SessionEscapeError`**. So must any symlink that resolves outside the session directory.
2. `update_state(state="planning")` after the session is already `executing` **must raise `InvalidStateTransition`**.
3. `session.json` is written atomically (temp-file-then-rename) on every update.
4. `append_trace_event` uses `O_APPEND` so multiple concurrent writers don't interleave.

## Run the tests

```bash
pytest chapters/chapter_01_session/tests.py -v
```

All eight tests must pass.

## Run the demo

```bash
python -m chapters.chapter_01_session.demo
```

You should see a session directory appear under `./sessions/`, with all the expected subdirectories, a valid `session.json`, and a couple of trace events. The demo script prints the directory tree at the end.

## What's next

Chapter 2 will introduce the `SessionQueue` — the central coordinator that decides which session's work runs when, serializes per-session work so memory writes don't race, and enforces a global concurrency cap so 100 sessions waking up at once doesn't spawn 100 workers.
