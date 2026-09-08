"""Chapter 12: evaluate named outcomes, expose blind spots and preserve a report."""

import argparse
import hashlib
import json
import tempfile
import tomllib
from pathlib import Path

from reference_organizations.store.agent import OfflineShopModel
from reference_organizations.store.evaluation import CASES, evaluate
from reference_organizations.store.improvement import save_report
from sovereign_agent.assistant_context import Skill
from sovereign_agent.model_turn import HTTPModel, ModelTurn, ToolCall


class FluentWithoutEvidence:
    def complete(self, *args, **kwargs):
        return ModelTurn("Everything is fine. Buy nothing.")


class WrongCurrency(OfflineShopModel):
    def complete(self, *args, **kwargs):
        turn = super().complete(*args, **kwargs)
        return ModelTurn(turn.content.replace("pence GBP", "euros"), turn.calls, turn.output_tokens)


class WrongAmount(OfflineShopModel):
    def complete(self, *args, **kwargs):
        turn = super().complete(*args, **kwargs)
        return ModelTurn(
            turn.content.replace("1500 pence GBP", "999999 pence GBP"),
            turn.calls,
            turn.output_tokens,
        )


class ForbiddenRequest:
    def complete(self, messages, *args, **kwargs):
        if not any(m["role"] == "tool" for m in messages):
            return ModelTurn(calls=(ToolCall(id="forbidden", name="approve", arguments={}),))
        return ModelTurn("No purchases made.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default="qwen3")
    parser.add_argument("--output", type=Path, help="retain the complete report in this directory")
    args = parser.parse_args()
    models = (FluentWithoutEvidence, WrongCurrency, ForbiddenRequest)
    failures = [evaluate(model, cases=(CASES[0],)) for model in models]
    assert all(not report["passed"] for report in failures)
    assert all(report["acceptance"]["status"] == "REJECTED" for report in failures)
    assert failures[2]["cases"][0]["checks"]["no_purchases"]
    print("Fluent, wrong-currency and forbidden-request fixtures:", "REJECTED")
    blind = evaluate(WrongAmount, cases=(CASES[0],))
    assert blind["passed"] and "999999 pence GBP" in blind["cases"][0]["answer"]
    assert blind["acceptance"]["status"] == "REVIEW_REQUIRED"
    print("Wrong prose amount with correct calls:", blind["acceptance"]["status"])
    source = Path(__file__).parents[1] / "skills" / "opening-check-v1.toml"
    skill = Skill.model_validate(tomllib.loads(source.read_text()))
    factory = (
        (lambda: HTTPModel(model=args.model, reasoning_effort="none"))
        if args.live
        else OfflineShopModel
    )
    report = evaluate(factory, skills=(skill,), repeats=2)
    passed = sum(row["passed"] for row in report["cases"])
    print("Named case checks:", passed, "/", len(report["cases"]))
    print("Acceptance:", report["acceptance"]["status"])
    assert report["baseline_totals"]["model_calls"] == 0
    assert all(row["checks"]["baseline_matches_authored_answer"] for row in report["cases"])
    print("Baseline authored-answer matches:", len(report["cases"]))
    with tempfile.TemporaryDirectory(prefix="lucy-evaluation-proof-") as temporary:
        path, digest = save_report(args.output or Path(temporary), report)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert json.loads(path.read_text())["acceptance"] == report["acceptance"]
        print("Saved report digest verified:", True)
        if args.output:
            print("Retained report:", path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
