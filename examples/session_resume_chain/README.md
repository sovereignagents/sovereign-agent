# Example: session resume chain

## What it shows

Module 3 in action. Three generations of sessions linked via
`resumed_from`:

```
parent (research)
  └── child (deposit negotiation)
         └── grandchild (confirmation email)
```

Each child:

- Has a fresh session id, its own directory, its own state.
- Records `resumed_from` pointing at its parent.
- Auto-receives a parent-context summary prepended to its SESSION.md
  (trace tail, final result, tickets list).
- Leaves the parent **completely untouched** — forward-only rule
  preserved.

## Run

```bash
python -m examples.session_resume_chain.run
```

No LLM calls — pure library demo. Fast, deterministic.

## The API surface

```python
from sovereign_agent.session.resume import resume_session, find_ancestor_chain

child = resume_session(
    parent_id=parent.session_id,
    task="continue where we left off",
    sessions_dir=sessions_dir,
)
assert child.state.resumed_from == parent.session_id

# Walk the chain.
ancestors = find_ancestor_chain(grandchild)  # ['parent_id', 'child_id']
```

## What gets refused

`resume_session` refuses to fork a parent that is still running
(state = `planning` or `executing`):

```
ValidationError: cannot resume from session 'sess_xxx':
  state='planning' is not terminal.
  Pass allow_unfinished_parent=True to override.
```

This protects against reading a mid-write session whose memory and
trace are actively changing. The override flag is a sharp knife for
the rare case where you genuinely want to fork a live run (e.g., to
try an alternative path in parallel).

## What the planner sees

The child's SESSION.md opens with a block like this, inserted
automatically:

```markdown
## Parent session context (auto-generated)

This session resumes from `sess_d8a02d993a80`.
- Scenario: `pub-booking`
- Parent state: `completed`

### Parent result
{
  "booking_confirmed": true,
  "deposit_paid": 200
}

### Parent trace tail (last 20 of 47 events)
...

> The above is read-only context from the parent. This session is a
> fresh execution with its own trace, tickets, and memory. The planner
> MAY use parent context to guide its plan but MUST NOT assume the
> parent's side effects are still valid.
```

That last caveat matters. A resumed session is a **continuation**, not
a replay. The child shouldn't assume "the booking is committed" just
because the parent's result says so — the world might have moved on.
