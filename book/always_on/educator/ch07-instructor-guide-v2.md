# Chapter 7 instructor guide — What should happen to missed scheduled runs?

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT educator companion v2

Supersedes v1 for new classes. Use `ch07-scheduling-class-v2.ipynb`. Preserve first attempts and the distributed v1 files. The book remains at profrod.ai/book.

## Why Lucy needs this lesson

A late wake creates repeated stale briefs instead of one current brief, consuming Lucy’s request allowance.

The student should finish able to explain that consequence using an actual altered implementation, a retained observation and a repair. The ten-minute decision function is a warm-up. The central practical copies and changes `src/sovereign_agent/assistant_work.py`; executing an untouched checkpoint is not completion of that practical.

## Prepare the actual experiment

Prerequisites: Chapter 6 durable intake; integer division and explicit observed time. Use Python 3.14 with the book’s locked dependencies. The current educator index names the exact cohort commit, and the runtime experiment verifies SHA-256 `b359e33e95ea475b492935f743cd7d6e59232d2b8507cc4b09806ab1572752e9` before copying the target. Do not remove a mismatched-hash guard; locate the pinned files. Chapter 1 alone remains standalone standard-library Python 3.11 or newer.

One bounded Python subprocess per trial; temporary SQLite state; no paid model or channel call. No worker is killed. The probe subprocess has a 60-second ceiling. Three default trials run per notebook. This is an execution bound, not a promised classroom duration. Rehearse on the actual classroom machines and record observed time. The helper creates no server kernel and installs no dependencies. No paid provider, real Telegram account, real purchase or private Zeocore package is needed.

The optional whole-chapter checkpoint is a separate cell with RUN_FULL_CHECKPOINT=False. Its ceiling is 180 seconds. Read its process behavior before enabling it: checkpoints/ch07.py: main. Trace tick, scan, persisted generation, and the agent serve child without a prompt argument. The source probe and checkpoint differ in scope; retain their results under separate labels. Specifically, Chapter 10 and 16 checkpoints kill an actual local worker; Chapter 11 runs an MCP child but does not run containers by default; Chapter 15 does not install a service or reboot a host.

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

A job is due at 100, repeats every ten seconds, and is observed at 139. How many work records should a coalescing policy create, how many runs were skipped, and when is the next due time?

Implement decide(case) for integer due, now and positive interval. If paused or now < due, return [0,0,due]. Otherwise return [1, skipped, next_due] where skipped=(now-due)//interval and next_due=due+(skipped+1)*interval. One work item represents the latest coalesced wake. No wall-clock reads inside the function.

The new visible suite has 5 cases. Expected values are literal authored examples. Input mutation fails even if the return value agrees. Unsupported returns such as sets or bytes produce a JSON-safe FAILED diagnostic, including the return type, and do not prevent later reference and worked evidence being retained. PARTIAL means some cases were left unimplemented; it is not a pass.

Visible-case lookup tables can pass this suite. Tell students this explicitly. Review their source and ask a new teacher-chosen case after the submission; do not advertise published cases as hidden or tamper-proof. Passing visible tests alone receives no runtime-repair credit.

## Real-code teacher answer key

Target: `src/sovereign_agent/assistant_work.py:261`. The notebook prints surrounding lines so students can check this location against the pinned file.

Original decision:

```python
next_due = row["next_due"] + (skipped + 1) * row["interval_seconds"]
```

Supplied fault:

```python
next_due = row["next_due"] + row["interval_seconds"]
```

The independently authored expected baseline is `{"work_per_pass": [1, 0, 0, 0], "work_count": 1}`. The expected broken result is `{"work_per_pass": [1, 1, 1, 1], "work_count": 4}`. A broken trial marked PASS means the fault behaved as predicted; it does not mean the modified runtime is safe.

Both versions eventually reach next_due=140. Only the sequence of durable work counts exposes the backlog; checking the final due time alone misses it.

The actual probe imports this copied module, invokes its function, then prints fields from the returned tool result or retained database state. Read the complete probe in `runtime-experiments-v1.json` or `lab.probe`, and require the student to identify that data path. Printing the expected dictionary in a replacement stub fails this outcome.

The minimal worked repair restores the original marked fragment above. Students may implement an equivalent repair but must rerun the probe and explain the changed observation. Retain their source before creating the separate worked copy. The supplied answer never overwrites student_repair or student_source.

Trace submission fields are source_path, source_line, observation_key, observed_value and explanation. Choose one changed key from the expected dictionaries above. Mechanical validation checks that the location and value exist; STRUCTURE_VALID_TEACHER_REVIEW_REQUIRED means you must still judge the causal explanation. Award no trace credit for a copied location with no explanation of the function call and returned data.

## Warm-up worked answer

```python
def worked_decide(case):
    due, now, interval = case["due"], case["now"], case["interval"]
    if case["paused"] or now < due:
        return [0, 0, due]
    skipped = (now - due) // interval
    return [1, skipped, due + (skipped + 1) * interval]
```

The second pass at 139 returns [0,0,140]. Stock conditions use episodes and rearming, not the clock’s coalescing count. The real child process discovers the second episode from durable state, drafts seven vanilla tubs for 1750 pence and purchases nothing.

## Transfer and chapter-specific remediation

Pause before ticking and verify no advancement. Compare a stock condition episode with a clock interval; they use different rearming rules.

If both implementations appear equivalent, inspect work_per_pass rather than next_due after four passes. Both finally reach 140. In the separate full checkpoint, seven vanilla tubs cost 1750 pence, displayed as GBP 17.50: divide by 100 for pounds without changing the integer ledger.

For the oral transfer, choose fresh values that preserve the same invariant but are absent from CASES. Ask for the expected result before execution and retain both. For Chapters 3, 5, 8 and 13, distinguish the pure-function transfer from the runtime extension; ReplayModel objects, staged files and database transactions do not belong in TRANSFER_CASES. Chapter 3 provides an explicit student-owned model/limits integration cell and retains stop reason, attempted calls, configured exposure and actual tool messages.

## Assessment, evidence and observed pilot

Score five dimensions 0–2: justified prediction; contract code with a novel case; independently repaired real code; causal file:line → output trace; explanation of scope and remaining uncertainty. Zero is missing/incorrect, one needs a specific correction, two is supported by retained evidence. Suggested readiness threshold is 8/10, requiring full credit for the repair and evidence limits. Record your actual rubric choice.

Keep first-attempt code, visible-case results, transfer cases, all three trial records, the student source patch, trace and exit ticket. Record whether each run was performed by the student, instructor or automation. A worked answer, a reference PASS, or a template lookup is not student construction. Review whether the patch repairs the function for a second case instead of special-casing this fixture.

Use `classroom-pilot-record-v1.md` for the real pilot. Record anonymous learner ID, environment/cohort SHA, start/finish times, setup errors, first-attempt failure, assistance, repair outcome and transfer explanation. Leave unobserved fields blank. The proposed 90 minutes and automated checks are not evidence of classroom completion, learning gain, human render approval or Manning acceptance.

## Scope after this lesson

This arithmetic does not persist jobs, define time zones or prevent duplicate transactions. The runtime supplies those boundaries; the checkpoint proves a local child run, not long-term host availability.

Continue with the next manuscript chapter after completing this practical. Preserve the copied experiment as evidence; never install its deliberately broken source into the working agent.
