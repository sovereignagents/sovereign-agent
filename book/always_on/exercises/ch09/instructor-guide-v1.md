# Chapter 9 instructor guide — Survive the ambiguous order

**Created:** 2026-09-09 · **Status:** DRAFT successor companion v1

## Purpose

Students build the durable local transition around an external effect, then make and repair a real duplicate-purchase defect. Lucy's observable consequence is concrete: a fresh retry identity creates two supplier orders while the agent still reports uncertainty.

Unit A owns the `SENDING → UNKNOWN → CONFIRMED/REJECTED` transition against the real SQLite schema. Unit B mutates `src/sovereign_agent/assistant_orders.py` in a fingerprinted temporary copy and adapts a second supplier's discovery shape into the exact internal receipt contract.

## Preparation

Use the locked Python 3.14 authoring environment. The exercises make no model or channel calls and cannot contact a real supplier. They start reviewed loopback or in-memory fixtures. A local subprocess is not a security sandbox.

Run Unit A before Unit B in the same working directory. The official release builder uses a chapter-scoped temporary directory so the signed handoff is consumed across fresh kernels.

## Teaching sequence

| Minutes | Activity | Evidence |
|---:|---|---|
| 0–10 | Predict local and supplier state after the lost reply | First prediction and falsifier |
| 10–35 | Implement `record_transition` | Visible state and money transitions |
| 35–55 | Connect to the loopback supplier | `UNKNOWN`, one remote row, then exact receipt |
| 55–65 | Inspect Unit A handoff and predict the retry fault | Durable evidence path |
| 65–80 | Break and repair the actual send boundary | Baseline/broken/repaired records |
| 80–100 | Normalize another supplier and transfer to rejection | Chronology and money evidence |
| 100–110 | Explain guarantee and limits | Exit ticket |

Record actual classroom time. This plan is not evidence that a learner completed it.

## Assessment

Require all of the following:

- `SENDING` is committed before the external call;
- `UNKNOWN` keeps the reservation;
- an exact conclusive receipt settles the reservation only once;
- mismatched or nonconclusive receipts fail closed;
- the real copied runtime returns one supplier order after repair;
- the partner transfer produces `order` then `lookup`, with no second send;
- the learner explains that provider idempotency and discovery are contractual dependencies.

The hidden Unit A case uses strawberry, a rejection, and 1,100 pence. It defeats hard-coded vanilla/1,500/accepted logic. The hidden Unit B case uses the actual response-loss probe and a `declined` partner result. A fresh-ID repair or an adapter that returns the partner payload unchanged fails.

The source repository contains the instructor holdouts; they are separated from student artifacts, not cryptographically secret. Do not present a starter notebook's clean execution or an official solution run as student mastery.

## Worked mechanisms

The solution records one row whose exact `id` and `work_id` match, validates canonical proposal JSON, and changes reserved/spent amounts only on the first terminal transition. The runtime repair restores the stable `identifier` at `supplier.order`. The adapter maps only `accepted` and `declined`; any other decision is rejected.

## Scope

This fixture proves one retained intent can reconcile against a supplier with persistent discovery and stable-key idempotency. It does not prove universal exactly-once delivery, safe recovery from a backup that predates the intent, authentication of arbitrary receipts, process containment, or correctness for a supplier whose idempotency keys expire before recovery.
