# How to build and verify each chapter

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

Read in order. The chapters form one cumulative implementation, with one executable checkpoint per chapter and increasingly demanding shop scenarios. A checkpoint is a reproducible observation of a design; it is not a substitute for constructing and understanding the component described in the prose.

## Keep source and environment together

Use the exact source commit linked by the edition you are reading. A moving branch can contain later behavior than a printed listing. From the repository root, install the committed environment and run the first checkpoint:

```bash
uv sync --frozen --python 3.14 --group dev
uv run --python 3.14 python book/always_on/checkpoints/ch01.py
```

Use Python 3.14 throughout, including the inline examples. Some later listings use Python 3.14's unparenthesized multiple-exception syntax; on older interpreters those statements are syntax errors. Run inline examples and checkpoints from the repository root, because relative fixture paths start there. Chapters 2 and 3 give exact instructions for saving the reader-built definitions in `book/always_on/learner/`. Run another checkpoint by replacing the chapter number. The [checkpoint index](CHECKPOINTS.md) links all sixteen files. Chapter 1 explains the setup before asking for the first live model call. Do not use the published PyPI version as a substitute for an unreleased edition checkout.

## Read the evidence labels literally

A Python listing introduces code you can inspect. The website numbers figures and listings within each chapter from source order; the source captions intentionally keep their stable descriptive text. A selected listing title identifies a passage discussed in the surrounding prose; it does not imply that every code fence is a standalone program. Adjacent text output records the shown experiment. The construction instrument executes marked Python examples and compares paired output. Bash commands may require the stated host, model or credentials; their presence in a fence is not a claim that a portable test executed them.

| Evidence | What it establishes | What still needs inspection |
| --- | --- | --- |
| Deterministic model fixture | Dispatch, control flow and authored failure paths | Live model choices and explanation quality |
| SQLite and independent supplier fixture | Local accounting and the controlled supplier's retained operations | Another provider's idempotency and discovery contract |
| Linux service experiment | The recorded installation, restart and maintenance cases | Availability outside the observed run |
| Container experiment | The tested file, network, identity and lifetime restrictions | Host kernel and container-engine compromise |
| Mechanical chapter score | Named structural and pedagogical signals | Reader comprehension, prose quality and visual judgment |

A high score does not change DRAFT to READY. Model-dependent evaluation also retains a review requirement: a correct tool trace can coexist with a false amount in its explanation. Chapter 12 demonstrates that blind spot instead of letting the instrument certify itself.

## Work with Lucy's units

The shop uses multiple SKUs from the beginning. Quantities are whole tubs; monetary records use integer pence. Display pounds only at the presentation boundary. Physical stock, pending replenishment, reserved spend and confirmed expenditure are different values. Do not replace structured inventory with a remembered sentence, or treat an approval as proof of an external purchase.

Use synthetic shop data and a controlled supplier for the exercises. Configuration belongs to the operator. Keep tokens out of source, transcripts, screenshots and evidence bundles. A local MCP subprocess executes with host rights unless a separate execution boundary restricts it; a readable skill file grants no tool authority.

## Change a constraint, then explain the result

For each chapter, first reproduce the expected observation. Run the failure experiment and explain why the previous design fails. Implement the repair, then change an exercise constraint: a second product, repeated message, expired approval, late worker or incomplete supplier history. Check that your explanation follows the records actually produced.

The full repository gate is `make verify`. It also preserves the original curriculum and labs. The new construction gate is `uv run python scripts/verify_always_on_v1.py`; its `--complete` option requires READY statuses in addition to construction checks. Do not relax a failed assertion simply to reach a green report. The [reproducibility appendix](appendices/reproducibility-v1.md) describes how to retain an experiment that another builder can inspect.
