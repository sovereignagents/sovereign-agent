# Teach Chapter 3 through bounded admission and real-source repair

**Created:** 2026-09-09 · **Status:** DRAFT instructor edition v1

Unit A constructs the admission boundary and connects it to a small model–tool–observation loop using the actual Chapter 2 dispatcher. Unit B then mutates a temporary copy of `book/always_on/learner/ch03.py` and repairs the actual failed-call exposure accounting.

## Learning evidence

A learner should be able to:

1. predict assistant/tool transcript order and trace a tool-call identifier;
2. implement call-count and cost admission before the next provider attempt;
3. explain why a failed admitted call remains counted;
4. distinguish final prose from retained tool evidence;
5. reproduce a real-source accounting fault, repair it, and retain the before/after observation;
6. explain repeated call identifiers and provider failure as distinct stop reasons;
7. transfer the repair to an unseen configured estimate.

## Schedule

Use 75–90 minutes for Unit A and 60–75 for Unit B. Do not spend class time on a live model. The replay turns make control flow reproducible; a later optional experiment can compare live model decisions without changing the loop exercise.

Require a prediction before each admission row, the successful replay, the broken exposure probe, the repeated identifier, and the failed provider. Use hints in order. Reveal the solution only after the learner retains an attempt and a falsifiable explanation.

## Assessment

| Criterion | Full evidence |
| --- | --- |
| Admission | novel call/cost cases pass without input mutation |
| Connection | the learner decision controls every attempted model turn in the notebook loop |
| Transcript | request and observation identifiers are traced; prose is not treated as draft evidence |
| Repair | the real copied source returns the baseline result after mutation |
| Transfer | the seven-pence hidden probe retains one call and seven pence after failure |

Suggested progression is 8/10 with full marks on admission and failure accounting. Notebook execution alone is not a pass: the student starter deliberately reports `NEEDS_WORK`.

## Worked answers

Call-limit precedence makes an exhausted call allowance stop even when money is also exhausted. Equality at the money boundary is allowed. The loop increments the attempt and configured exposure before calling the provider, so an exception returns `MODEL_FAILED`, one attempted call, and the admitted exposure.

The real-source mutation removes only exposure accounting. It does not change `model_count += 1`, so the pair of observations isolates the fault. The correct fragment is `exposure += limits.estimated_call_pence`. The hidden check changes five pence to seven; a printed constant or visible-output special case fails.

The replay fixture proves the loop/dispatcher control flow. It does not prove a model would select those calls. The Chapter 2 dispatcher validates and computes drafts; the final explanation remains separate from its tool observations.

## Operational boundary

`RuntimeLab` copies reviewed source and runs a bounded local subprocess. It is not isolation for arbitrary code. The student should inspect the probe before running it. No credential, network call, supplier process, purchase, or hard kill is used in Chapter 3.

