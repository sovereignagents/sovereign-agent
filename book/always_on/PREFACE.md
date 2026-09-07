# Build an agent you can leave with work

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

Lucy runs an ice cream shop. She wants to open her phone in the morning and find a useful stock brief, approve an order when it exceeds her allowance, and return later to a record of what actually happened. You are the developer building that agent for her. The question driving this book is practical: what must you implement before leaving the agent unattended becomes a reasonable decision?

You begin with several products and one model call. By Chapter 3 you have written the model–tool–observation loop that prepares a grounded replenishment draft. You then give that same agent persistent preferences, reusable procedures, a phone connection and scheduled work. When the supplier accepts an order but loses the response, you build the records and reconciliation that prevent a blind repeat. When a process dies, you separate the durable assignment from the worker that happened to be carrying it out.

## What “from scratch” means here

You implement the loop, tool dispatch, context assembly, SQLite records, scheduler, permissions, approvals, recovery, a small messaging adapter and a bounded MCP client. Python's standard library and Pydantic provide ordinary programming infrastructure. An existing model supplies language reasoning through a thin HTTP adapter. SQLite supplies transactions; Linux and a container engine supply operating-system mechanisms. You do not import a finished agent framework or depend on a private organizational service to run the book.

The repository also contains earlier provider integrations that delegate reasoning to installed CLI agents. Those are alternatives in the wider project; they do not replace the reader-owned loop in this edition. Nor do you train a language model. The construction target is the agent around a model, with each important boundary visible in code you can inspect and modify.

## Who should read it

You can already write Python functions and classes, use a terminal, and understand JSON. Basic SQL helps, but the chapters explain the queries on which each design depends. Python 3.14 and the committed environment lock are the main path. No prior agent-framework knowledge is assumed. Lucy is the customer, not a fictional shop owner who must suddenly become a runtime engineer.

The ordinary checkpoints run locally without model credentials, a Telegram account or live purchasing. Live model exercises require an HTTP model endpoint; the main path uses a local Ollama model. Phone exercises require your own Telegram test bot and account. Actual service operation and the code sandbox use one Linux host. Each chapter says which evidence its portable fixture can establish and which observation needs those additional facilities.

## Why the records matter

A fluent answer and a successful process exit are useful observations. Neither establishes that the supplier received one order, that a revoked approval was refused, or that a replacement worker owns the next write. These become observable business questions in Lucy's shop. Authority and recovery enter the story when their absence produces a failure you can reproduce.

The final accelerated day retains a separate supplier database as well as the agent's state. You compare operation identifiers and authored amounts, receive an order exactly once, and generate a report from structured records. Its spending total is purchase expenditure, not profit or an invoice for model usage. A shorter script remains the comparison whenever it can perform the same task more predictably.

## A bounded promise

“Always-on” means the installed system can receive and process work while you are away, while its host and dependencies are available. Waiting does not require model calls. Persistent intake, jobs and approvals survive a restart; ambiguous external outcomes require reconciliation. Host failure, a provider without discoverable history, and compromised infrastructure still have limits that the book names explicitly.

The manuscript is a construction draft. Executed tests, Linux experiments and live model evaluations support particular claims; they do not constitute a month of uptime or independent editorial acceptance. The phone transport has portable contract tests, while the live handset acceptance remains a separate observation. This status stays visible rather than being converted into a publication claim by a high mechanical score.

## The books beside our implementation

OpenClaw, NanoClaw and Hermes appear when their code illuminates a particular decision. Every finished comparison names a commit and distinguishes documented rationale from our interpretation. We do not infer that a project lacks a feature because a short inspection did not find it. The decisions organize the book; the projects are dated illustrations.

Sovereign Agent is the educational implementation. Zeocore is an optional path to maintained integrations in a separate environment. The [integration appendix](appendices/zeocore-interop-v2.md) demonstrates a real, bounded protocol connection without making it a prerequisite for understanding the chapters. Start with [the reader conventions](CONVENTIONS.md), then make Lucy's [first model call](ch01_first_model_call/README.md).
