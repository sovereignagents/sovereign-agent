"""StructuredHalf: minimal rule-following state machine (skeleton).

Intentionally small. Production use cases needing sophisticated dialog
management can swap in a Rasa-based StructuredHalf via the [rasa] extra.
The default implementation is dependency-free so the chapters can teach it.

This is a Tier-3 skeleton: the Rule -> action -> escalate flow is wired up,
but there is no built-in dialog state management beyond the rule list. Real
use cases will want to register richer rules.

v0.2 update: `Rule.condition` and `Rule.escalate_if` now accept either a
plain callable (legacy form) or a `Verifier` (new form). See
sovereign_agent/halves/verifiers.py for the protocol and concrete
LambdaVerifier/ClassifierVerifier/LLMJudgeVerifier implementations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sovereign_agent.discovery import DiscoverySchema
from sovereign_agent.halves import HalfResult
from sovereign_agent.halves.verifiers import (
    Verifier,
    VerifierResult,
    as_verifier,
)
from sovereign_agent.session.directory import Session

# A rule condition/escalate test is either a plain callable (legacy) or
# anything implementing the Verifier protocol. StructuredHalf.run()
# normalises both to Verifier at evaluation time.
RuleCheck = Callable[[dict], bool] | Verifier


@dataclass
class Rule:
    name: str
    condition: RuleCheck
    action: Callable[[dict], dict]
    escalate_if: RuleCheck | None = None


class StructuredHalf:
    name = "structured"

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules: list[Rule] = list(rules or [])

    def add_rule(self, rule: Rule) -> None:
        self.rules.append(rule)

    def discover(self) -> DiscoverySchema:
        return {
            "name": self.name,
            "kind": "half",
            "description": (
                "Minimal structured half. Evaluates a list of rules in order "
                "and runs the first matching action. Escalates if any rule's "
                "escalate_if returns True."
            ),
            "parameters": {"type": "object", "properties": {"data": {"type": "object"}}},
            "returns": {"type": "object"},
            "error_codes": [],
            "examples": [
                {
                    "input": {"data": {"action": "confirm"}},
                    "output": {"success": True, "next_action": "complete"},
                }
            ],
            "version": "0.2.0",
            "metadata": {"rule_count": len(self.rules)},
        }

    async def run(self, session: Session, input_payload: dict) -> HalfResult:
        data = input_payload.get("data") or input_payload
        for rule in self.rules:
            # v0.2: normalise condition to a Verifier. This lets rules
            # mix lambdas and classifiers/LLM-judges without StructuredHalf
            # caring which is which.
            try:
                cond_verifier = as_verifier(rule.condition)
            except TypeError as exc:
                return HalfResult(
                    success=False,
                    output={"rule": rule.name, "error": str(exc)},
                    summary=f"rule {rule.name!r} has malformed condition",
                    next_action="escalate",
                )
            # cond_verifier is non-None because rule.condition is required.
            assert cond_verifier is not None
            try:
                cond_result: VerifierResult = await cond_verifier.evaluate(data)
            except Exception as exc:  # noqa: BLE001
                return HalfResult(
                    success=False,
                    output={"rule": rule.name, "error": str(exc)},
                    summary=f"rule {rule.name!r} condition raised",
                    next_action="escalate",
                )
            if not cond_result.ok:
                continue

            # Escalation check.
            if rule.escalate_if is not None:
                try:
                    esc_verifier = as_verifier(rule.escalate_if)
                except TypeError as exc:
                    return HalfResult(
                        success=False,
                        output={"rule": rule.name, "error": str(exc)},
                        summary=f"rule {rule.name!r} has malformed escalate_if",
                        next_action="escalate",
                    )
                assert esc_verifier is not None
                try:
                    esc_result = await esc_verifier.evaluate(data)
                except Exception as exc:  # noqa: BLE001
                    return HalfResult(
                        success=False,
                        output={"rule": rule.name, "error": str(exc)},
                        summary=f"rule {rule.name!r} escalate_if raised",
                        next_action="escalate",
                    )
                if esc_result.ok:
                    return HalfResult(
                        success=False,
                        output={
                            "rule": rule.name,
                            "reason": esc_result.reason or "escalate_if returned True",
                            "verifier_reason": esc_result.reason,
                            "verifier_score": esc_result.score,
                        },
                        summary=f"rule {rule.name!r} triggered escalation",
                        next_action="escalate",
                    )

            # Action.
            try:
                result = rule.action(data)
            except Exception as exc:  # noqa: BLE001
                return HalfResult(
                    success=False,
                    output={"rule": rule.name, "error": str(exc)},
                    summary=f"rule {rule.name!r} action raised",
                    next_action="escalate",
                )
            return HalfResult(
                success=True,
                output={
                    "rule": rule.name,
                    "result": result,
                    # v0.2: surface the verifier's reasoning in the output
                    # so the trace records WHY the rule fired. Critical
                    # for classifier/LLM-judge rules where you need to
                    # justify decisions later.
                    "verifier_reason": cond_result.reason,
                    "verifier_score": cond_result.score,
                },
                summary=f"rule {rule.name!r} fired",
                next_action="complete",
            )
        # No rule matched.
        return HalfResult(
            success=False,
            output={"reason": "no matching rule"},
            summary="structured half could not match any rule",
            next_action="escalate",
        )


__all__ = ["Rule", "RuleCheck", "StructuredHalf"]
