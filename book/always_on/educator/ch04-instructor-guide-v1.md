# Chapter 4 instructor guide — Which remembered facts should enter the next request?

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT educator companion v1

## Learning outcomes

By the end, the student can implement the stated decision contract, explain a failing shortcut with a concrete counterexample, trace the related decision through the chapter runtime, and state the limits of the observed evidence. The complete chapter construction remains in [Remember across conversations](https://www.profrod.ai/book/ch04-memory); this lab isolates one decision for independent work and then reconnects it to that implementation.

## Preparation and classroom setup

Read the chapter and its checkpoint before teaching. Prerequisites: Chapter 3 transcripts; records with provenance and a character budget. Use the cumulative Python 3.14 environment and repository setup from the book conventions. Open `ch04-memory-class-v1.ipynb` in an existing notebook environment whose interpreter can import the book dependencies. The lab locates the checkout from the working directory or `SOVEREIGN_AGENT_REPO`; it checks the checkpoint SHA-256 `9acb4fc3d28fdd76cccb02ab9d2129fbaa2d7fa9da4727cab1f8fc26cbb31e2b` before executing it. It never installs dependencies for students. If the kernel is older or the checkpoint differs, correct the environment or use the matching lesson version; do not delete the guard.

If a Python 3.14 notebook kernel is unavailable, use the included standard-library runner from the repository root: `uv run --python 3.14 python book/always_on/educator/run_lesson_v1.py --chapter 4 --output /tmp/lucy-ch04-class.json`. The output path must be new. Read the notebook cells in an editor, implement `decide` there and rerun; the runner executes those saved cells and records submission results separately from the answer key. It does not install Jupyter or substitute another Python interpreter.

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

Lucy replaces morning delivery with afternoon delivery, then asks the agent to forget the preference. Should old operational reports also disappear? Can another session’s preference enter Lucy’s request?

Implement decide(case). Scan rows in supplied priority order, select only active rows for the requested session, retain key/value/source, and charge len(value) Unicode characters. Skip a row that would exceed budget and keep scanning. Return a list; do not mutate rows. This lesson budget counts characters, not tokens or bytes.

Do not answer immediately. Ask pairs to identify the authoritative inputs and the untrusted input, when present. Have one pair argue for the shortcut and another produce a concrete case against it. Require a reason that survives changing the fixture values.

## Answer key and case evidence

```python
def worked_decide(case):
    selected, used = [], 0
    for row in case["rows"]:
        if row["session"] != case["session"] or not row["active"]:
            continue
        size = len(row["value"])
        if used + size > case["budget"]:
            continue
        selected.append({key: row[key] for key in ("key", "value", "source")})
        used += size
    return selected
```

The notebook supplies 4 independent initial cases. Inspect their literal expected outcomes, not just the final assertion. Input mutation is a failure even if the returned value happens to match. The tempting shortcut is `lambda case: [{'key': r['key'], 'value': r['value'], 'source': r['source']} for r in case['rows']]`; its failing cases are printed separately. A student who merely pastes this answer still needs to explain the rejected case, implement the transfer, and trace the runtime.

## Runtime connection

checkpoints/ch04.py: ObservedModel.complete and main. Trace preferences → context → first_messages, and compare retained assistant_work rows.

Expected observations include: `Forgotten value in future context: False`, `Context reached the model: True`. These strings help locate the result; the checkpoint itself exercises the underlying behavior and assertions. Ask the student to identify the real state or tool result behind each observation. Printing the same words from a new stub would not meet the lab outcome.

## Transfer task and worked discussion

Add an over-budget first row and a short valid second row. Then run the Chapter 4 correction/forgetting experiment and inspect the exact messages passed to ObservedModel.

The short second row remains eligible; breaking instead of continuing loses it. In the runtime, the forgotten afternoon preference leaves future context while the old work record remains. That is selective context withdrawal, not erasure from every historical record.

For an additional oral challenge, change one boundary value from the submitted case and ask for the result without running it. Ask which input validation or persistence layer the small function assumes. This distinguishes understanding from memorizing the happy path.

## Misconception and remediation

Persistent memory is not automatically authoritative. Supplier preferences do not replace structured stock or order records.

If the student confuses a model assertion with runtime evidence, return to the exact trace above and label each value as input, request, local decision or independent observation. If the student gets the code right but cannot explain a boundary, have them write a failing counterexample first and then repair their explanation. If the transfer mutates the original fixture, copy it and rerun both cases; the earlier case must remain intact.

## Assessment and retained evidence

Score five dimensions from 0 to 2: prediction with reasoning; contract implementation including boundary cases; a traced runtime effect; an independent transfer case; honest explanation of what is and is not proved. Zero means missing or incorrect, one means partly correct with a concrete gap, and two means correct and explained using the submitted evidence. Suggested readiness threshold: 8/10, with two points required for the final evidence/limits dimension. A teacher may adapt the threshold and should record that choice.

Retain the student's original function, case output, transfer case, short trace, and exit ticket. Record separately whether the learner, instructor or automated gate executed the cumulative reference. Do not award construction credit from REFERENCE_CHECKPOINT_PASSED or WORKED_EXAMPLE_PASSED. These are scaffold checks. No score from this rubric establishes publisher acceptance or a measured classroom learning gain without actual learner work.

## Scope and next step

The exercise is a context selector, not a database or full retrieval algorithm. The cumulative code supplies persistence, correction and actual context assembly.

Homework: finish the corresponding manuscript construction, then submit one additional adversarial case absent from this notebook. Explain how its expected answer was obtained independently and which real boundary should enforce it. The next chapter extends the cumulative system; do not carry a classroom-only helper into production as an unreviewed replacement for its runtime counterpart.
