# Chapter 5 instructor guide — Can a procedure grant itself a new tool?

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT educator companion v1

## Learning outcomes

By the end, the student can implement the stated decision contract, explain a failing shortcut with a concrete counterexample, trace the related decision through the chapter runtime, and state the limits of the observed evidence. The complete chapter construction remains in [Reuse a tested opening procedure](https://www.profrod.ai/book/ch05-skills); this lab isolates one decision for independent work and then reconnects it to that implementation.

## Preparation and classroom setup

Read the chapter and its checkpoint before teaching. Prerequisites: Chapter 4 context; sets and the difference between guidance and permission. Use the cumulative Python 3.14 environment and repository setup from the book conventions. Open `ch05-skills-class-v1.ipynb` in an existing notebook environment whose interpreter can import the book dependencies. The lab locates the checkout from the working directory or `SOVEREIGN_AGENT_REPO`; it checks the checkpoint SHA-256 `e0f6a8a9228f5faf4f4b7a69dc4bb84f199d1e8e7f274b16922c8c9708bb3547` before executing it. It never installs dependencies for students. If the kernel is older or the checkpoint differs, correct the environment or use the matching lesson version; do not delete the guard.

If a Python 3.14 notebook kernel is unavailable, use the included standard-library runner from the repository root: `uv run --python 3.14 python book/always_on/educator/run_lesson_v1.py --chapter 5 --output /tmp/lucy-ch05-class.json`. The output path must be new. Read the notebook cells in an editor, implement `decide` there and rerun; the runner executes those saved cells and records submission results separately from the answer key. It does not install Jupyter or substitute another Python interpreter.

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

A skill requires list_stock and supplier_order. The runtime allows only list_stock. Should loading the file make supplier_order available?

Implement decide(case). Given skills with name, active and requires, return sorted names of active skills whose requirements are a subset of allowed. Empty requirements are permitted. Never alter allowed.

Do not answer immediately. Ask pairs to identify the authoritative inputs and the untrusted input, when present. Have one pair argue for the shortcut and another produce a concrete case against it. Require a reason that survives changing the fixture values.

## Answer key and case evidence

```python
def worked_decide(case):
    allowed = set(case["allowed"])
    return sorted(
        skill["name"]
        for skill in case["skills"]
        if skill["active"] and set(skill["requires"]) <= allowed
    )
```

The notebook supplies 4 independent initial cases. Inspect their literal expected outcomes, not just the final assertion. Input mutation is a failure even if the returned value happens to match. The tempting shortcut is `lambda case: sorted(s['name'] for s in case['skills'] if s['active'])`; its failing cases are printed separately. A student who merely pastes this answer still needs to explain the rejected case, implement the transfer, and trace the runtime.

## Runtime connection

checkpoints/ch05.py: stage_skill → activate_skill → skill_snapshot → context. Locate the Missing required tool observation.

Expected observations include: `Missing required tool excludes skill: True`, `Purchases: 0`. These strings help locate the result; the checkpoint itself exercises the underlying behavior and assertions. Ask the student to identify the real state or tool result behind each observation. Printing the same words from a new stub would not meet the lab outcome.

## Transfer task and worked discussion

Change a copy of opening-check-v1.toml to require an unavailable tool. Inspect both its staged row and the model context. Explain why registration, activation and eligibility are three distinct states.

A staged skill is retained but not automatically active. Evaluation guards activation. Even an active version is omitted when its requirements are not allowed; the runtime does not widen authority to satisfy it.

For an additional oral challenge, change one boundary value from the submitted case and ask for the result without running it. Ask which input validation or persistence layer the small function assumes. This distinguishes understanding from memorizing the happy path.

## Misconception and remediation

The model may request a tool named in prose, but a request does not add an executable capability.

If the student confuses a model assertion with runtime evidence, return to the exact trace above and label each value as input, request, local decision or independent observation. If the student gets the code right but cannot explain a boundary, have them write a failing counterexample first and then repair their explanation. If the transfer mutates the original fixture, copy it and rerun both cases; the earlier case must remain intact.

## Assessment and retained evidence

Score five dimensions from 0 to 2: prediction with reasoning; contract implementation including boundary cases; a traced runtime effect; an independent transfer case; honest explanation of what is and is not proved. Zero means missing or incorrect, one means partly correct with a concrete gap, and two means correct and explained using the submitted evidence. Suggested readiness threshold: 8/10, with two points required for the final evidence/limits dimension. A teacher may adapt the threshold and should record that choice.

Retain the student's original function, case output, transfer case, short trace, and exit ticket. Record separately whether the learner, instructor or automated gate executed the cumulative reference. Do not award construction credit from REFERENCE_CHECKPOINT_PASSED or WORKED_EXAMPLE_PASSED. These are scaffold checks. No score from this rubric establishes publisher acceptance or a measured classroom learning gain without actual learner work.

## Scope and next step

This function only filters eligible guidance. Candidate evaluation, durable versions, provenance and rollback are supplied by the cumulative implementation and revisited in Chapter 13.

Homework: finish the corresponding manuscript construction, then submit one additional adversarial case absent from this notebook. Explain how its expected answer was obtained independently and which real boundary should enforce it. The next chapter extends the cumulative system; do not carry a classroom-only helper into production as an unreviewed replacement for its runtime counterpart.
