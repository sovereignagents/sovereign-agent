# Chapter 1 follow-on — instructor guide for prompts and the harness

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT classroom companion v1

Use `ch01-prompts-and-harness-class-v1.ipynb` after students have spent thirty minutes with the first notebook. This is a 60-minute follow-on, with an optional live comparison inside the timebox. It is standalone Python 3.11 or newer, uses only the standard library and requires no account or package installation. Its shop is the same three-product fixture: vanilla needs six tubs, strawberry four and chocolate none. The draft total is 2600 pence GBP. Students may use Colab or an existing Jupyter environment; perform a classroom-machine rehearsal before relying on either.

The lesson separates three interventions. Prompt wording changes what the model is asked to do. Moving the same grounding text between user and system messages changes its declared instruction role, subject to the provider's support for that role. Python code determines which returned proposals can proceed and how many attempts may be made. Students should be able to point to each intervention in the displayed request or executing function.

## Preparation

Read the notebook through once and keep `RUN_LIVE = False` for the rehearsal. Restart and Run all; the authored fixtures should validate vanilla six and strawberry four, refuse the deliberately bad proposals, and leave purchases at zero. Preserve the original shop when trying the Lime exercise. Keep the worked answer hidden until students have predicted the new quantity and budget result.

A live comparison is optional. Students deliberately configure their existing compatible endpoint using `CLASS_BASE_URL`, `CLASS_MODEL` and, when required, `CLASS_API_KEY` through the environment or Colab secrets. Key presence alone does not enable calls. The notebook permits six attempts in one comparison: three prompt variants, twice each, holding the model and generation settings fixed. No free-tier availability or particular provider response is promised. A failed live attempt stays a failed live row; do not replace it with an authored success when comparing prompts.

## Sixty-minute sequence

| Minutes | Activity | Ask for |
| --- | --- | --- |
| 0–8 | Recover the first notebook's lesson | A claim that passed structural validation but was false |
| 8–18 | Inspect base, grounded-system and grounded-user requests | The exact text moved and what stayed fixed |
| 18–33 | Read and challenge `validate_draft` | A valid draft, wrong quantity, duplicate SKU and bool quantity |
| 33–43 | Challenge `Harness` with hostile text and failed calls | Why the third attempt is refused and why no purchase tool appears |
| 43–53 | Compare fixture rows or run the optional live experiment | Separate labels for fixtures, live successes and live failures |
| 53–60 | Lime transfer and exit ticket | Independent amount calculation and a justified policy change |

If live setup consumes more than five minutes, retain the fixture experiment and explicitly record that model quality was not measured. Keep the comparisons identical except for the intended prompt intervention. Do not let each pair change the model, temperature, stock and wording simultaneously and then attribute differences to system prompts.

## Prompts: questions and answers

Ask students to identify the output contract shared by all variants. Every variant requests the same structured draft fields. The grounding rule is added in one system variant and moved, unchanged, into a user variant. The same shop data remains in the user message. The role-placement comparison is therefore narrower than an uncontrolled rewrite of the whole request.

The model may use learned knowledge beyond the supplied text. The current authoritative stock and prices in this exercise nevertheless come from the shop fixture and Python price table, not a model's recollection. A system message may guide supported models more strongly; it does not mutate `allowed_actions`, the budget or the validator. A hostile supplier note that calls itself a system instruction remains document content in the request constructed here.

Ask: “If every fixture row passes, did the system prompt improve the model?” The answer is no. Those responses were authored to exercise control flow. Even the optional six live attempts offer only a small exploratory observation, with possible truncation or provider variation. Preserve each attempt's outcome, and avoid turning two successes into a general ranking.

## Harness: questions and answers

`validate_draft` checks exact root keys and operation, known unique SKUs, strict positive integer quantities equal to current need, completeness across shortages and the independently calculated estimate. Vanilla costs 6 × 250 = 1500 pence and strawberry costs 4 × 275 = 1100 pence. The default 3000-pence estimate limit admits their 2600-pence draft. The function has no supplier purchase capability.

A quantity of `True` must fail despite Python's bool/int relationship. Repeated SKUs must fail rather than hiding a duplicate in a dictionary conversion. Missing strawberry must fail even when the included vanilla draft is correct. A proposed `purchase` operation must fail regardless of prose claiming Lucy authorized it. Lowering the host estimate constraint to 2000 refuses the unchanged 2600-pence proposal.

A structurally valid explanation may still falsely claim delivery. The validator retains it under `model_explanation_unverified`; correct structured fields do not prove arbitrary prose. Ask students to submit that counterexample rather than claim all text is now safe.

`Harness` checks its allowance before calling the model transport and charges the attempt before processing its result. After two allowed calls, the third is refused without transport invocation. A failed call still consumes an attempt. Re-running a whole comparison constructs a new explicit experiment; the classroom object is not a durable daily budget across restarts. That limitation motivates later chapters.

## Transfer: Lime and a changed constraint

Add Lime only to a copied shop and price table: on_hand zero, target four, unit price200 pence. Lime needs four tubs and adds800 pence. The three shortages now total3400, so the original3000 limit makes a complete draft infeasible. The original two-product draft also fails because Lime is missing. Removing a required item to stay under budget violates this exercise's completeness contract.

Students should identify the conflict before changing anything. A recorded host policy change to3500 permits the complete3400-pence draft; a sentence in the prompt cannot make that change. The notebook provides this worked answer after the discussion. Other designs could support partial replenishment, but that would require a different explicit contract and new evaluation cases.

## Assessment, remediation and next chapter

Collect six short answers: what changed between prompt variants; which facts remained fixed; why fixture success is not model-quality evidence; which Python boundary rejected the hostile request; why a failed call used budget; and why Lime requires both a complete draft and a revised estimate allowance. Require the original and expanded fixtures to remain independently replayable.

Score five dimensions 0–2: controlled comparison, deterministic business arithmetic, capability/call-budget explanation, a concrete counterexample and the Lime transfer. Suggested readiness is8/10 with full marks for the boundary explanation. The rubric is a teaching recommendation, not a measured learning outcome. Record the student's actual evidence before marking readiness.

If students say the system prompt enforces permission, change only that prompt and re-run the same refused action. If they say all text is verified, use the false explanation with correct draft rows. If they treat a timeout as a free retry, inspect the attempt counter before and after failure. These observations prepare Chapter2's tool dispatcher and Chapter3's full model–tool loop; the single-response classroom harness is not yet that loop or a deployed always-on service.
