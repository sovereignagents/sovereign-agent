"""Outcome checks must reject fluent failures, not just grade a completed loop."""

import json

from reference_organizations.store.agent import OfflineShopModel
from reference_organizations.store.evaluation import CASES, candidate_checks, evaluate
from sovereign_agent.model_turn import ModelTurn, ToolCall


def test_authored_scenarios_and_baseline_are_independent_of_model():
    report = evaluate(OfflineShopModel)
    assert report["passed"] is True
    assert len(report["cases"]) == 8
    assert {row["split"] for row in report["cases"]} == {"development", "regression", "held-out"}
    assert all(row["baseline"]["model_calls"] == 0 for row in report["cases"])
    assert all(candidate_checks(report).values())


def test_fluent_answer_without_stock_evidence_fails():
    class Fluent:
        def complete(self, *args, **kwargs):
            return ModelTurn("Everything is fine. I recommend buying nothing.")

    report = evaluate(Fluent, cases=(CASES[0],))
    row = report["cases"][0]
    assert row["checks"]["completed"] is True
    assert row["checks"]["quantities"] is False and row["checks"]["grounded"] is False
    assert report["passed"] is False


def test_correct_numbers_with_wrong_currency_fail():
    class WrongCurrency(OfflineShopModel):
        def complete(self, *args, **kwargs):
            result = super().complete(*args, **kwargs)
            return ModelTurn(
                result.content.replace("pence GBP", "euros"), result.calls, result.output_tokens
            )

    report = evaluate(WrongCurrency, cases=(CASES[0],))
    row = report["cases"][0]
    assert row["checks"]["quantities"] is True
    assert row["checks"]["currency_labels"] is False and report["passed"] is False


def test_hostile_requested_tool_never_becomes_authorized():
    class Hostile:
        def complete(self, messages, *args, **kwargs):
            if not any(m["role"] == "tool" for m in messages):
                return ModelTurn(calls=(ToolCall(id="bad", name="approve", arguments={}),))
            refusal = json.loads(messages[-1]["content"])
            assert refusal["ok"] is False
            return ModelTurn("Nothing purchased.")

    report = evaluate(
        Hostile, cases=(next(case for case in CASES if case.name == "hostile_request"),)
    )
    row = report["cases"][0]
    assert row["checks"]["no_purchases"] is True
    assert row["checks"]["allowed_operations"] is False and report["passed"] is False


def test_malformed_tool_arguments_are_a_failed_case_not_a_grader_crash():
    class Malformed:
        def complete(self, messages, *args, **kwargs):
            if not any(m["role"] == "tool" for m in messages):
                return ModelTurn(
                    calls=(
                        ToolCall(
                            id="one", name="draft_order", arguments={"sku": None, "quantity": "6"}
                        ),
                        ToolCall(
                            id="two", name="draft_order", arguments={"sku": "V", "quantity": True}
                        ),
                    )
                )
            return ModelTurn("The draft is ready in GBP.")

    report = evaluate(Malformed, cases=(CASES[0],))
    assert report["passed"] is False
    assert report["cases"][0]["checks"]["quantities"] is False
    assert report["cases"][0]["checks"]["no_tool_errors"] is False
