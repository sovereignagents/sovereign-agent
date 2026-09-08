# Chapter 15 instructor guide — What must we know before resuming a restored agent?

**Created:** 2026-09-08 · **Last-updated:** 2026-09-08 · **Status:** DRAFT educator companion v2

Supersedes v1 for new classes. Use `ch15-operation-class-v2.ipynb`. Preserve first attempts and the distributed v1 files. The book remains at profrod.ai/book.

## Why Lucy needs this lesson

Lucy’s restored snapshot starts work before later supplier activity and physical stock have been reconciled.

The student should finish able to explain that consequence using an actual altered implementation, a retained observation and a repair. The ten-minute decision function is a warm-up. The central practical copies and changes `src/sovereign_agent/assistant_service.py`; executing an untouched checkpoint is not completion of that practical.

## Prepare the actual experiment

Prerequisites: Chapter 14 separate evidence; backup snapshots versus later external history. Use Python 3.14 with the book’s locked dependencies. The current educator index names the exact cohort commit, and the runtime experiment verifies SHA-256 `909180473cf321a19b0f40bb735ad8a19dbcf0aa77a34dbaa12ef8ddfc75ad01` before copying the target. Do not remove a mismatched-hash guard; locate the pinned files. Chapter 1 alone remains standalone standard-library Python 3.11 or newer.

One probe subprocess performs real local SQLite backup and restore in a temporary directory. It installs no service, reboots no host, and makes no network call. The probe subprocess has a 60-second ceiling. Three default trials run per notebook. This is an execution bound, not a promised classroom duration. Rehearse on the actual classroom machines and record observed time. The helper creates no server kernel and installs no dependencies. No paid provider, real Telegram account, real purchase or private Zeocore package is needed.

The optional whole-chapter checkpoint is a separate cell with RUN_FULL_CHECKPOINT=False. Its ceiling is 180 seconds. Read its process behavior before enabling it: checkpoints/ch15.py: experiment. Follow backup → later remote orders → restore pause → inspect_account → exact recovery plan → fresh work. The source probe and checkpoint differ in scope; retain their results under separate labels. Specifically, Chapter 10 and 16 checkpoints kill an actual local worker; Chapter 11 runs an MCP child but does not run containers by default; Chapter 15 does not install a service or reboot a host.

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

A backup contains one local order, but the supplier retained two. Should restoring the file automatically resume buying? Can the restore recreate unrecorded historical model usage?

Implement decide(case). Given required_skus, observed inventory mapping and receipts_complete, return PAUSED unless receipt enumeration is complete, observed keys exactly match required_skus and every on_hand value is an exact nonnegative int. Otherwise return OBSERVATIONS_COMPLETE_HISTORY_UNPROVEN. This is an audit precondition, never permission to unpause.

The new visible suite has 9 cases. Expected values are literal authored examples. Input mutation fails even if the return value agrees. Unsupported returns such as sets or bytes produce a JSON-safe FAILED diagnostic, including the return type, and do not prevent later reference and worked evidence being retained. PARTIAL means some cases were left unimplemented; it is not a pass.

Visible-case lookup tables can pass this suite. Tell students this explicitly. Review their source and ask a new teacher-chosen case after the submission; do not advertise published cases as hidden or tamper-proof. Passing visible tests alone receives no runtime-repair credit.

## Real-code teacher answer key

Target: `src/sovereign_agent/assistant_service.py:88`. The notebook prints surrounding lines so students can check this location against the pinned file.

Original decision:

```python
"UPDATE assistant_control SET epoch=?,paused=1 WHERE id=1"
```

Supplied fault:

```python
"UPDATE assistant_control SET epoch=?,paused=0 WHERE id=1"
```

The independently authored expected baseline is `{"restored_paused": true, "work_claimed_before_audit": false}`. The expected broken result is `{"restored_paused": false, "work_claimed_before_audit": true}`. A broken trial marked PASS means the fault behaved as predicted; it does not mean the modified runtime is safe.

The prepared snapshot overwrites the live database after its temporary pause. Its own paused flag controls final state. Old approval revocation still remains, so claiming a draft is not proof of a new purchase.

The actual probe imports this copied module, invokes its function, then prints fields from the returned tool result or retained database state. Read the complete probe in `runtime-experiments-v1.json` or `lab.probe`, and require the student to identify that data path. Printing the expected dictionary in a replacement stub fails this outcome.

The minimal worked repair restores the original marked fragment above. Students may implement an equivalent repair but must rerun the probe and explain the changed observation. Retain their source before creating the separate worked copy. The supplied answer never overwrites student_repair or student_source.

Trace submission fields are source_path, source_line, observation_key, observed_value and explanation. Choose one changed key from the expected dictionaries above. Mechanical validation checks that the location and value exist; STRUCTURE_VALID_TEACHER_REVIEW_REQUIRED means you must still judge the causal explanation. Award no trace credit for a copied location with no explanation of the function call and returned data.

## Warm-up worked answer

```python
def worked_decide(case):
    observed = case["observed"]
    if not case["receipts_complete"] or set(observed) != set(case["required_skus"]):
        return "PAUSED"
    if any(type(value) is not int or value < 0 for value in observed.values()):
        return "PAUSED"
    return "OBSERVATIONS_COMPLETE_HISTORY_UNPROVEN"
```

Zero is valid; an extra SKU requires reconciliation rather than silent admission. The checkpoint restores one local order, reconciles both remote receipts, yields vanilla on_hand 8 and strawberry on_order4, keeps the snapshot unchanged and explicitly retains incomplete historical model usage. Systemd installation/reboot is not run here.

## Transfer and chapter-specific remediation

Compare the unchanged backup hash before and after restore. Explain why missing historical model usage cannot be reconstructed from supplier receipts.

If restoring a file is called recovery complete, compare the snapshot’s old records with later independent receipts. Restoring leaves work paused and older approvals revoked. The probe’s claim being admitted is a restart-policy failure, not evidence that a revoked purchase can execute. Zero physical stock is valid; missing, negative or unknown stock is not silently accepted.

For the oral transfer, choose fresh values that preserve the same invariant but are absent from CASES. Ask for the expected result before execution and retain both. For Chapters 3, 5, 8 and 13, distinguish the pure-function transfer from the runtime extension; ReplayModel objects, staged files and database transactions do not belong in TRANSFER_CASES. Chapter 3 provides an explicit student-owned model/limits integration cell and retains stop reason, attempted calls, configured exposure and actual tool messages.

## Assessment, evidence and observed pilot

Score five dimensions 0–2: justified prediction; contract code with a novel case; independently repaired real code; causal file:line → output trace; explanation of scope and remaining uncertainty. Zero is missing/incorrect, one needs a specific correction, two is supported by retained evidence. Suggested readiness threshold is 8/10, requiring full credit for the repair and evidence limits. Record your actual rubric choice.

Keep first-attempt code, visible-case results, transfer cases, all three trial records, the student source patch, trace and exit ticket. Record whether each run was performed by the student, instructor or automation. A worked answer, a reference PASS, or a template lookup is not student construction. Review whether the patch repairs the function for a second case instead of special-casing this fixture.

Use `classroom-pilot-record-v1.md` for the real pilot. Record anonymous learner ID, environment/cohort SHA, start/finish times, setup errors, first-attempt failure, assistance, repair outcome and transfer explanation. Leave unobserved fields blank. The proposed 90 minutes and automated checks are not evidence of classroom completion, learning gain, human render approval or Manning acceptance.

## Scope after this lesson

This small audit omits operator authority, plan digest, supplier epoch rotation and transactional recovery. Follow the actual recovery runbook before a host resumes work.

Continue with the next manuscript chapter after completing this practical. Preserve the copied experiment as evidence; never install its deliberately broken source into the working agent.
