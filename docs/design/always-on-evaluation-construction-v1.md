**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** FINDING

# A passing grader must declare what it did not grade

The full overhaul remains active. Chapter12 constructs the authored cases,
scripted baseline and isolated evaluation loop. Its failure experiment preserves
correct tool requests while replacing1500 pence GBP with999999 pence GBP in the
answer. Existing named checks passed; the old report documented a prose-review
limit but the CLI's short passed result was easy to overread.

Report schema2 preserves passed as the named-check conjunction and adds explicit
acceptance REJECTED or REVIEW_REQUIRED, with explanation amounts, unsupported
claims and business usefulness ungraded. CLI evaluate exposes that status beside
the report path and digest. Each case records the actual loop terminal status,
which distinguishes an empty answer from other unsuccessful runs. Baseline
calculation time is measured independently over the supplied fixture and labeled
as excluding acquisition; it is not advertised as equivalent end-to-end latency.
Four new regressions cover wrong prose, empty replies, measured baseline and the
real CLI/report path. The existing operator-requested skill activation continues
using its declared case contract and configuration fence; no automatic prose
judge or silently expanded activation rule is introduced.

Two real local qwen3 reasoning-none temperature-zero runs used all8 existing
public cases twice. Without guidance6/16 passed named checks in46.2437seconds;
with the already-frozen opening procedure16/16 passed in63.1948seconds. The
latter used52 model calls and36 tool calls. No guidance was changed from those
outputs. The authored scripted baseline matched all expected quantities with
zero model calls. Both full schema1 reports from bff6622 are retained unchanged
and clearly identified as predating the additive schema2 fields. Repeated public
held-out fixtures are not represented as new blind tests or statistical proof.

The chapter checkpoint constructs three rejected adversarial model fixtures,
the explicit wrong-prose review requirement,16 successful offline case-runs and
an actual saved report with verified digest. Optional live mode uses the frozen
procedure and retains output when --output is supplied. Structural draft scores
and automatic case passes are not human publication acceptance.
