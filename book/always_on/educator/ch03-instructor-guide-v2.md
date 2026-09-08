# Chapter 3 instructor guide — When must the loop stop before another model call?

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT educator companion v2

Supersedes v1 for new classes. Use `ch03-agent-loop-class-v2.ipynb`. Preserve first attempts and the distributed v1 files. The book remains at profrod.ai/book.

## Why Lucy needs this lesson

Lucy loses the allowance accounting for failed attempts, so repeated failures look free.

The student should finish able to explain that consequence using an actual altered implementation, a retained observation and a repair. The ten-minute decision function is a warm-up. The central practical copies and changes `book/always_on/learner/ch03.py`; executing an untouched checkpoint is not completion of that practical.

## Prepare the actual experiment

Prerequisites: Chapter 2 tools; loops, counters and inclusive/exclusive boundaries. Use Python 3.14 with the book’s locked dependencies. The current educator index names the exact cohort commit, and the runtime experiment verifies SHA-256 `e17b034dff63cfab77af872e408fe1aee860decde9b0263081db9831f02a0840` before copying the target. Do not remove a mismatched-hash guard; locate the pinned files. Chapter 1 alone remains standalone standard-library Python 3.11 or newer.

One bounded Python subprocess per trial; temporary SQLite state; no paid model or channel call. No worker is killed. The probe subprocess has a 60-second ceiling. Three default trials run per notebook. This is an execution bound, not a promised classroom duration. Rehearse on the actual classroom machines and record observed time. The helper creates no server kernel and installs no dependencies. No paid provider, real Telegram account, real purchase or private Zeocore package is needed.

The optional whole-chapter checkpoint is a separate cell with RUN_FULL_CHECKPOINT=False. Its ceiling is 180 seconds. Read its process behavior before enabling it: learner/ch03.py: run_loop. Find exposure += and model_count += before model.complete, then inspect the paired assistant/tool transcript. The source probe and checkpoint differ in scope; retain their results under separate labels. Specifically, Chapter 10 and 16 checkpoints kill an actual local worker; Chapter 11 runs an MCP child but does not run containers by default; Chapter 15 does not install a service or reboot a host.

A subprocess is not a security sandbox for arbitrary Python. Only reviewed local code belongs in this exercise. The helper strips model/channel environment credentials from its child. It copies source without bytecode, runs from that copy, clears caches between mutations, records stdout/stderr before classifying failure, and checks the original source remains unchanged. Cleanup removes the temporary copy after evidence is saved.

## Ninety-minute teaching sequence

| Minutes | Work | Evidence retained |
| --- | --- | --- |
| 0–10 | Predict the warm-up and actual mutation | Expected result, business consequence and falsifying observation |
| 10–20 | Implement the narrow decision contract | Original code and visible-case results |
| 20–30 | Read the real target and probe; run baseline | Source line and actual data entering the decision |
| 30–45 | Apply supplied fault and explain output | Broken source fingerprint, stdout/stderr and observed fields |
| 45–65 | Student repairs copied source and traces effect | Student patch, rerun, file:line → result explanation |
| 65–80 | Change one constraint; independent transfer | Expected answer plus novel observed outcome |
| 80–90 | Reveal worked answer and collect exit ticket | Limits of evidence and teacher review |

Collect the first attempt before revealing the worked answer. Wrong predictions are useful if students revise them using evidence. If setup prevents a student executing the practical, record INCOMPLETE_SETUP and schedule completion; a teacher demonstration is not that student’s executed repair. Keep observed minutes distinct from this planned schedule.

## Opening question and decision contract

With two calls used from a two-call allowance, is one more retry free? If a failed call used an estimated five pence, should that exposure disappear?

Implement decide(case) over trusted nonnegative counters. Check in this order: used_calls >= max_calls → MODEL_CALL_LIMIT; spent + next_cost > budget → MODEL_COST_LIMIT; otherwise CALL. This is a pre-call decision; the caller must reserve the attempt before transport, including failed attempts.

The new visible suite has 5 cases. Expected values are literal authored examples. Input mutation fails even if the return value agrees. Unsupported returns such as sets or bytes produce a JSON-safe FAILED diagnostic, including the return type, and do not prevent later reference and worked evidence being retained. PARTIAL means some cases were left unimplemented; it is not a pass.

Visible-case lookup tables can pass this suite. Tell students this explicitly. Review their source and ask a new teacher-chosen case after the submission; do not advertise published cases as hidden or tamper-proof. Passing visible tests alone receives no runtime-repair credit.

## Real-code teacher answer key

Target: `book/always_on/learner/ch03.py:124`. The notebook prints surrounding lines so students can check this location against the pinned file.

Original decision:

```python
exposure += limits.estimated_call_pence
```

Supplied fault:

```python
exposure += 0
```

The independently authored expected baseline is `{"estimated_pence": 5, "model_calls": 1, "stop_reason": "MODEL_FAILED"}`. The expected broken result is `{"estimated_pence": 0, "model_calls": 1, "stop_reason": "MODEL_FAILED"}`. A broken trial marked PASS means the fault behaved as predicted; it does not mean the modified runtime is safe.

The attempt counter remains one while the estimate drops to zero. This is configured exposure, not an invoice or proof that the provider billed the failed call.

The actual probe imports this copied module, invokes its function, then prints fields from the returned tool result or retained database state. Read the complete probe in `runtime-experiments-v1.json` or `lab.probe`, and require the student to identify that data path. Printing the expected dictionary in a replacement stub fails this outcome.

The minimal worked repair restores the original marked fragment above. Students may implement an equivalent repair but must rerun the probe and explain the changed observation. Retain their source before creating the separate worked copy. The supplied answer never overwrites student_repair or student_source.

Trace submission fields are source_path, source_line, observation_key, observed_value and explanation. Choose one changed key from the expected dictionaries above. Mechanical validation checks that the location and value exist; STRUCTURE_VALID_TEACHER_REVIEW_REQUIRED means you must still judge the causal explanation. Award no trace credit for a copied location with no explanation of the function call and returned data.

## Warm-up worked answer

```python
def worked_decide(case):
    if case["used_calls"] >= case["max_calls"]:
        return "MODEL_CALL_LIMIT"
    if case["spent"] + case["next_cost"] > case["budget"]:
        return "MODEL_COST_LIMIT"
    return "CALL"
```

Two replay turns can produce all three tool calls but no final answer, so the loop ends MODEL_CALL_LIMIT. A first-call failure ends MODEL_FAILED with model_calls=1 and its configured estimated exposure retained. Three calls in the happy path produce COMPLETED; the prose alone cannot prove the drafts.

## Transfer and chapter-specific remediation

Run your own ReplayModel with two allowed calls, then a first-call ModelError. Retain the actual tool messages as well as counts.

If exposure is erased on failure, draw an attempt reservation before transport and put the ModelError after it. Ask the learner to explain the observed one attempt and five pence without pretending it is a provider invoice. In the integration transfer, two replay calls yield three tool results and no final answer; a first-call failure yields one call, zero tools and five estimated pence. Grade both saved observations.

For the oral transfer, choose fresh values that preserve the same invariant but are absent from CASES. Ask for the expected result before execution and retain both. For Chapters 3, 5, 8 and 13, distinguish the pure-function transfer from the runtime extension; ReplayModel objects, staged files and database transactions do not belong in TRANSFER_CASES. Chapter 3 provides an explicit student-owned model/limits integration cell and retains stop reason, attempted calls, configured exposure and actual tool messages.

## Assessment, evidence and observed pilot

Score five dimensions 0–2: justified prediction; contract code with a novel case; independently repaired real code; causal file:line → output trace; explanation of scope and remaining uncertainty. Zero is missing/incorrect, one needs a specific correction, two is supported by retained evidence. Suggested readiness threshold is 8/10, requiring full credit for the repair and evidence limits. Record your actual rubric choice.

Keep first-attempt code, visible-case results, transfer cases, all three trial records, the student source patch, trace and exit ticket. Record whether each run was performed by the student, instructor or automation. A worked answer, a reference PASS, or a template lookup is not student construction. Review whether the patch repairs the function for a second case instead of special-casing this fixture.

Use `classroom-pilot-record-v1.md` for the real pilot. Record anonymous learner ID, environment/cohort SHA, start/finish times, setup errors, first-attempt failure, assistance, repair outcome and transfer explanation. Leave unobserved fields blank. The proposed 90 minutes and automated checks are not evidence of classroom completion, learning gain, human render approval or Manning acceptance.

## Scope after this lesson

The small admission function omits time, token, context and tool limits. Inspect and build those in the chapter loop. Replay tests control flow, not an LLM decision.

Continue with the next manuscript chapter after completing this practical. Preserve the copied experiment as evidence; never install its deliberately broken source into the working agent.
