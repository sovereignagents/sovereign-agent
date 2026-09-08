**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

# Build Your Always-On AI Agent From Scratch

**Subtitle:** Tools, memory, permissions, and reliable operation in Python.
**Author:** Rod Rivera. **Submission status:** Internal proposal; not sent to a publisher.

## The reader's promise

Build a self-contained Python agent for Lucy's ice cream shop: it answers through
one messaging channel, remembers preferences, wakes for stock events, asks before
spending, and recovers work without blindly repeating a purchase. The reader
implements the model/tool loop and surrounding runtime, using an HTTP model API,
SQLite and standard operating-system services as infrastructure. No finished
agent framework or private organizational service is required.

The intended reader can write Python functions and classes, use a terminal and
understand JSON. No agent-framework experience is assumed. Lucy is the customer;
the reader is her technically capable builder. The main implementation uses
Python 3.14, one runtime dependency, and a committed development lock. The measured
budget covers both the core and installed integrations; it does not hide the
channel, skills or MCP client in an uncounted dependency.

## Why this book, and why now

Recognizable projects such as OpenClaw, NanoClaw and Hermes make agents with
memory, tools and unattended work concrete examples for readers. They also expose
choices worth understanding: who owns the reasoning loop, where memory lives,
what a gateway authenticates, and what a sandbox actually enforces. The chapters
teach those decisions through construction. Pinned project comparisons provide
bounded evidence, with author rationale separated from interpretation.

The distinctive promise is reliable action that a builder can explain. Lucy's
supplier can accept an order and lose the reply; two workers can overlap after a
crash; a restored database can omit a purchase that happened afterward. Readers
reproduce those failures and add the specific records, approvals and fences that
resolve them. This is stronger than concluding a tutorial at a fluent response.
It is also a bounded teaching system, not a claim to reproduce a mature fleet
platform in one book.

No search-volume study or acquisition probability supports this proposal. Project
names are discovery topics, not evidence of an SEO increase. The durable title
uses “always-on AI agent”; project names appear in chapter descriptions and a
dated reference appendix where they can be revised without changing the spine.

## Construction and chapter outcomes

The four-part [source contents](../../book/always_on/PUBLICATION.json) contain
sixteen chapters. Chapters 1–3 build a useful tool-using draft agent. Chapters 4–7
add memory, skills, phone intake and actual supervised unattended draft work.
Chapters 8–11 introduce exact approval, ambiguous-effect reconciliation, worker
recovery and restricted execution. Chapters 12–16 evaluate outcomes, control
improvement, justify one delegation, practice Linux maintenance and run Lucy's
integrated day. Each chapter has runnable examples, an observable outcome,
a failure experiment and exercises that change a constraint.

The shop contains multiple products from the beginning. Catalog and per-product
threshold work is integrated into tools, stock conditions and acceptance rather
than consuming several small chapters. The original thirteen-chapter curriculum
and labs remain available under their existing identities. Conversational memory,
external effect recovery, worker ownership and operational restore are separate
problems with separate proofs.

The final accelerated day includes an independent supplier database, duplicate
messages, corrected preferences, a failed model call, exact approvals, lost
responses, a killed worker and receiving. Authored expectations require exactly
two supplier orders totaling 2600 pence. A deterministic report distinguishes
physical stock, pending replenishment, reservations and confirmed expenditure.
The fixture uses model and Telegram transport substitutes; live facilities have
separate receipts and acceptance conditions.

## Proposed sample package

Read [Chapter 1](../../book/always_on/ch01_first_model_call/README.md) for entry-level
exposition, [Chapter 3](../../book/always_on/ch03_agent_loop/README.md) for the owned
loop, and [Chapter 9](../../book/always_on/ch09_ambiguous_order/README.md) for the
book's distinctive depth. Chapter 9 is the primary sample: the supplier accepts,
the response disappears, and a small durable protocol changes what the builder
can safely conclude. Its runnable checkpoint is
[checkpoints/ch09.py](../../book/always_on/checkpoints/ch09.py). The preface and
conventions specify prerequisites and evidence labels before any sample is read.

The comparative benchmark is the construction-first promise in Manning's
[Build a Large Language Model from Scratch](https://www.manning.com/books/build-a-large-language-model-from-scratch).
The parallel is the reader implementing and understanding the essential
components. We do not claim equal editorial quality because the artifact has a
similar shape, or describe an agent loop as training a language model.

## Extent and production status

The current main chapters contain approximately 59,543 prose words outside code
fences, 5,223 code/output lines excluding Mermaid, 52 source-captioned figures and
97 selected listings. The [measurement receipt](../evidence/always-on/manuscript-extent-v1.json)
pins each chapter's bytes and counting method. Illustrative density assumptions
give roughly 266–355 main-text pages before front matter, appendices, code wrapping
and publisher layout decisions. Plan provisionally for 320–380 pages, then replace
that estimate with typeset sample measurements. This is not a measured page count.

All sixteen chapters are DRAFT. Their construction gate executes 139 Python
examples and 131 paired outputs. The runtime passed 697 deterministic tests before
the publication-contract tests were added; versioned subsequent receipts carry
the final gate counts. Linux service restart, compatible upgrades, restore,
container boundaries and live model evaluations have recorded experiments. A
shape score of 100 is evidence about named checks, not independent editorial
acceptance. Live phone observation, manuscript review and rendered page review
remain open. No month-of-uptime claim is made.

## Author suitability and platform

Rod Rivera maintains the teaching implementation and authors the running shop
example. His [public profile](https://www.profrod.ai/about) describes his work as a
Professor of Practice at ITAM, teaching and industry AI experience. Those profile
claims should be checked against the author's submission CV before sending the
proposal; this draft invents no audience size, sales history or publisher interest.
Prof Rod is the reader-facing book home. Sovereign Agent owns the source; Zeocore
provides an optional connection to maintained integrations in a separate environment.

## Submission and review plan

Manning's [author guidance](https://www.manning.com/write-for-us) asks proposals to
explain timeliness, differentiation, reader outcomes and author suitability. This
draft addresses those topics. The linked proposal form returned no readable body
during preparation, so this document does not claim to reproduce its current fields.
No proposal has been emailed or otherwise submitted.

Before submission, obtain a cold reader's review of the sample construction,
inspect the site on desktop and phone, complete the dedicated Telegram exchange,
verify the source-to-site pin and assemble the current gate receipts. Ask reviewers
to identify where the explanation outruns the code, where a fixture is mistaken
for live evidence, and where a familiar Python reader cannot reproduce a step.
Incorporate findings in source and regenerate the projection. The operator retains
the final publisher contact and manuscript acceptance decision.
