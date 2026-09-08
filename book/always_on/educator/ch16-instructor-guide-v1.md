# Chapter 16 instructor guide — Can the daily report be reconciled against independent receipts?

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT educator companion v1

## Learning outcomes

By the end, the student can implement the stated decision contract, explain a failing shortcut with a concrete counterexample, trace the related decision through the chapter runtime, and state the limits of the observed evidence. The complete chapter construction remains in [Lucy leaves the shop for a day](https://www.profrod.ai/book/ch16-acceptance); this lab isolates one decision for independent work and then reconnects it to that implementation.

## Preparation and classroom setup

Read the chapter and its checkpoint before teaching. Prerequisites: All preceding chapters; identity, money and evidence sources. Use the cumulative Python 3.14 environment and repository setup from the book conventions. Open `ch16-acceptance-class-v1.ipynb` in an existing notebook environment whose interpreter can import the book dependencies. The lab locates the checkout from the working directory or `SOVEREIGN_AGENT_REPO`; it checks the checkpoint SHA-256 `2145f13550a2c9d6a662355ab95f816c94a91d4aa104f773d1461f89093fa0aa` before executing it. It never installs dependencies for students. If the kernel is older or the checkpoint differs, correct the environment or use the matching lesson version; do not delete the guard.

If a Python 3.14 notebook kernel is unavailable, use the included standard-library runner from the repository root: `uv run --python 3.14 python book/always_on/educator/run_lesson_v1.py --chapter 16 --output /tmp/lucy-ch16-class.json`. The output path must be new. Read the notebook cells in an editor, implement `decide` there and rerun; the runner executes those saved cells and records submission results separately from the answer key. It does not install Jupyter or substitute another Python interpreter.

Run the notebook from a restarted kernel on the classroom machines before class. Use no model/channel credentials. Default checkpoints use authored model responses and temporary local state. They may start local supplier/worker processes; Chapter 11 uses a local MCP child. Container isolation, live Telegram, real provider behavior and host installation remain separately labelled chapter procedures. A subprocess failure is evidence to inspect, not permission to replace its result with a success fixture.

Keep the solution cells below the students' first attempt. Ask them to save or submit that attempt before revealing the answer. A default Run all intentionally reports NOT_SUBMITTED for their empty function while running the worked example separately. This makes the handout executable without awarding automatic credit. The teacher's assessment must not count the answer-key status as the learner's score.

## Ninety-minute sequence

| Minutes | Action | Evidence to collect |
| --- | --- | --- |
| 0–10 | Predict before any code | Written outcome and a falsifying observation |
| 10–35 | Implement `decide` against the contract | Original function and named case results |
| 35–55 | Read the named runtime path, then run the checkpoint | Input → decision → observed effect trace |
| 55–75 | Add and explain the transfer case | Independent expected answer and changed constraint |
| 75–85 | Reveal solution and break the shortcut | The precise case that rejects the shortcut |
| 85–90 | Exit ticket | Scope of evidence and one remaining uncertainty |

If setup consumes the opening time, demonstrate the reference checkpoint on the prepared instructor machine and record that students did not execute it themselves. Preserve the construction and prediction blocks; schedule the missing environment work explicitly. This is a documented observation gap, not a completed practical.

## Opening question and contract

Lucy’s report says two orders total2600 pence. If local orders total2600 but refer to different operation IDs, has reconciliation succeeded?

Implement decide(case). local and supplier are lists of normalized operation/amount records. Refuse duplicate IDs in either list. Return RECONCILED only if their ID→amount dictionaries match exactly and summed supplier amounts equal reported_pence; otherwise MISMATCH. Empty lists with reported zero are valid. This checks purchases only, not the whole day.

Do not answer immediately. Ask pairs to identify the authoritative inputs and the untrusted input, when present. Have one pair argue for the shortcut and another produce a concrete case against it. Require a reason that survives changing the fixture values.

## Answer key and case evidence

```python
def worked_decide(case):
    local = {row["operation"]: row["amount"] for row in case["local"]}
    supplier = {row["operation"]: row["amount"] for row in case["supplier"]}
    if len(local) != len(case["local"]) or len(supplier) != len(case["supplier"]):
        return "MISMATCH"
    matches = local == supplier and sum(supplier.values()) == case["reported_pence"]
    return "RECONCILED" if matches else "MISMATCH"
```

The notebook supplies 5 independent initial cases. Inspect their literal expected outcomes, not just the final assertion. Input mutation is a failure even if the returned value happens to match. The tempting shortcut is `lambda case: 'RECONCILED' if sum(r['amount'] for r in case['local']) == case['reported_pence'] else 'MISMATCH'`; its failing cases are printed separately. A student who merely pastes this answer still needs to explain the rejected case, implement the transfer, and trace the runtime.

## Runtime connection

checkpoints/ch16.py: day. Trace independent supplier SQLite rows → operating_report → CLI report, plus SIGKILL and the duplicate delivery receipt.

Expected observations include: `Independent supplier: 2 orders, 2600 pence`. These strings help locate the result; the checkpoint itself exercises the underlying behavior and assertions. Ask the student to identify the real state or tool result behind each observation. Printing the same words from a new stub would not meet the lab outcome.

## Transfer task and worked discussion

Keep the total at2600 but swap individual order amounts. Add a missing supplier row. Then identify evidence for the killed worker, pending strawberry delivery and completed catering quote in the actual day report.

Both corruptions are MISMATCH. The accelerated day has two independently recorded supplier orders for2600, one delivered and one confirmed, vanilla on_hand8, strawberry on_hand1/on_order4, no pending work and one completed research quote. It is not evidence of real Telegram delivery or a full day of uptime.

For an additional oral challenge, change one boundary value from the submitted case and ask for the result without running it. Ask which input validation or persistence layer the small function assumes. This distinguishes understanding from memorizing the happy path.

## Misconception and remediation

A fluent daily report can agree with itself while disagreeing with the world. Match identities and individual amounts, not only totals.

If the student confuses a model assertion with runtime evidence, return to the exact trace above and label each value as input, request, local decision or independent observation. If the student gets the code right but cannot explain a boundary, have them write a failing counterexample first and then repair their explanation. If the transfer mutates the original fixture, copy it and rerun both cases; the earlier case must remain intact.

## Assessment and retained evidence

Score five dimensions from 0 to 2: prediction with reasoning; contract implementation including boundary cases; a traced runtime effect; an independent transfer case; honest explanation of what is and is not proved. Zero means missing or incorrect, one means partly correct with a concrete gap, and two means correct and explained using the submitted evidence. Suggested readiness threshold: 8/10, with two points required for the final evidence/limits dimension. A teacher may adapt the threshold and should record that choice.

Retain the student's original function, case output, transfer case, short trace, and exit ticket. Record separately whether the learner, instructor or automated gate executed the cumulative reference. Do not award construction credit from REFERENCE_CHECKPOINT_PASSED or WORKED_EXAMPLE_PASSED. These are scaffold checks. No score from this rubric establishes publisher acceptance or a measured classroom learning gain without actual learner work.

## Scope and next step

The function audits only a normalized order subset. Physical stock, approvals, model usage, pending work and human-readable claims require their own evidence in the integrated chapter.

Homework: finish the corresponding manuscript construction, then submit one additional adversarial case absent from this notebook. Explain how its expected answer was obtained independently and which real boundary should enforce it. The next chapter extends the cumulative system; do not carry a classroom-only helper into production as an unreviewed replacement for its runtime counterpart.
