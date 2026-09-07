**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** ACTIVE

# One bounded catering assignment

The full overhaul remains active. This runtime checkpoint implements the assignment required by planned Chapter 14; that manuscript is not yet drafted.

The operator may delegate one catering calculation from an existing shop work record. Its immutable inquiry, parent, deadline, model-call limit, estimate per call and total estimated allowance are durable. Repeated identical handoffs return the same child; changed contracts conflict. A research parent cannot delegate again. The default shop worker never claims research work.

The child has its own session, so a second worker can process it while the stock worker holds the parent's session. Model exposure is charged to the parent's billing session, and assignment call/cost consumption persists across replacement. Admission happens before each model call; lost replies do not refund allowance. This bounds estimated exposure, not provider invoices. Claim checks independently verify role, session, prompt and product subject. Research has no purchasing authority at the core proposal boundary.

The catering worker exposes one read-only calculation tool. Lucy's fixture specifies ten portions per tub and a catalog selling price; integer arithmetic rounds the required tubs upward. The model does not reserve stock, order supplies, receive deliveries or create another assignment. A successful result requires an actual checked quote observation. Channel output is built from that observation; the model's prose remains ungraded in the report. Comparing both paths through the same calculation does not prove the calculation correct: separately authored boundary expectations test one, ten, eleven and two hundred guests.

The comparison records function latency, agent latency, model/tool counts, transcripts and cumulative assignment exposure. For this fixed task the function is retained as the recommendation. Delegation is a demonstrated option, not a presumed improvement. A richer task would require new evidence before changing that recommendation.

Cancellation of the parent prevents later tool calls, observations and completion by its child. Deadline expiry cancels queued or active work. Stale generations cannot finish a replacement's work. Graceful shutdown requeues eligible research while retaining consumed allowance; a hard-killed worker is replaceable after its existing lease expires. An exhausted allowance leaves work blocked; retry cannot reset it.

## Commands and operation

`agent delegate PARENT_ID --guests 40 --sku SKU-VANILLA --deadline EPOCH_UTC` creates the assignment. Repeating it must supply the same absolute deadline. The command reports QUEUED, not completion. `agent research-work CHILD_ID` makes one bounded pass. `agent serve --research-worker` runs a separate worker against the same state root. The ordinary worker continues stock work and delivers completed child results through the parent's copied output route. No channel token is needed by the research worker.

`agent service install --research-worker` installs a separate Linux user unit, sovereign-agent-research.service. It reads research.env, separately from the main agent.env; that file should contain only the model configuration needed by this worker. Installation and removal refuse conflicting unit contents. This is a service recipe, not yet evidence of Linux reboot acceptance.

## Evidence and continuation

Thirteen focused tests cover authored quantity boundaries, handoff identity, transaction rollback, concurrent stock work, tool and core authority refusal, shared daily allowance, durable assignment budgets, cancellation during a model call, deadline expiry, actual unattended CLI routing, separate service configuration and graceful continuation. The full gate must pass before commit.

Remain active on account-wide restore reconciliation, Linux deployment and integrated acceptance, twelve manuscript chapters, proposal, pinned comparisons and exact-source site migration with rendered review. Restored state remains paused until external effects and current physical stock are reconciled.
