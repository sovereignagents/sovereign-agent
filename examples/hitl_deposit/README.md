# Example: HITL deposit approval

## What it shows

Module 5 in action. An end-to-end human-in-the-loop flow:

1. Agent proposes a £500 booking deposit.
2. Tool returns `requires_human_approval=True` because the deposit
   exceeds the £300 auto-approve ceiling.
3. Executor writes the request to `ipc/awaiting_approval/<request_id>.json`
   and exits cleanly. **No coroutine holds state across the wait.**
4. A human (here: `typer.testing.CliRunner`) invokes the real CLI:

   ```sh
   sovereign-agent approvals grant <session_id> <request_id> --reason "..."
   # or
   sovereign-agent approvals deny  <session_id> <request_id> --reason "..."
   ```

5. `resume_from_approval()` re-enters the executor with the decision
   visible in the opening user message. The LLM adapts.

The script runs **both grant and deny paths** in sequence so you can
see the contrast.

## Run

```bash
python -m examples.hitl_deposit.run
```

No LLM credentials needed — uses the scripted `FakeLLMClient`.

## What you'll see

**Scenario A (granted):**
```
awaiting_approval: appr_xec_sg_1_l_book_1
pending approvals on disk: 1

Invoking CLI: `sovereign-agent approvals grant ...`
  granted: appr_xec_sg_1_l_book_1

Resuming executor with the decision surfaced to the LLM...
  final_answer: 'Approval granted. The £500 booking at Haymarket Tap
                 is now committed. Subgoal complete.'
```

**Scenario B (denied):**
```
Invoking CLI: `sovereign-agent approvals deny ...`
  denied: appr_xec_sg_1_l_book_1

Resuming executor with the denial surfaced to the LLM...
  final_answer: 'Understood — the £500 deposit exceeds the policy
                 limit. I will propose an alternative venue with a
                 lower deposit...'
```

The LLM didn't get a retry; it got a **new turn** with the denial in
its opening user message, and it adapted.

## The one thing that matters

A tool, any tool, can pause a session:

```python
return ToolResult(
    success=True,
    output={
        "venue_id": "...",
        "deposit_gbp": 500,
        "approval_reason": "Deposit exceeds auto-approve ceiling.",
    },
    summary="proposed booking awaiting approval",
    requires_human_approval=True,    # <-- that's it
)
```

The framework handles everything else: writing the request, exiting
the executor, surfacing the decision when you resume.

## Common pitfalls

**1. `approval_reason` must live inside `output`, not at `ToolResult` level.**
The framework pulls `approval_reason` from `output` to put in the
request file. If you put it on `ToolResult` directly, the approver
will see an empty reason and not know what they're deciding on.

**2. Use the CLI, not hand-written JSON.**
The CLI writes both the decision file AND the permanent audit log.
Hand-writing the decision file skips the audit log — you lose the
permanent record.

**3. Don't resume before the decision exists.**
`resume_from_approval()` raises `SovereignIOError` if called while
the request is still pending. Poll `list_pending_approvals()` or
`find_decision()` first, or wire a filesystem watcher.

## The audit trail

After a grant-and-resume cycle, the session directory looks like:

```
sessions/sess_b54d95d854bc/
├── ipc/
│   └── approval_granted/
│       └── appr_xec_sg_1_l_book_1.json     # ephemeral — live state
├── logs/
│   └── approvals/
│       ├── appr_xec_sg_1_l_book_1.request.json   # permanent audit
│       └── appr_xec_sg_1_l_book_1.decision.json  # permanent audit
└── ...
```

Double audit trail by design: the IPC file reflects live state (may
be pruned on archive); the `logs/approvals/` pair is permanent. Six
months later, a reviewer can reconstruct the exact request, the exact
arguments (with SHA-256), the approver, the reason, and the timing.
