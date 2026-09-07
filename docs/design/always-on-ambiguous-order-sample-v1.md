**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

# Ambiguous-order sample and response boundary

The full overhaul remains active. Chapters 1–3 and 9 are now constructed drafts, with twelve chapters still planned. This is the requested sample sequence, not a complete manuscript or publication approval.

## Chapter 9 evidence

The chapter implements stable operation identity, an idempotent supplier ledger, exact receipt recording, send admission and reconciliation. It distinguishes conversation call IDs from effect IDs, revocation from recalling an admitted send, and supplier acceptance from physical delivery. Unknown outcomes retain spending reservations. An empty lookup without the provider guarantee cannot authorize retransmission.

Ten inline Python examples and eight output pairs pass. The standalone checkpoint starts the HTTP supplier in an independent process and database, loses the response after remote commit, inspects the supplier's one persisted order, reopens the agent ledger, reconciles the receipt, and confirms reserved/spent amounts of 0/1500. It explicitly does not describe reopening a database connection as a hard-killed worker; that belongs to Chapter 10.

The unchanged Prof Rod scoring instrument at `8511698f7f84643adef7f3973543256f5f76ca31` scores the chapter 100. The receipt excludes exact-source synchronization, link verification, rendered review and publisher acceptance. Chapter 3 also receives a pinned NanoClaw comparison that separates the authors' documented SDK rationale from our interpretation of its teaching trade-off. No claim of unique recovery capabilities or project-wide security superiority is made.

## A falsified response-parser assumption

Hypothesis: malformed provider message or usage objects can escape the adapter as `AttributeError`, bypassing the loop's sanitized `MODEL_FAILED` path. Direct evidence: loading the committed adapter from `ae67fe38d5892061276d33a6455f7bfb73632ec6` and supplying an HTTP 200 envelope with `message: []` raises `AttributeError`. The hypothesis would have been falsified by a sanitized `ModelError` from those same bytes; that did not occur.

The parser now requires an object envelope, exactly one object choice, an object message and usage record, a bounded tool-call array, and string-or-null content. Booleans and numeric content no longer become empty strings through truthiness coercion. Eleven malformed-envelope cases run through the real owned loop and require `MODEL_FAILED`; a valid single response still completes. The blind spot is semantic truth and provider billing correctness: this validation checks protocol shape and usage bounds, not the truth of the generated explanation.

## Remaining work

Run the full repository gate before commit and retain its receipt. Keep PR88 draft. Next implementation priorities are persistent stock conditions, receiving/account reconciliation, bounded delegation, active-skill evaluation alignment, and Linux deployment/acceptance. The remaining twelve chapters, publisher proposal, pinned comparison appendix, exact-source site integration, and rendered review are still required. An older restored backup remains paused until account-wide reconciliation can cover newer and late external effects.
