# Chapter 7 — The organization wakes itself

Every chapter so far began the same way: a human *dispatched* the work — wrote the
statement of work, made the assignment. Lucy wants something narrower but
important: when a sale drops the freezer below its line, she wants the reorder
*work itself* to be created from that signal, without her writing the dispatch by
hand each time.

Be precise about the claim, because most systems overstate exactly this. This
chapter separates three things and is careful not to confuse them: (1) a
**signal-driven decision** — a durable low-stock fact turned into a wake
decision; (2) **one Pulse tick** — a single call that derives governed work from
that decision; and (3) a **durable watcher** that evaluates a condition when a
host invokes it at a due time. This chapter proves all three state machines, but
it does not install a daemon: *you* invoke both Pulse and `run_due()`. "The
organization wakes itself" means it creates its own work from its own signals,
not that the Python process runs forever on its own. And when
it does create work, it leaves a durable, traceable record you can walk backward
from the finished work all the way to the sale that woke it. No record, no claim.

## Learning objective

Watch the organization create governed work **without a human prompt**, and
learn what makes that claim honest rather than theater: a durable
`pulse.work_created` event and a structured origin row, both produced by the
real mechanism, both checkable after the fact — never a status string, never
an inference from "nobody typed a command."

Chapter 0 ended by telling you the truth: you started everything. The package
now has a heartbeat and a durable watcher, but neither rewrites that history and
neither is smuggled into the Pulse claim. A manually invoked Pulse tick derives
work from a durable signal without a human authoring that work; a separately
invoked watcher evaluates its own due condition; a heartbeat proves only that a
runtime reached the ledger.

## Vocabulary this chapter adds

| Term | What it is |
| --- | --- |
| **Signal** | A durable, append-only "something needs attention" fact — e.g. inventory falling below the reorder point after a sale. |
| **Wake gate** | A deterministic callback that decides whether a signal fires, and what governed work it should create if it does. The Store's own gate lives outside `sovereign_agent`'s budget: it is domain logic about SKUs and reorder points, not a general Pulse mechanism. |
| **Wake decision** | The durable, `UNIQUE(source_signal_id)` claim that one signal fired — the SQLite-boundary enforcement of "exactly one canonical decision per signal," not a preflight check a race can slip past. |
| **Pulse origin** | The structured, queryable answer to "manual or Pulse, and from what?" — every SOW, manual or Pulse-created, has exactly one row. Absence of a row is never the definition of manual. |

## Separate trigger, decision, and execution

"Autonomous" is too vague to test. Pulse splits it into explicit stages:

```mermaid
flowchart LR
    E[Domain event\nsale committed] --> S[Signal\ndurable fact]
    S --> Q[Pulse query\nunevaluated signals]
    Q --> G[Wake gate\npure domain decision]
    G -->|fire| D[Wake decision\nUNIQUE signal id]
    D --> W[SOW + origin\ncreated atomically]
    W --> A[Assignment]
    A --> X[Provider execution]
    G -->|do not fire| N[Nothing recorded\nre-evaluated next pass]
```

**Figure:** A durable signal is evaluated by a pure gate; only a firing decision atomically creates one governed work chain, while a non-fire creates no false work record.

The signal is not a task. It records that the world crossed a meaningful
boundary. The gate is not a worker. It decides whether that signal still merits
work and specifies the governed work shape. Pulse is not a scheduler. One call
scans eligible signals and invokes the gate; only a firing decision is durable.
The provider is not the decider. It executes only after ordinary governance
creates an assignment.

This decomposition gives each race one database invariant. Two Pulse processes
may evaluate the same signal concurrently, but `UNIQUE(source_signal_id)` allows
only one canonical wake decision. The winner creates the SOW and its
`pulse_origins` row in the same transaction. The loser observes the existing
decision instead of manufacturing duplicate work. "Exactly once" here means
one canonical decision in the ledger—not that a function is physically invoked
only once.

### Four clocks that should not share one name

| Mechanism | What advances it? | What it proves |
| --- | --- | --- |
| Signal | Domain transaction | A relevant fact occurred. |
| Pulse tick | Caller invocation | Eligible signals were evaluated once. |
| Supervisor tick | Loop or caller | Expired claims/attempts were reconciled. |
| Heartbeat | Explicit `record_heartbeat` call | The runtime was alive at that moment; never that work happened, never a Pulse trigger. |

Keeping these clocks distinct prevents an operational command loop from being
mistaken for a liveness protocol, or a liveness protocol from being mistaken for
business decision-making.

## Build the tick yourself, then double-order the cones

Before running the real mechanism, build a pulse tick small enough to watch
it make the one mistake every naive version makes.

The scene: a sale dropped vanilla to 2 against a reorder point of 3, and the
sale committed a durable **signal** — a fact, not a task:

```python
import sqlite3

db = sqlite3.connect(":memory:")
db.executescript("""
    CREATE TABLE inventory (sku TEXT PRIMARY KEY, on_hand INT NOT NULL, reorder INT NOT NULL);
    CREATE TABLE signals (id TEXT PRIMARY KEY, sku TEXT, kind TEXT);
    CREATE TABLE wake_decisions (id INTEGER PRIMARY KEY, source_signal_id TEXT UNIQUE,
                                 sow_id TEXT);
    CREATE TABLE sows (id TEXT PRIMARY KEY, title TEXT, state TEXT);
""")
db.execute("INSERT INTO inventory VALUES ('SKU-VANILLA', 2, 3)")
db.execute("INSERT INTO signals VALUES ('sig-1', 'SKU-VANILLA', 'low_stock')")
db.commit()
```

Note the `UNIQUE` on `wake_decisions.source_signal_id`. It looks like a
detail. It is the entire chapter.

### The gate decides WHAT — and nothing else

**Listing:** Decide whether one durable signal still deserves work

```python
def wake_gate(db, signal_sku):
    on_hand, reorder = db.execute(
        "SELECT on_hand, reorder FROM inventory WHERE sku = ?", (signal_sku,)
    ).fetchone()
    if on_hand < reorder:
        return f"Replenish {signal_sku} to {reorder}"
    return None


print(wake_gate(db, "SKU-VANILLA"))
```

```text
Replenish SKU-VANILLA to 3
```

The gate is a pure read: world in, decision out, no writes. That split is
deliberate and mirrored in production — the gate decides *what* should
happen (domain logic about SKUs and reorder points, owned by the Store, not
by the Pulse mechanism), while the tick alone decides *how* work gets
created. Keep the gate pure and every hard question in this chapter lands in
one place.

### The tick that creates work every time you ask

```python
def tick_naive(db, signal_id):
    sku = db.execute("SELECT sku FROM signals WHERE id = ?", (signal_id,)).fetchone()[0]
    scope = wake_gate(db, sku)
    if scope is None:
        return "signal does not qualify"
    count = db.execute("SELECT COUNT(*) FROM sows").fetchone()[0]
    sow_id = f"sow-for-{signal_id}-{count}"
    db.execute("INSERT INTO sows VALUES (?, ?, 'READY')", (sow_id, scope))
    db.commit()
    return f"created {sow_id}"


print(tick_naive(db, "sig-1"))
print(tick_naive(db, "sig-1"))  # a retry, a second runner, a crash-and-rerun...
print("SOWs on the ledger:", db.execute("SELECT COUNT(*) FROM sows").fetchone()[0])
```

```text
created sow-for-sig-1-0
created sow-for-sig-1-1
SOWs on the ledger: 2
```

One sale, one signal, **two** replenishment jobs — and nothing about the
second call was unreasonable. Ticks get retried; supervisors get restarted;
a crash right after a tick makes rerunning it the obviously safe move. Every
one of those ordinary events is now a duplicate freezer order. The naive
tick's flaw is structural: nothing durable records that *this signal was
already decided*, so every evaluation decides it again.

### The tick that claims the decision, atomically

The repair binds three things into **one transaction**: re-checking the
world, claiming the decision, and creating the work. The claim is the
`UNIQUE(source_signal_id)` insert — enforced by the database at the moment
of writing, not by a Python check a race can slip past — and a loser does
not fail: it returns the **winner's canonical identifiers**.

```python
db.execute("DELETE FROM sows")
db.commit()


def tick(db, signal_id):
    sku = db.execute("SELECT sku FROM signals WHERE id = ?", (signal_id,)).fetchone()[0]
    try:
        db.execute("BEGIN IMMEDIATE")
        scope = wake_gate(db, sku)  # REVALIDATED inside the transaction
        if scope is None:
            db.execute("ROLLBACK")
            return "signal no longer qualifies"
        cursor = db.execute(
            "INSERT INTO wake_decisions(source_signal_id, sow_id) VALUES (?, ?)",
            (signal_id, f"sow-{signal_id}"),
        )
        db.execute("INSERT INTO sows VALUES (?, ?, 'READY')", (f"sow-{signal_id}", scope))
        db.execute("COMMIT")
        return f"created sow-{signal_id} (decision {cursor.lastrowid})"
    except sqlite3.IntegrityError:
        db.execute("ROLLBACK")
        winner = db.execute(
            "SELECT sow_id FROM wake_decisions WHERE source_signal_id = ?", (signal_id,)
        ).fetchone()[0]
        return f"already decided: canonical work is {winner}"


print(tick(db, "sig-1"))
print(tick(db, "sig-1"))
print("SOWs on the ledger:", db.execute("SELECT COUNT(*) FROM sows").fetchone()[0])
```

```text
created sow-sig-1 (decision 1)
already decided: canonical work is sow-sig-1
SOWs on the ledger: 1
```

Run it a hundred more times: one SOW, forever. And look at what the loser
got back — not an error, but the canonical answer. A contender that loses
the race learns *which* work is the real one, which is exactly what a
restarted runner needs in order to carry on. This is also the crash-window
resume in miniature: a tick that finds the decision already committed but
the work not yet run doesn't create anything — it picks up the canonical
identifiers and resumes from there, which is precisely `run_pulse_once`'s
step one in production.

### The fault that leaves nothing behind

The claim and the work must commit **together**, or a crash between them
strands a decided-but-workless signal forever:

```python
db.execute("INSERT INTO signals VALUES ('sig-2', 'SKU-VANILLA', 'low_stock')")
db.commit()


def tick_with_fault(db, signal_id):
    sku = db.execute("SELECT sku FROM signals WHERE id = ?", (signal_id,)).fetchone()[0]
    try:
        db.execute("BEGIN IMMEDIATE")
        wake_gate(db, sku)
        db.execute(
            "INSERT INTO wake_decisions(source_signal_id, sow_id) VALUES (?, ?)",
            (signal_id, f"sow-{signal_id}"),
        )
        raise RuntimeError("power cut before the SOW was written")
    except RuntimeError as error:
        db.execute("ROLLBACK")
        return f"fault: {error}"


print(tick_with_fault(db, "sig-2"))
count = db.execute(
    "SELECT COUNT(*) FROM wake_decisions WHERE source_signal_id = 'sig-2'"
).fetchone()[0]
print("half-made decisions left behind:", count)
print(tick(db, "sig-2"))  # the next tick simply tries again, cleanly
```

```text
fault: power cut before the SOW was written
half-made decisions left behind: 0
created sow-sig-2 (decision 2)
```

Chapter 1's migration lesson, at the work-creation layer: a failure at *any*
boundary rolls the whole creation back, so recovery is never a repair — it
is just the next tick doing its ordinary job.

### The world moved; the signal did not

A signal records that something *was* true. Between the sale and the tick, a
manual restock can land — and the tick must ask the world again, inside its
own transaction, rather than trust the signal's snapshot:

```python
db.execute("INSERT INTO signals VALUES ('sig-3', 'SKU-VANILLA', 'low_stock')")
db.execute("UPDATE inventory SET on_hand = 9")  # a manual restock landed first
db.commit()
print(tick(db, "sig-3"))
print("SOWs on the ledger:", db.execute("SELECT COUNT(*) FROM sows").fetchone()[0])
```

```text
signal no longer qualifies
SOWs on the ledger: 2
```

This is Chapter 2's deepest rule — *re-read the world at the moment of the
act* — applied at the moment work is **born** instead of the moment it is
accepted. The signal was honest when written; the gate is honest now; no
work is created for a freezer that is already full.

The production mechanism, `run_pulse_once` in `src/sovereign_agent/pulse.py`,
is everything you just built plus the integration your toy elides: it resumes
already-fired signals whose canonical assignment never ran (the crash
window), asks the caller-supplied gate exactly as yours did, creates the
canonical SOW *and* assignment *and* origin rows through
`Organization.create_pulse_work` in one transaction, and then runs the
assignment through the very same fenced `run_assignment` path as Chapter 5 —
no Pulse-only bypass. One boundary is load-bearing enough to be a ruling:
the supervisor from Chapter 6 **never calls this**, and this module never
calls the supervisor — the two compose only through a foreground caller
running each as its own separate operation. Recovery reconciles work that
exists; Pulse creates work that should; a mechanism that did both would be a
process nobody could reason about when it failed halfway through either job.

### Break it: what the outcome-disambiguation guard is actually preventing

Your `wake_gate` only checked one thing: is `on_hand` still below `reorder`.
The Store's own production gate, `store_wake_gate` in
`src/reference_organizations/store/pulse_gate.py`, checks that and something
your toy never modeled, because your toy never had more than one outcome to
choose between. This is quoted verbatim from `pulse_gate.py` — an excerpt to
read, not a standalone block to run (`org` and `sku` are the surrounding
function's real arguments, not names this page defines):

```text
rows = org.db.connection.execute("SELECT record FROM outcomes").fetchall()
matching = []
for row in rows:
    record = json.loads(row["record"])
    if record.get("subject") == sku and record.get("state") == OutcomeState.ACTIVE.value:
        matching.append(record)
if len(matching) != 1:
    return None  # zero or ambiguous -- no durable rule disambiguates more than one
```

A signal names a SKU. It does not name which governed outcome the
replenishment work belongs to — that has to be looked up, and the lookup can
fail two different ways. Zero matching active outcomes means nobody has
chartered replenishment for this SKU yet, so there is no outcome to attach
the work to. More than one matching active outcome is worse: two different
principals could both plausibly own "keep `SKU-TEA` stocked," and the gate
has no rule for picking between them. Both cases return `None` — the same
signal the gate returns for "stock is fine now." A learner reading only the
JSON report cannot tell "already resolved" from "ambiguous ownership" apart;
that distinction lives in `pulse_gate.py`'s own source, not in the report.

```mermaid
flowchart TD
    Sig[Signal names one SKU] --> Look[Look up ACTIVE outcomes\nwhere subject = SKU]
    Look --> Zero{How many\nmatch?}
    Zero -->|0| None1[No outcome chartered yet\ngate returns None]
    Zero -->|1| Fire[Exactly one owner\ngate fires]
    Zero -->|2+| None2[Ambiguous ownership\ngate returns None]
```

**Figure:** The wake gate fires only when exactly one active outcome governs the signal's subject, refusing both missing and ambiguous ownership.

*Figure — the Store's outcome-disambiguation check inside `store_wake_gate`.
The stock-level check from the section above narrows signals to real
candidates; this second, independent check narrows candidates to signals
with exactly one unambiguous owner. Either failure mode returns the same
`None` a caller cannot distinguish from "already resolved" without reading
the source.*

Two tests in `tests/test_pulse.py` prove both halves fail closed rather than
guessing:
`test_no_active_outcome_matching_the_subject_creates_no_work` seeds a sale
with no outcome created for that SKU at all and asserts `report.created ==
()`; `test_more_than_one_matching_active_outcome_creates_no_work` activates
a *second* outcome naming the same SKU alongside the first and asserts the
identical empty result. Neither test asserts an error — a gate that raised
on ambiguity would turn an ordinary chartering mistake (two principals both
opening an outcome for the same SKU) into a crash instead of a quiet,
re-evaluable no-op. The signal is not consumed either way: it still has no
`pulse_wake_decisions` row, so a later Pulse pass — after someone closes the
duplicate outcome — evaluates it again and can still fire.

**Prove the ambiguous case yourself.** Chapter 0 seeded exactly one outcome
per SKU, so every earlier chapter's exercises never exercised this branch.
Run `solution.py` once normally, then run this against the same database to
force the ambiguity and watch the gate refuse where it previously fired:

```python
from pathlib import Path
from sovereign_agent.organization import Organization
from sovereign_agent.pulse import run_pulse_once
from reference_organizations.store import record_sale
from reference_organizations.store.pulse_gate import store_wake_gate

root = Path("/tmp/lucy-ch07-ambiguous")
org = Organization.init(root)
from reference_organizations.store import seed

seed(org.db)
first = org.create_outcome(
    "Keep the tea jar stocked",
    "On-hand tea is at or above reorder.",
    ["inventory_at_or_above_reorder_point"],
    "principal-human",
    "SKU-TEA",
)
org.activate(first.id, "master-course")
second = org.create_outcome(
    "A second outcome about the same SKU",
    "Also tea.",
    ["inventory_at_or_above_reorder_point"],
    "principal-human",
    "SKU-TEA",
)
org.activate(second.id, "master-course")  # two ACTIVE outcomes now name SKU-TEA

signal = record_sale(org.db, "SKU-TEA", 2, 400)
report = run_pulse_once(org, store_wake_gate)
print("created:", report.created)  # () -- refused, not fired
print(
    "signal still has no decision:",
    org.db.connection.execute(
        "SELECT COUNT(*) FROM pulse_wake_decisions WHERE source_signal_id = ?",
        (signal.id,),
    ).fetchone()[0]
    == 0,
)
```

```text
created: ()
signal still has no decision: True
```

The mutation: delete the `if len(matching) != 1: return None` guard from
your own local copy of `pulse_gate.py`'s `store_wake_gate` (leave everything
else unchanged — do not touch `matching = []` above it) and rerun the same
script. The gate now has no rule for the two-owner case, so it falls
through to `matching[0]` — a real `IndexError`-free but silently wrong
pick, arbitrary Python dict ordering deciding which of two legitimate
principals' outcomes gets the replenishment work with no record of why
that one won. `report.created` becomes a one-item tuple instead of `()`:
the mutated gate fires exactly where the real one must refuse, which is the
provable, falsifiable failure this exercise is built to expose — not an
assertion that the guard matters, but the guard's absence producing a
different, wrong, observable result on the same input.

## Add a watcher without turning every clock into Pulse

Pulse reacts to a durable domain signal. A freezer-temperature watcher has a
different shape: at a due time it observes the world, persists condition state,
and may fire a payload. A heartbeat cannot substitute for either mechanism. It
only records that a runtime reached the ledger at one moment.

```mermaid
flowchart TD
    Clock[Due time] --> Watch[Evaluate pure condition]
    Watch -->|fire=false| State[Persist observation state and next due time]
    State --> NoRun[Create no run row]
    Watch -->|fire=true| Claim[Uniquely claim automation plus due_at]
    Claim --> Payload[Call payload with durable run_id]
    Payload -->|success| Commit[Commit new condition state]
    Payload -->|failure| Fail[Record failure; keep old condition state]
    Fail --> Bound{failure budget reached?}
    Bound -->|yes| Disable[Disable automation]
    Bound -->|no| Retry[Remain eligible for a later due slot]
```

**Figure:** A scheduler records observations without inventing runs, uniquely claims each due slot, and commits new condition state only after successful payload execution.

The condition is a pure function from prior JSON state to
`WatchDecision(fire, message, state)`. Its serialized state is capped at 16
KiB. That limit keeps a convenient checkpoint from quietly becoming another
unbounded transcript.

### The false checkpoint

Suppose the condition observes a hot freezer and proposes
`{"notified": true}`. The supplier call then fails. If the scheduler commits
the proposed state before the payload succeeds, the next evaluation believes
the alert was already sent and suppresses the retry.

The implementation commits different facts at different moments:

| Outcome | Run row | Condition state | Failure count |
| --- | --- | --- | --- |
| not due | none | unchanged | unchanged |
| condition false | none | new observation | unchanged |
| payload succeeds | `SUCCEEDED` | proposed state | reset to zero |
| payload fails | `FAILED` | previous state | incremented |

After a configured number of payload failures, the automation disables itself.
That does not mean the business problem disappeared. It means repeated
unattended execution stopped and left a durable reason for intervention.

### Two schedulers, one due slot

A preflight query that says “no run exists” is not a claim. Two processes can
both read that answer. The actual serialization point is the database
constraint `UNIQUE(automation_id, due_at)`. Both contenders may evaluate the
condition, but only one can insert the run for that logical slot. The other
returns `REPLAYED` and never calls the payload.

Exactly-once external effects still require cooperation. The winning payload
receives the durable `run_id` as its idempotency key. A payment or notification
adapter must store or forward that key; SQLite cannot make a remote service
transactional by declaration.

Run the quiet-then-fire sequence:

```bash
uv run python book/ch07_the_organization_wakes_itself/advanced_exercise.py \
  --root /tmp/sa-ch07-automation
```

The expected statuses are `NO_FIRE` and `SUCCEEDED`. There must be one run row,
one payload call, a persisted `checks: 1` observation, and the payload's key
must equal the run id in the ledger.

Now make the false branch insert a run row. The CLI may still print
`NO_FIRE`, but the history lies by claiming work occurred. Then move condition
state persistence before the payload and make the payload raise. These proofs
must expose both mutations:

```bash
uv run pytest -q \
  tests/test_advanced_mechanisms.py::test_nonfiring_watcher_persists_state_without_inventing_a_run \
  tests/test_advanced_mechanisms.py::test_failed_payload_keeps_condition_state_retryable_and_auto_disables \
  tests/test_advanced_mechanisms.py::test_two_scheduler_processes_claim_one_due_slot
```

The scheduler here is a durable `run_due()` primitive. It does **not** install a
daemon or cron job. A native host timer can invoke it. Keeping hosting outside the
mechanism makes the important state transitions executable on a laptop while
leaving deployment frequency, clock ownership, and process supervision as
explicit system decisions.

## The exercise

```bash
uv run python book/ch07_the_organization_wakes_itself/solution.py --root /tmp/lucy-ch07
```

Read the file before you run it. Notice what is missing: no `create_sow`, no
`ready_sow`, no `assign`. A sale is committed — the same everyday act Chapter
0's exercise triggered by hand — and then exactly one call,
`run_pulse_once(org, store_wake_gate)`, is what turns that sale into governed,
executed, accepted work.

## Expected observations

```json
{
  "sale_committed_no_human_dispatch": {
    "signal_id": "sig_...",
    "below_reorder_after_sale": true
  },
  "pulse_report": {
    "status": "created",
    "sow_id": "sow_...",
    "assignment_id": "asg_...",
    "assignment_state": "COMPLETED"
  },
  "durable_pulse_event": {
    "new_event_kinds_this_run": [
      "assignment.created",
      "assignment.finished",
      "assignment.running",
      "assignment.workspace_boundary_checked",
      "pulse.work_created",
      "sow.created",
      "sow.ready"
    ],
    "pulse_work_created_present": true
  },
  "structured_origin": {
    "origin_kind": "pulse",
    "sow_id": "sow_...",
    "assignment_id": "asg_...",
    "wake_decision_id": "pdec_...",
    "pulse_event_id": "evt_...",
    "wake_decision_source_signal_id": "sig_...",
    "wake_decision_source_event_id": "evt_...",
    "wake_decision_traces_back_to_this_signal": true
  }
}
```

This is the whole chapter, in four facts:

1. **`pulse_work_created_present: true`.** A genuine `pulse.work_created`
   event landed in the append-only event log during this run — not asserted
   in prose, read back from the ledger after the fact, the same way Chapter
   0 taught you to check every other claim in this book.
2. **`origin_kind: "pulse"`.** Not inferred from the absence of a manual
   dispatch call — a column, read directly. This is a deliberate design
   principle: the absence of a CLI invocation, of process logs, or of a
   manual-origin row is *not* proof that work was self-generated. Only a
   positive, recorded origin is.
3. **`wake_decision_traces_back_to_this_signal: true`.** The full chain —
   signal → wake decision → Pulse event → SOW → assignment — is walkable,
   not merely claimed. The wake decision's own `source_signal_id` matches
   the exact signal this sale produced.
4. **`assignment_state: "COMPLETED"`.** The work Pulse created ran through
   the *exact same* `run_assignment` path a human-dispatched assignment
   uses — the same actor-lease and execution-attempt fencing from Chapter 5
   apply here with no exception, no Pulse-only bypass.

Confirm it yourself, independent of this exercise's own summary:

```bash
sqlite3 /tmp/lucy-ch07/.sovereign/organization.db <<'SQL'
SELECT po.origin_kind, po.sow_id, po.assignment_id,
       wd.source_signal_id, wd.source_event_id
FROM pulse_origins po
LEFT JOIN pulse_wake_decisions wd ON wd.id = po.wake_decision_id
ORDER BY po.created_at;
SQL
```

Expected: one row, `origin_kind = pulse`, naming a real signal and a real
source event.

## Why this Pulse claim is allowed here and nowhere else in this book

No chapter before this one calls `run_pulse_once`, and this project's own
curriculum checker refuses an earlier chapter from claiming that its exercise
did. Chapter 0 shows a ledger with no `pulse.*` event because that demo takes the
manual path. This chapter invokes Pulse for the first time in the learning
sequence and produces the durable origin chain. Pulse remains separate from a
heartbeat and from scheduling: this exercise calls it explicitly once.

The same curriculum checker that refuses an early chapter's Pulse claim
holds THIS chapter to a stricter standard than "the words are true": it
actually runs this exercise and inspects the resulting database for a real
`pulse.*` event and a real, traceable `pulse_origins` row before it will
accept this chapter's own prose claiming Pulse fired. A chapter that
fabricated a `pulse.work_created` event directly — bypassing
`run_pulse_once` entirely — would fail that check even though the *word*
"pulse" appeared nowhere suspicious in its prose. The claim has to be earned
by the mechanism, not merely phrased carefully.

## Learner verification command

```bash
uv run python -m pytest tests/test_pulse.py -k \
  "full_teaching_slice or attribution or does_not_bypass"
uv run python scripts/verify_curriculum.py
```

Expected: all pass. The pytest selection proves the full sale-to-accepted
slice through the real mechanism, the source-event-to-SOW attribution chain,
and that Pulse-created work is not exempt from Chapter 5's fencing.
`verify_curriculum.py` proves this chapter's own claim is backed by durable
evidence, not merely present in the prose — the mechanical guard this
project's own curriculum checker enforces specifically for Chapter 7.

## Exercise 2: prove the crash-window resume, don't just read the prose about it

Two sections back, this chapter asserted something and moved on: "a tick
that finds the decision already committed but the work not yet run doesn't
create anything — it picks up the canonical identifiers and resumes from
there, which is precisely `run_pulse_once`'s step one in production." That
sentence is a claim about `_resumable_signals` and `_resumable_signals`
alone (`src/sovereign_agent/pulse.py`). Exercise 1 never exercises this
path — its sale-to-completion run never crosses a crash boundary, so
`_resumable_signals` always returns nothing for that run. This exercise
forces the crash window open and checks what actually comes back.

```mermaid
flowchart LR
    C1[create_pulse_work\ncommits SOW + assignment\nassignment.state = CREATED] -->|hard kill here| K[process dies\nrun_assignment never called]
    K --> R2[fresh run_pulse_once\n_resumable_signals finds it]
    R2 -->|resumes SAME assignment| Done[assignment.state = COMPLETED\nledger: 1 SOW, 1 assignment]
```

**Figure:** A process death after work creation leaves a resumable assignment; the next pulse completes that same identity instead of duplicating the SOW and assignment.

*Figure — the crash window `_resumable_signals` closes. A hard kill between
canonical creation and provider execution leaves an assignment stuck at
`CREATED`; the next ordinary `run_pulse_once` pass — no special "resume"
flag, no operator action — finds it via the same query every pass runs and
invokes the identical assignment rather than minting a second one.*

Call `Organization.create_pulse_work` directly instead of `run_pulse_once`,
so the assignment it creates is left at `CREATED` — exactly what a hard
kill between canonical creation and provider execution would leave behind:

```python
from pathlib import Path
import shutil

from reference_organizations.store import record_sale, seed
from reference_organizations.store.pulse_gate import store_wake_gate
from sovereign_agent.models import Role
from sovereign_agent.organization import Organization
from sovereign_agent.pulse import run_pulse_once

root = Path("/tmp/lucy-ch07-crash")
shutil.rmtree(root, ignore_errors=True)

org = Organization.init(root)
seed(org.db)
outcome = org.create_outcome(
    "Keep the tea jar stocked",
    "On-hand tea is at or above the reorder point.",
    ["inventory_at_or_above_reorder_point"],
    "principal-human",
    "SKU-TEA",
)
org.activate(outcome.id, "master-course")

signal = record_sale(org.db, "SKU-TEA", 2, 400)
source_event_id = org.db.connection.execute(
    "SELECT id FROM events WHERE kind = 'sale.committed'"
).fetchone()["id"]

# THIS is the simulated crash: create_pulse_work runs, so the SOW,
# assignment, pulse.work_created event, and origin row are all durable --
# but nobody calls run_assignment. The assignment is left at CREATED.
sow, assignment, created = org.create_pulse_work(
    source_signal_id=signal.id,
    source_event_id=source_event_id,
    subject="SKU-TEA",
    outcome_id=outcome.id,
    scope="pulse replenishment",
    role=Role.OPERATOR,
    planner_id="master-course",
    worker_id="operator-course",
    required_effect_kind="replenishment",
)
print("assignment state after simulated crash:", assignment.state.value)
org.db.close()

# "Restart": a fresh Organization handle over the SAME database file, then
# one ORDINARY Pulse pass -- nothing tells it a crash happened.
resumed = Organization(root)
report = run_pulse_once(resumed, store_wake_gate)
print("items in the resume pass's report:", len(report.items))
print("status:", report.items[0].status)
print("resumed assignment id == original:", report.items[0].assignment_id == assignment.id)
print("resumed assignment state:", report.items[0].assignment_state)
```

```text
assignment state after simulated crash: CREATED
items in the resume pass's report: 1
status: replayed
resumed assignment id == original: True
resumed assignment state: COMPLETED
```

Four things this proves, read back from the report rather than asserted:
the resume pass reports exactly one item for a signal that already has a
wake decision — `_unevaluated_signals` correctly does not re-offer it to
the gate, because re-deciding an already-decided signal is not this
function's job; the status is `"replayed"`, never `"created"` — nothing
new was minted; the assignment id is byte-identical to the one
`create_pulse_work` returned before the simulated crash — this is
*resumption*, not a lookup that merely resembles one; and the assignment
that was stuck at `CREATED` reaches `COMPLETED` through the exact same
`run_assignment` call every other path in this chapter uses, with no
special-cased "resume" branch that could drift from ordinary execution.

**The mutation.** Comment out exactly the resume loop in
`src/sovereign_agent/pulse.py`'s `run_pulse_once` — the two lines quoted
verbatim below, to read and delete in your own local copy, not a
standalone block to run:

```text
    for signal, sow_id, assignment in _resumable_signals(org):
        items.append(_invoke_or_report(org, signal.id, sow_id, assignment, created=False))
```

— leaving `_unevaluated_signals` and everything below it untouched, then
rerun the script above against a fresh `/tmp/lucy-ch07-crash`. The mutated
function no longer asks the database which signals already fired but never
finished; it only asks which signals have never been decided at all — and
this signal already has a decision, so it is invisible to both loops:

```text
assignment state after simulated crash: CREATED
items in the resume pass's report: 0
```

`report.items` is `()`. Not an error, not a refusal — silence. The
`CREATED` assignment this run left behind is never picked up by this or
any later pass, because nothing in the mutated function ever looks for it
again; the sale that woke the organization produced work that then sits
forever, half-finished, with a green `create_pulse_work` return and no
downstream signal that anything is wrong. This is the exact failure mode
`tests/test_pulse.py::test_canonical_created_work_survives_restart_and_resumes_without_duplication`
exists to catch on every commit — restore the two lines before moving on;
this repository's own suite will otherwise fail on the next `make verify`.

## Summary

The organization can now wake itself through `run_pulse_once`: a pure
gate that decides what work a signal warrants, and a `UNIQUE(source_signal_id)`
claim, made inside one transaction with the SOW and origin rows it creates,
that lets exactly one canonical decision exist per signal.

The chapter then added a durable automation state machine. A non-firing
condition persists observation state without inventing a run, a firing slot is
claimed once by `(automation_id, due_at)`, and payload failure never commits a
false checkpoint.

The governing condition is that self-generated work is provable only
positively — a real `pulse.work_created` event and a `pulse_origins` row
naming a real signal — never inferred from the absence of a manual
dispatch call, which this chapter's own curriculum checker enforces by
re-deriving the claim from the database rather than trusting the prose.

The naive tick's double-order is now refused: retried or
re-run against the same signal, it created two replenishment SOWs from one
sale, and nothing about that retry was unreasonable — ticks get retried
constantly. The claimed decision closes it structurally, at the database.

For Lucy, this is the freezer alarm that fires exactly once per
low-stock sale, however many times the alarm system itself gets restarted
or double-checks its own work.

## Explain it back

1. This file never calls `create_sow`, `ready_sow`, or `assign`. What
   function call is doing the work those three calls did in every earlier
   chapter, and what does it do differently?
2. `pulse_wake_decisions.source_signal_id` is `UNIQUE`. What real problem
   does that one constraint prevent, at the database level, that a
   Python-level "check first, then insert" could not?
3. "Absence of a manual-origin row is not proof of Pulse origin." Why is
   that distinction worth a dedicated table rather than just checking
   whether any human-facing CLI command was invoked?
4. The assignment Pulse created ran through the exact same `run_assignment`
   path Chapter 5 fenced. Why does that matter for trusting this chapter's
   own `COMPLETED` result?
5. What specifically would make this chapter's own Pulse claim FALSE — name
   at least two different ways the underlying ledger could fail to back up
   the prose above, and explain how you would notice.
6. `tick_naive` was defeated by perfectly reasonable behavior — retries and
   restarts, not attacks. Why is "just don't call it twice" not an
   acceptable fix, and what does the UNIQUE claim change structurally?
7. The losing contender returns the winner's canonical identifiers instead
   of an error. Name the caller that specifically needs that behavior, and
   what it would wrongly do if it got an exception instead.
8. `sig-3` was honest when recorded, yet created no work. Reconcile "signals
   are durable append-only facts" with "this signal produced nothing" —
   which of the two would it be dishonest to change?
9. A watcher records `notified=true` and then its supplier call fails. Why must
   the next run see the old state, and what durable identifier should the remote
   call use for idempotency?

## Where to look next

- `src/sovereign_agent/pulse.py` — `run_pulse_once`, the whole mechanism
- `src/reference_organizations/store/pulse_gate.py` — the Store's own wake
  gate, deliberately outside `sovereign_agent`'s own module budget
- `tests/test_pulse.py` — the full proof matrix, including that the canonical
  creation transaction (signal → wake decision → SOW → assignment) is genuinely
  atomic, so a crash mid-creation cannot strand a half-woken piece of work

`solution.py` imports the production package rather than copying it.

You have now built the whole spine of a governed organization: memory,
judgement, bounded work, fenced authority, recovery, and signal-driven work
creation. Chapters 8 through 12 turn from the machinery to the shop itself—
Lucy's catalog grows, and you watch every guarantee you built hold up as it
scales. Heartbeat-based liveness and due-time automation remain separate from
Pulse, and this chapter now gives each mechanism its own falsifiable claim.

Next: [Chapter 8 — The Store becomes a catalog](../ch08_the_store_becomes_a_catalog/README.md)
