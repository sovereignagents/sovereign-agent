# Sovereign Agent: the executable textbook

The book grows with the implementation. Each chapter uses the production
package; it does not copy or fork it.

**New here? Start with the front matter:** [`PREFACE.md`](PREFACE.md) (who
this book is for, prerequisites, setup, and the build-break-repair teaching
method) and [`CONVENTIONS.md`](CONVENTIONS.md) (notation, recurring terms,
and the chapter-to-lab map). Both are additive — the chapter sequence below
is unchanged and remains the required reading path.

Read them in order. Each one takes apart something the previous chapter asked
you to take on faith.

Use the [companion labs](labs/README.md) alongside the chapters. Every lab gives
you an intentionally incomplete starter, behavioral checks, adversarial
mutations, and a verified reference solution. The checks grade observable
invariants rather than requiring your code to look like the reference.

After Chapter 12, continue with [Advanced mechanisms](ADVANCED_MECHANISMS.md):
six compact, production-shaped lessons in isolation, unattended schedules,
context compaction, session incarnations, progressive tool discovery, and
hybrid memory retrieval.

The chapters are organized into three parts:

- [Part 1: Durable foundations](parts/part-1-durable-foundations.md), Chapters 0–3
- [Part 2: Bounded autonomy](parts/part-2-bounded-autonomy.md), Chapters 4–7
- [Part 3: Proof at scale](parts/part-3-proof-at-scale.md), Chapters 8–12

- [Chapter 0: Lucy's first shift](ch00_first_shift/README.md) — run one
  complete piece of work and learn that `ACCEPTED` is a proved claim
- [Chapter 1: The organization remembers](ch01_organization_remembers/README.md) —
  SQLite, transactions, append-only events, hybrid memory retrieval, and what
  is canonical versus derived
- [Chapter 2: Work needs governance](ch02_work_needs_governance/README.md) —
  outcomes, SOWs, evidence, verification, review, and no-self-approval
- [Chapter 3: The actor is not a model](ch03_actor_is_not_a_model/README.md) —
  providers are probed CLIs; source-preserving context compaction; tool
  discovery kept separate from authority
- [Chapter 4: Work stays inside its boundary](ch04_work_stays_inside_its_boundary/README.md) —
  a detectable workspace boundary, safe joins, reclaim, and five independently
  qualified isolation planes
- [Chapter 5: Authority needs a fence](ch05_authority_needs_a_fence/README.md) —
  process identity, actor leases, execution-attempt fencing, and multi-host
  session incarnations
- [Chapter 6: The organization recovers](ch06_the_organization_recovers/README.md) —
  a real hard-killed worker, and the supervisor that recovers it without
  guessing success
- [Chapter 7: The organization wakes itself](ch07_the_organization_wakes_itself/README.md) —
  genuine Pulse: governed work created without a human prompt, with durable,
  structured evidence; plus a distinct durable condition scheduler
- [Chapter 8: The Store becomes a catalog](ch08_the_store_becomes_a_catalog/README.md) —
  the single-product fixture becomes a genuine multi-SKU catalog
- [Chapter 9: Each product has its own threshold](ch09_each_product_has_its_own_threshold/README.md) —
  independent stock state and reorder decisions, per SKU
- [Chapter 10: One signal wakes one need](ch10_one_signal_wakes_one_need/README.md) —
  the wake gate binds each signal to its own SKU's own outcome, never another's
- [Chapter 11: Replenishment scales without losing governance](ch11_replenishment_scales_without_losing_governance/README.md) —
  multiple governed replenishment chains, idempotency and attribution intact
- [Chapter 12: The pilot begins with a receipt](ch12_the_pilot_begins_with_a_receipt/README.md) —
  the pilot-start mechanism, exercised against a disposable identity, and
  what "started" does and does not mean

## Where the book goes

Chapters 0–3 are manually dispatched because durable memory and governed work
must exist before proactive execution can be honest. Chapters 4–6 add
containment, fencing, and recovery. Chapter 7 is the first chapter in which a
durable signal creates governed work without a human prompt. Chapters 8–12
then add the second product, retries, causal attribution, and a pilot-start
receipt that states exactly what has and has not been proven.

After the main sequence, use the
[field guide to the agent ecosystem](AGENT_ECOSYSTEM_MAP.md) to map the book's
mechanisms to MCP, A2A, OpenTelemetry, OWASP agentic threats, and NIST AI risk
practice. The map translates interfaces; it does not treat protocol support as
proof of authority or outcome.

## Every chapter contains

- a concrete learning objective
- a runnable exercise
- expected observations
- a learner verification command
- an "explain it back" section
- a `solution.py` that imports the production package

Run `python scripts/verify_curriculum.py` to check that all of that is actually
present and that the chapters' imports still work.

Run `python scripts/verify_book_labs.py` to execute all companion reference
solutions twice from fresh roots and compare their observations with the
checked-in expected results.
