# Teach Chapter 1 through construction, repair and transfer

**Created:** 2026-09-09 · **Status:** DRAFT instructor edition v1

Use [Unit A](unit-a-first-grounded-brief-v1.md) before [Unit B](unit-b-prompt-and-harness-v1.md). The canonical Markdown and generated notebooks contain the same learner content. Solutions and holdouts are separate and must not be distributed with the student bundle.

## Learning evidence

By the end, a learner should be able to:

1. distinguish request guidance, response-envelope validation, deterministic business facts and external-effect evidence;
2. repair a naive response reader against malformed and incomplete envelopes;
3. trace the learner-owned reader into Lucy's connected morning brief;
4. explain what changes between prompt wording, message role and harness policy;
5. repair a naive draft validator without memorizing the visible products;
6. refuse a hostile proposal even when its text claims system priority or owner approval;
7. transfer the validator to a changed product set and budget.

Unit A saves `ch01-unit-a-handoff-v1.json`. Unit B verifies the snapshot before using it. Missing or stale handoffs stay visible. This file is evidence of continuity, not evidence that the learner understands the code.

## Suggested schedule

| Minutes | Activity | Evidence |
| --- | --- | --- |
| 0–12 | Predict stock needs and inspect request bytes | written quantities and boundary labels |
| 12–35 | Repair `read_brief` | visible cases plus explanation of one refusal |
| 35–50 | Connect and challenge a fluent lie | data-flow trace into `morning_brief` |
| 50–65 | Save and inspect the handoff | exact artifact and snapshot identity |
| 65–90 | Debrief or begin Unit B | revised prediction and remaining-limit statement |

Teach Unit B in a second 60–75 minute block. Reserve at least twenty minutes for the learner-owned validator and fifteen for the changed Lime case. Do not reveal the solution after the first visible failure; use the three progressive hints in order.

## Assessment

Score each row from 0–2. Require 8/10 and full marks on boundaries before the learner proceeds to a chapter with consequential tools.

| Criterion | Two-point evidence |
| --- | --- |
| Prediction and revision | records a prediction, observation and evidence-based revision |
| Construction | learner function passes visible cases without mutating input |
| Connection | traces the displayed result through the learner function into the cumulative object |
| Repair and transfer | passes the instructor holdout with the changed product set |
| Honest claim | distinguishes draft, validated structure and external receipt |

The hidden runner defeats a visible-case lookup by adding Lime and changing product order. It also tests malformed response containers and undeclared draft fields. Passing it is behavioral evidence for these cases, not a universal correctness proof.

## Worked solution notes

Unit A must inspect the response from the outside in. Accept only one `finish_reason="stop"` choice containing an assistant message, no tool request or refusal, and nonempty string content. The reader returns text; it does not certify the claims inside that text.

Unit B derives the required SKU set from shop records, checks uniqueness before any dictionary conversion, rejects booleans as quantities, validates exact keys, recalculates quantities and cost, and keeps the explanation labelled unverified. The original shop total is 2,600 pence. Adding four Lime tubs at 225 pence produces 3,500 pence, so the transfer must deliberately raise the host estimate limit to 4,000 rather than silently changing arithmetic.

The hostile note remains data. A model may follow it, but `validate_draft` refuses `action="purchase"` and the out-of-policy quantity. No purchase capability exists in this chapter.

## Classroom record

Record elapsed time to the first passing visible contract, hint level used, first successful connection, transfer result and the learner's explanation of the prompt/harness distinction. Preserve actual errors. Do not turn successful execution of the untouched student notebook into a learning claim: its starter is expected to report `NEEDS_WORK`.

