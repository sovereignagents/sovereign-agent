# From completed loops to measured shop behavior

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

This construction record advances the issue 603 review repairs without claiming the whole overhaul is complete. It follows `always-on-implementation-review-v2.md` and preserves both the old thirteen-chapter curriculum and the new sixteen-chapter contract.

## Live failures and the resulting changes

The local Ollama 0.32.5 / Qwen3 path is now configured explicitly with `reasoning_effort=none` in the teaching CLI. The reusable HTTP adapter leaves the field unset unless requested. Other provider configurations can select `provider-default`. The option is supported by the [Ollama compatibility reference](https://docs.ollama.com/api/openai-compatibility); it is a tested local teaching choice, not a universal claim about model quality.

A live suite initially passed only two of six cases. It exposed skipped draft creation, wrong replenishment quantities and ordering a product already at threshold. The first run's currency error had already led to explicit GBP/pence tool fields. Fluent final text and a completed protocol exchange did not establish correct shop behavior.

The stock tool now calculates `needed` deterministically from physical, reserved and incoming quantities. Draft calculation refuses a quantity that differs from that need. The reference order-proposal handler invokes the same calculation before creating a durable proposal. A local opening-check skill tells the model to create each positive draft through the tool and report the resulting GBP amounts. This changes both the business tool and the procedure; the observed improvement cannot be attributed to the skill alone.

The six used cases remain development/regression evidence. Two fresh cases were added after the skill was frozen. A live evaluation of all eight cases, repeated twice, passed the declared checks: completed loop, expected draft quantities, stock lookup, allowed operations, no tool errors, currency labels, no purchases, and agreement of an independent scripted baseline with authored answers. The sixteen runs used 52 model calls, 36 tools and 1496 output tokens, taking approximately 64 seconds in total on this host. Zero configured estimated monetary cost does not mean free electricity or a guarantee about hosted-model invoices.

Raw transcripts and outcomes are retained in `docs/evidence/always-on/evaluation-development-before-v1.json` and `evaluation-candidate-v1.json`. The initial report's former held-out labels describe its first use; those cases were subsequently promoted to regression cases. The initial construction report was not captured at a dedicated source commit and must not be presented as a fully pinned benchmark. The successful report records adapter/model/settings and the exact skill digest. Its checks do not prove every natural-language claim or generalize beyond the tested conditions.

## Controlled changes and tool integration

Operator actions stage an immutable local skill, evaluate it against the scenario suite, retain the report with restricted file permissions, and activate it only when every required case passes. Failed candidates leave the active version unchanged. Rollback selects a previously activated version and reevaluates it; versions and activation history remain available. The offline model tests this control flow but does not evaluate natural-language skill quality.

MCP catalog lookup and the container Python report tool are explicitly enabled by the operator. Both run through the ordinary dispatcher and loop. The MCP integration test launches the actual local server and observes its catalog. A live container integration test changes SQLite stock to 123 and verifies that generated code receives and reports 123 through the mounted snapshot, followed by confirmed container removal. Discovery or model text does not enable either edge.

## Opening chapter and migration gate

Chapter 1 is drafted under `book/always_on/ch01_first_model_call/README.md`, with a standalone standard-library checkpoint. Ten Python examples execute and eight expected outputs match. An actual local model call also ran. The chapter teaches the difference between a response fixture, a live response, a valid envelope, a factual claim and a future external-effect receipt. It does not begin by importing a finished agent loop.

`book/always_on/BOOK.json` preserves sixteen stable lesson identities. Fifteen chapters remain planned. The new construction gate runs existing drafts and reports exactly how many it checked; `--complete` refuses planned or unready chapters. It does not weaken the old curriculum gates or establish publication acceptance. The root publication manifest and site remain on the preserved edition until migration is complete.

Remaining work includes Chapters 2–16, independent publisher-facing review, the exact-source site bridge and full publication gates, stock-event wiring, bounded delegation, receipt/receiving accounting, restore reconciliation and reauthorization, operational proof and the integrated day. No step here reduces that scope.
