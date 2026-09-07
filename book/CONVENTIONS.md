# Notation, conventions, and the chapter-to-lab map

This is the second half of the book's front matter, alongside
[`PREFACE.md`](PREFACE.md).

## Recurring terms

This is a short glossary of terms the book uses repeatedly across chapters,
not a restatement of the root [`README.md`](../README.md)'s own "Product
vocabulary" table (which covers the shipped CLI's nouns — `supervisor`,
`pulse`, `heartbeat`, `provider`, `actor`). The terms below are the book's
own recurring narrative and mechanism vocabulary.

- **Statement of work (SOW).** A statement of work: the scope, non-goals,
  deliverables, and done-when conditions for one piece of governed work,
  first defined in [Chapter 2](ch02_work_needs_governance/README.md)'s own
  vocabulary table. Used as "SOW" throughout the rest of the book once
  introduced — this glossary entry is that introduction for any reader who
  starts here instead of at Chapter 2.
- **Lucy.** The book's fictional running example: the owner of an ice cream
  shop who hands progressively more governed work to the organization you
  build. Every chapter returns to the operational consequence at her shop.
- **Compare-and-set (CAS).** A single atomic database statement whose
  `WHERE` clause both decides *and* performs a write in one step, so that no
  window exists between "read the current state" and "act on it" for a
  second, concurrent actor to land in. Introduced in
  [Chapter 5](ch05_authority_needs_a_fence/README.md), reused by name (and
  abbreviated CAS after its first spell-out per chapter) in Chapters 6, 11,
  and 12 for the mailbox claim, actor lease, execution attempt, wake
  decision, idempotency key, and pilot-start mechanisms respectively — one
  shape, applied to six different tables.
- **Fencing token.** A number drawn from one shared, strictly increasing
  counter, presented at a terminal write to prove the writer's authority is
  still current. Introduced in Chapter 5 alongside compare-and-set; the two
  are related but distinct — a CAS decides *who wins right now*, a fencing
  token additionally guarantees a *later*, stale winner can never write
  successfully after being superseded.
- **Signal.** A durable, append-only "something needs attention" fact —
  never a task, never work itself. Introduced in
  [Chapter 7](ch07_the_organization_wakes_itself/README.md).
- **Wake gate / wake decision.** The deterministic function that decides
  whether a signal still merits work (the gate), and the durable,
  `UNIQUE`-constrained row recording that a specific signal fired exactly
  once (the decision). Both introduced in Chapter 7.
- **Context compaction.** An append-only derived view over transcript source,
  never permission to delete or rewrite the messages it summarizes. Built in
  [Chapter 3](ch03_actor_is_not_a_model/README.md).
- **Session incarnation.** A monotonically increasing generation that
  distinguishes successive claims on one resumable session, even when actor,
  host, and session names repeat. Built in
  [Chapter 5](ch05_authority_needs_a_fence/README.md).
- **Tool discovery / authorization.** Retrieval decides which tool schemas are
  relevant enough to show; policy independently decides which tool may run.
  Built in [Chapter 3](ch03_actor_is_not_a_model/README.md).
- **Automation due slot.** One durable `(automation_id, due_at)` claim. A
  condition evaluation is not a run, and a heartbeat is not a scheduler.
  Built in [Chapter 7](ch07_the_organization_wakes_itself/README.md).
- **Causal binding.** The requirement that acceptance trace a real
  provenance path — this exact execution produced this exact required
  effect on this exact subject — rather than merely observing that a world
  condition happens to hold. The deepest idea in the book; built across five
  generations of one function in
  [Chapter 10](ch10_one_signal_wakes_one_need/README.md).
- **Status tokens** (`ACCEPTED`, `COMPLETED`, `FAILED`, `REFUSED`, and
  similar). Written in backticks when the book is naming the literal token
  or field value under discussion (a table cell, a state-machine label, "the
  word `ACCEPTED`"), and left as plain prose when narrating what happened in
  a sentence ("the demo printed ACCEPTED and the shelf was empty"). Match
  this convention if you add prose referencing a status.

## Notation used in derivations

A handful of chapters (9 and 10 especially) write a predicate mathematically
before showing it in code, to expose boundary choices prose can hide easily
(does `≤` include the boundary itself, is a field derived or supplied). Read
`⇔` as "if and only if," `∧` as "and," and a function-style
name like `available(sku)` as a value computed from the ledger at the
instant it is evaluated — never a value carried in from an earlier read.

## The build-break-repair method, briefly

See [`PREFACE.md`](PREFACE.md#the-teaching-method-build-it-break-it-repair-it)
for the full explanation. In short: each chapter has you build a small honest
version of a mechanism yourself, watch a specific, reproducible failure with
real output, then repair it into the shape production code actually uses —
and each chapter states plainly what it has *not* proven, as part of the
mechanism, not an admission of failure.

## Chapters and their companion labs

Every chapter has exactly one companion lab, at the identical directory name
under [`labs/`](labs/README.md) (`book/chNN_<slug>/` pairs with
`book/labs/chNN_<slug>/`). The lab is a small, reduced, executable experiment
mapped to exact production symbols and tests — not an alternative
implementation, and not required to complete the chapter itself, but the
place to go for a graded exercise with a starter, a checker, and a reference
solution.

| Chapter | Companion lab |
| --- | --- |
| [0 — Lucy's first shift](ch00_first_shift/README.md) | [`labs/ch00_first_shift`](labs/ch00_first_shift/README.md) |
| [1 — The organization remembers](ch01_organization_remembers/README.md) | [`labs/ch01_organization_remembers`](labs/ch01_organization_remembers/README.md) |
| [2 — Work needs governance](ch02_work_needs_governance/README.md) | [`labs/ch02_work_needs_governance`](labs/ch02_work_needs_governance/README.md) |
| [3 — The actor is not a model](ch03_actor_is_not_a_model/README.md) | [`labs/ch03_actor_is_not_a_model`](labs/ch03_actor_is_not_a_model/README.md) |
| [4 — Work stays inside its boundary](ch04_work_stays_inside_its_boundary/README.md) | [`labs/ch04_work_stays_inside_its_boundary`](labs/ch04_work_stays_inside_its_boundary/README.md) |
| [5 — Authority needs a fence](ch05_authority_needs_a_fence/README.md) | [`labs/ch05_authority_needs_a_fence`](labs/ch05_authority_needs_a_fence/README.md) |
| [6 — The organization recovers](ch06_the_organization_recovers/README.md) | [`labs/ch06_the_organization_recovers`](labs/ch06_the_organization_recovers/README.md) |
| [7 — The organization wakes itself](ch07_the_organization_wakes_itself/README.md) | [`labs/ch07_the_organization_wakes_itself`](labs/ch07_the_organization_wakes_itself/README.md) |
| [8 — The Store becomes a catalog](ch08_the_store_becomes_a_catalog/README.md) | [`labs/ch08_the_store_becomes_a_catalog`](labs/ch08_the_store_becomes_a_catalog/README.md) |
| [9 — Each product has its own threshold](ch09_each_product_has_its_own_threshold/README.md) | [`labs/ch09_each_product_has_its_own_threshold`](labs/ch09_each_product_has_its_own_threshold/README.md) |
| [10 — One signal wakes one need](ch10_one_signal_wakes_one_need/README.md) | [`labs/ch10_one_signal_wakes_one_need`](labs/ch10_one_signal_wakes_one_need/README.md) |
| [11 — Replenishment scales without losing governance](ch11_replenishment_scales_without_losing_governance/README.md) | [`labs/ch11_replenishment_scales_without_losing_governance`](labs/ch11_replenishment_scales_without_losing_governance/README.md) |
| [12 — The pilot begins with a receipt](ch12_the_pilot_begins_with_a_receipt/README.md) | [`labs/ch12_the_pilot_begins_with_a_receipt`](labs/ch12_the_pilot_begins_with_a_receipt/README.md) |

Run every lab's reference solution twice from a fresh root, for all
thirteen chapters at once:

```bash
uv run python scripts/verify_book_labs.py
```

Return to [`PREFACE.md`](PREFACE.md) or continue to
[Chapter 0](ch00_first_shift/README.md).
