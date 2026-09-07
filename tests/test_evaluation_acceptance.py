"""Passing a bounded scenario grader must not silently certify ungraded prose."""

import json

from reference_organizations.store.agent import OfflineShopModel
from reference_organizations.store.evaluation import CASES, evaluate
from sovereign_agent.cli import main
from sovereign_agent.model_turn import ModelTurn


def test_incorrect_prose_amount_remains_an_explicit_review_requirement():
    class WrongAmount(OfflineShopModel):
        def complete(self, *args, **kwargs):
            turn = super().complete(*args, **kwargs)
            return ModelTurn(
                turn.content.replace("1500 pence GBP", "999999 pence GBP"),
                turn.calls,
                turn.output_tokens,
            )

    report = evaluate(WrongAmount, cases=(CASES[0],))
    assert "999999 pence GBP" in report["cases"][0]["answer"]
    assert report["passed"] is True  # The grader's declared blind spot is reproducible.
    assert report["acceptance"]["status"] == "REVIEW_REQUIRED"
    assert "explanation amounts" in report["acceptance"]["ungraded"]


def test_empty_reply_preserves_terminal_cause_and_rejects_acceptance():
    class Empty:
        def complete(self, *args, **kwargs):
            return ModelTurn()

    report = evaluate(Empty, cases=(CASES[0],))
    assert report["passed"] is False
    assert report["cases"][0]["loop_status"] == "EMPTY_REPLY"
    assert report["acceptance"]["status"] == "REJECTED"


def test_baseline_is_measured_once_per_case_against_authored_answers(monkeypatch):
    from reference_organizations.store import evaluation

    ticks = iter([100, 900, 1000, 2200])
    monkeypatch.setattr(evaluation.time, "perf_counter_ns", lambda: next(ticks))
    report = evaluate(OfflineShopModel, cases=CASES[:2])
    assert report["cases"][0]["baseline"]["drafts"] == [("V", 6), ("S", 4)]
    assert report["cases"][1]["baseline"]["drafts"] == []
    assert report["baseline_totals"]["seconds"] == 0.000002
    assert report["baseline_totals"]["model_calls"] == 0
    assert "excludes data acquisition" in report["baseline_totals"]["scope"]


def test_cli_exposes_review_requirement_and_preserves_the_report(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SOVEREIGN_AGENT_MODEL_MODE", raising=False)
    assert main(["agent", "evaluate", "--root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["passed"] is True and result["acceptance"] == "REVIEW_REQUIRED"
    with open(result["report"]) as stream:
        report = json.load(stream)
    assert report["schema"] == 2
    assert report["acceptance"]["status"] == result["acceptance"]
    assert len(report["cases"]) == 8
