# Teach Chapter 1: a first model call Lucy can question

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT classroom companion v1

Use [the standalone Chapter 1 notebook](ch01-first-model-call-class-v1.ipynb). It needs Python 3.11 or newer and the standard library. Upload the file to Colab, or open it in an existing Jupyter environment. No installation, model account, purchasing account or API key is needed for the complete offline lesson. The main book uses Python 3.14; this standalone introduction deliberately uses syntax available in 3.11. Check the interpreter version printed in the first cell instead of assuming a hosted service's current version.

This is the educator companion to [Chapter 1](https://www.profrod.ai/book/ch01-first-model-call), published with the book at profrod.ai/book. The notebook is an executable teaching artifact, not a claim of independent classroom validation. Its optional live experiment is off by default. A model call is different evidence from replaying a fixture; neither establishes that Lucy placed an order.

## Prepare in five minutes

1. Download the notebook, open it, restart the kernel/runtime, and run all cells. Expect seven envelope rejections, a detected claimed purchase, a missed false claim, an explicitly labelled offline fallback, a stale-snapshot refusal, and a missing Lime warning. The final original shop still has three products. Repeating Run all must not append products or send a live call.
2. Keep `RUN_LIVE = False`. If you already have a working compatible endpoint, prepare it separately before class. A student's laptop's localhost is not the hosted notebook's localhost. Do not ask students to create accounts during the mandatory lesson.
3. Give each student a prediction sheet with columns: experiment, prediction, observation, explanation, remaining uncertainty. A notebook Markdown cell or plain paper is sufficient. Work in pairs if typing or account setup would consume the lesson.
4. Keep the original notebook available so a learner can restart after experimenting. Save working copies under another filename. Do not submit notebook files containing keys, private endpoint addresses or live personal/business data.

## Outcomes and boundaries

Students already know Python functions, dictionaries and lists; spend the first ten minutes diagnosing that prerequisite. They should finish able to trace shop data into the request, explain each envelope refusal, demonstrate a false negative in a content checker, and detect a changed snapshot before presenting its draft for review.

The central lesson is **a claim requires evidence appropriate to that claim**. The model has learned knowledge, but it does not observe Lucy's current stock beyond supplied observations. “The model knows nothing except this prompt” is inaccurate. Likewise, an empty heuristic warning list cannot mean “the answer may be believed.” Use the missed lie to prevent that misconception from becoming classroom doctrine.

`read_brief` proves a limited response shape. `check_brief` is a warning heuristic with known false negatives and false positives. `stock_facts` calculates authoritative quantities for this authored fixture. `review_brief` correlates the review with unchanged local snapshot content and returns `NEEDS_FACTUAL_REVIEW`; it never authorizes an order. This separation is the outcome to assess, not whether students can recite runtime terminology.

## Ninety-minute lesson

| Minutes | Activity and teacher prompt | Expected evidence | If students struggle |
| --- | --- | --- | --- |
| 0–10 | Establish roles and stock. Ask “How many vanilla tubs are needed, and why?” Students write all three quantities before running. | Chocolate 0, strawberry 4, vanilla 6. Exactly at target needs zero. | Compute one subtraction together, then ask a different student to do strawberry. Explain SKU as stable identity. |
| 10–20 | Print the complete request. Ask students to locate currency, stock and the instruction prohibiting purchase claims. | Serialized JSON contains GBP and all three products. It contains no supplier receipt. | Compare the Python dictionary with the user-message string side by side. Do not move to prompts until students find the data. |
| 20–35 | Predict all seven malformed-envelope outcomes. Ask “Which check would reject a non-object choice?” | All seven raise ValueError; no AttributeError, guessed text or partial success. | Trace one guard at a time. The tool-request case belongs to a future dispatcher, not this reader. |
| 35–55 | Run the claimed purchase, then `MISSED_LIE`, then the negated action. Ask “What claim can this checker actually establish?” | The purchase phrase is flagged; incorrect stock numbers and a paraphrased purchase pass; a negated action is falsely flagged. | Stop anyone equating no flags with truth. Compare 200 with the authoritative count 2. Discuss why adding one phrase cannot validate all English. |
| 55–75 | Optional live experiment, or offline failure diagnosis. Keep a hard twenty-minute timebox. | Every trial records `mode`; failure is printed before fixture fallback. Three live trials, if enabled, have separate factual reviews. | If setup takes five minutes, use the failure drill and discuss what it proves. No student loses credit for lacking an endpoint. |
| 75–85 | Build a request, change vanilla to 9, inspect the old bytes, and attempt review. | Old serialized count remains 2; snapshot comparison raises ValueError; original SHOP is unchanged. | Draw the two dictionaries and one string. Ask what operation would update the already-created string. |
| 85–90 | Lime transfer task and exit ticket. | Four products in the copied shop, three in original; needed Lime=4; old response omits Lime. | Identify Lime by SKU, not a memorized list position. Assign the full written explanation as homework if needed. |

Require a written prediction before running each experiment. Discuss mismatches without grading a wrong prediction as failure. Grade whether the learner can revise the explanation using the observed evidence. The notebook is the working surface; a diagram can help explain a copy or a boundary, but does not replace examining values.

## Optional live experiment and honest fallback

The notebook requires a deliberate `RUN_LIVE = True`, `CLASS_BASE_URL`, and `CLASS_MODEL`. An optional `CLASS_API_KEY` comes from a Colab secret or environment variable. It does not assume a particular provider offers a free account or a particular model today. Use a compatible endpoint already available to the class. The main manuscript documents one local Ollama path.

The transport has a socket-operation timeout and a response byte ceiling. A slow-drip response can outlast the nominal socket timeout, so do not describe it as a total wall-clock deadline. Chapter 3 develops the stronger transport boundary. Remote plain HTTP and credentials/query strings in the base URL are refused. Error details are withheld; do not print exception bodies or keys for diagnosis in a shared room.

Run three explicit live trials only if setup is already working. Record each mode, generated text, warning list and manual check against the fixture. Temperature zero does not guarantee either identical or different output. An output limit of 20 may produce a length-limited response; record the actual `finish_reason`, rather than promising it must be `length`. A provider failure, malformed response or truncation takes the labelled fixture fallback. That keeps the lesson moving but leaves live acceptance unproved.

For an entirely offline class, use `unavailable` to simulate transport failure and the `truncated` envelope to simulate a length stop. Students can fully demonstrate those control-flow properties without testing a real provider. Exit tickets must identify that difference.

## Answer key and worked transfer

The shop calculation is `max(0, reorder_point - on_hand)`. Vanilla needs `8 - 2 = 6`, strawberry `5 - 1 = 4`, chocolate `max(0, 6 - 12) = 0`. At equality the difference is zero. There is no stock reservation, incoming order or delivery in this first fixture.

The seven failures are: the envelope is not an object; choices are missing; the choice is not an object; there are two choices; generation reports a length limit; a tool call requires a dispatcher; the text is empty. Two failures may reach the same guard. The supplied earlier runbook's claim that each must have a unique reason was unnecessary. The desired property is refusal with a relevant reason.

`LYING_RESPONSE` is structurally valid. The warning detects its exact purchase phrase but cannot prove an external effect. `MISSED_LIE` mentions both low product names while asserting wrong quantities and a paraphrased purchase, so it exposes the warning's false negative. `NEGATED_ACTION` exposes a false positive. No amount of counting passing warning checks turns them into complete language understanding. Lucy's dependable stock display can use deterministic `stock_facts`; model prose remains a separately labelled draft.

A snapshot hash compares serialized content at two instants. It does not authenticate model output, verify arbitrary prose, freeze the world, detect a change followed by a return to the same content, or guarantee that the stock remains unchanged after the check. The returned status remains `NEEDS_FACTUAL_REVIEW`. A tool can obtain a newer observation; an action boundary must still revalidate the relevant records later.

For the Lime assertion, students can add this independently justified expectation:

```python
lime = next(row for row in stock_facts(expanded_shop) if row[0] == "SKU-LIME")
assert lime == ("SKU-LIME", 0, 4)
assert "omits low product Lime" in check_brief(read_brief(OFFLINE_RESPONSE), expanded_shop)
assert len(SHOP["products"]) == 3
```

To challenge the snapshot experiment further, change only chocolate's count and expect refusal; then change it back and explain why the content hash matches again. This is a useful limitation experiment, not evidence that the hash function is broken.

To repair the missed-lie problem, a learner may propose structured stock assertions checked against SKU/count/needed fields, or a deterministic displayed summary with separate unverified model prose. Accept either with a concrete counterexample and scope statement. Do not award full marks to a growing blacklist advertised as complete truth verification.

## Assessment rubric

Collect the prediction sheet, one new malformed envelope, the missed-lie explanation, the stale-snapshot result and the Lime assertion. Score each row 0–2: 0 absent or unsupported, 1 partly correct with missing evidence, 2 correct with a specific observation and limitation.

| Criterion | Evidence for 2 points |
| --- | --- |
| Data flow | Locates the serialized values and computes needed quantities, including equality. |
| Structural validation | Supplies a new malformed case and explains the relevant guard without accepting partial text. |
| Business truth | Demonstrates a false negative and explains why no warning is not proof. |
| Time and evidence | Explains the unchanged old bytes, detects another product's changed snapshot and names a hash limitation. |
| Transfer and honest reporting | Asserts Lime by identity, preserves the fixture, and labels live versus offline evidence accurately. |

Suggested progression threshold: 8/10, with full marks in business truth before moving to consequential actions. This is an instructor recommendation, not a mechanically enforced publisher score. Offer remediation: compare `MISSED_LIE` to `stock_facts` aloud, then have the learner invent a second false claim. Assess the revised reasoning.

## Homework and next lesson

Have students design a small structured stock assertion such as `{sku, on_hand, needed}` and write one valid case and two counterexamples against the shop table. Do not ask them to validate unrestricted prose with another model. At the next lesson, use this to motivate typed tool arguments and deterministic calculations. Chapter 2 adds those tools; Chapter 3 builds the loop. No knowledge of leases, work queues or multi-agent terminology is required to complete this lesson.

## Provenance and validation limits

This corrected companion develops the notebook and runbook supplied in [issue 603](https://github.com/rodriveracom/org-zeroemployeeorg/issues/603#issuecomment-5585328911). The external files remain review inputs. Corrections include the checker limitation, safe non-object envelope handling, explicit live opt-in, actual labelled fallback, full request display, copied fixtures for replay and precise snapshot claims. Offline execution and adversarial regression checks support the code paths; a hosted Colab session, real provider run and human classroom observation are separate evidence.
