**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

# Opening construction chapters

This checkpoint extends the first-call chapter into a three-chapter build. The full sixteen-chapter overhaul remains active. It does not replace the existing thirteen published chapters or their labs.

## Constructed artifacts

- Chapter 2 implements typed argument schemas, deterministic stock and price functions, an explicit registry, and the dispatcher. Twelve executable examples have twelve matching output pairs. Its failure experiments distinguish name authority, strict argument types, business rules, invocation ordering, and post-handler result refusal.
- Chapter 3 shows the owned loop, model-turn representation, transcript association, batch admission, monotonic deadlines, token and estimated-cost limits, and replay fixtures. Twelve executable examples have eleven matching output pairs. The cumulative loop retains the later persistence and ownership callbacks; the chapter identifies those later additions explicitly.
- Both chapters have standalone checkpoints using the same three-product fixture. The checkpoint uses this repository's own components whose implementation appears in the manuscript; no finished agent framework owns execution.
- The unchanged Prof Rod score instrument at `8511698f7f84643adef7f3973543256f5f76ca31` gives each draft 100. The receipts explicitly exclude exact-source synchronization, link checking, rendered review, and publication acceptance.

## Live evidence changed the checkpoint

The first live Chapter 3 run returned a completed stock description without invoking either draft tool. Clarifying the system instruction alone did not fix the second run. Stating the requested draft artifact directly in the user message produced both drafts in the next two samples.

All four transcripts are retained in `docs/evidence/always-on/ch03-live-construction-v1.json`, including the failures and exact prompt differences. The final checkpoint independently checks successful draft observations against authored SKU, quantity, price, and currency answers. It exits unsuccessfully when that evidence is absent even if the loop status is `COMPLETED`. A regression test also corrupts the second product's quantity so a correct vanilla result alone cannot pass.

This is evidence about the named fixture and four local samples, not proof of general language quality or a measured model reliability rate. Prompt clarification does not replace runtime authority or outcome verification.

## Verification and next work

`scripts/verify_always_on_v1.py` now reports three constructed drafts, thirteen planned chapters, thirty-four executable Python examples, and thirty-one matching output pairs. Its `--complete` contract still refuses publication acceptance.

Next draft: Chapter 9, the ambiguous supplier order, using the already implemented intent, reservation, receipt, and reconciliation path. Remaining implementation includes persistent stock conditions, receiving and account reconciliation, bounded delegation, and operational acceptance. Chapters 4–16, publisher proposal material, pinned comparison references, exact-source site migration, and rendered review remain required. PR 88 stays draft.
