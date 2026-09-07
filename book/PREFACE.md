# Preface

## Why this book exists

Most material about AI agents teaches you to write a prompt and trust the
answer. This book teaches the opposite habit: build the smallest mechanism
that lets a claim be checked, then check it — by hand, adversarially, before
you ever let production code make the claim for you.

The organizing question is not "can a model do this task?" It is "when the
model, or the script, or the tired human says the task is done, what
*specifically* would have to be true for that to be trustworthy, and what
happens the moment it is not?" Every chapter answers that question for one
mechanism: memory, governance, actor identity, workspace boundaries,
authority, recovery, proactive work, and a multi-product catalog that has to
hold all of the above at once.

The book grows with a real, runnable implementation. Nothing here is
pseudocode standing in for a system that does not exist. Every fenced code
block executes; every printed output is a real transcript. `book/README.md`
lists all thirteen chapters; this preface, and its companion
[`CONVENTIONS.md`](CONVENTIONS.md), are the front matter that sits ahead of
Chapter 0.

## Who should read this book

The book is calibrated to a specific reader rather than an abstract
"beginner": a master's student or working developer who knows some Python,
has written scripts and notebooks, but has not yet operated a service,
debugged a transaction, or designed authority boundaries. Independent learner
sessions shaped which explanations stayed and which were rewritten.

Lucy, who runs the ice cream shop every chapter returns to, is fictional. She
is the running case that makes each mechanism concrete. You are the engineer
building the organization on her behalf.

If you are comfortable with Python classes, can read a `pydantic` model, and
have never had to explain why a status field can lie: this book is written
for you directly. If you already run production distributed systems for a
living, several early chapters (transactions, at-most-once writes) will feel
slow; the later multi-SKU chapters (8-12) and the causal-binding argument in
Chapter 10 are where this book has the most to offer you specifically.

## Prerequisites

Explicit, so you can check them before you start rather than discover a gap
mid-chapter:

- **Python**, comfortably: functions, classes, exceptions, and reading a
  `pydantic` model definition. Chapter 3 uses `pydantic.BaseModel`, and
  several chapters build small SQLite scripts you paste into a shell.
- **Basic SQL**: `SELECT`, `INSERT`, `UPDATE`, and knowing what a
  transaction is *supposed* to guarantee. You do not need to know SQLite's
  specific quirks going in — Chapter 1 teaches the ones that matter here,
  including at least one that surprises experienced database users.
- **A terminal**, and the willingness to actually run the commands rather
  than read past them. This book's central discipline — check the claim,
  don't trust it — only works if you run the checks yourself.
- **No machine-learning background is required.** Chapter 3 states this
  explicitly: the actor/provider distinction this book teaches applies
  whether the "provider" is a deterministic script or a frontier model, and
  understanding it does not require having trained or fine-tuned anything.

## Setup

This book does not duplicate the repository's own onboarding instructions —
they already exist, are exercised by an automated gate
(`scripts/verify_readme_onboarding.py`), and would drift out of sync with a
second copy here. Use the canonical path:

1. **Root [`README.md`](../README.md)** — install with `uv`, the Python 3.14
   floor, and the "Unit 1 gates" smoke commands that prove your environment
   is sound before you open Chapter 0.
2. **[`docs/quickstart.md`](../docs/quickstart.md)** — a ten-minute, no-API-key
   walkthrough of the exact shift Chapter 0 tours: install, run one shift,
   check whether the organization told you the truth, break it on purpose,
   and see the checker catch the lie. If you only read one setup document
   before starting Chapter 0, read this one.

Every chapter after Chapter 0 assumes you have already run
`uv sync && uv run sovereign-agent doctor` successfully once. If `doctor`
reports a problem, resolve it before continuing — the chapters that follow
depend on the `scripted` provider being available, and `doctor` is what
confirms it is.

## The teaching method: build it, break it, repair it

Every chapter after this preface follows the same rhythm, stated explicitly
in Chapter 0's own closing table so you recognize it from the first page:

1. **Build** a small, honest version of the real mechanism yourself, in a
   throwaway script or a pasted Python shell session — never the production
   module itself, not yet.
2. **Break** it. Each chapter shows the tempting, plausible-looking version
   of the mechanism failing in a specific, reproducible way: a migration that
   half-applies, an oversell race, a double-order under retry, a verifier
   that "helpfully" repairs the evidence it was supposed to be checking. You
   watch the failure happen, with real output, not a description of a
   failure that might occur.
3. **Repair** it into the shape the production code actually uses, and read
   the real module afterward to confirm every clause you just built by hand
   is there for the exact reason you just watched.

The method exists because reading a finished, correct function teaches you
*what* it does; it does not teach you *why every clause earned its place*.
Chapter 2's `accept()` is the clearest example in the book: it is built as
seven successive versions, each one closing a specific lie the version
before it still let through, so that by the time you read the real
`Organization.accept()` you recognize every line as the fix for a mistake
you just watched yourself make.

Every chapter also names, explicitly, what it has *not* proven — a stated
limit, not a hedge. Chapter 4's boundary check is honest about what it
cannot see outside its own scope; Chapter 12 ends the book by building a
verifier and then forging a pack that passes it anyway, to show you exactly
where "internally consistent" stops meaning "true." Knowing precisely where
the proven part ends is treated as part of the mechanism, not an admission
of failure.

## What this book is not

It is not a catalogue of prompt patterns or a wrapper around one model vendor.
It does not claim that a green test suite proves a deployment safe. It teaches
how to state a narrower claim, preserve the evidence for it, and refuse to
promote that claim when the evidence or authority is insufficient.

Continue to [Chapter 0 — Lucy's first shift](ch00_first_shift/README.md), or
read [`CONVENTIONS.md`](CONVENTIONS.md) first for the notation and the
chapter-to-lab map.
