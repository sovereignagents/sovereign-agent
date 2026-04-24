"""Classifier rule — Module 4 (`ClassifierVerifier`) in action.

## What this shows

A StructuredHalf rule whose `condition` is driven by a text classifier,
not a lambda. In the pub-booking scenario the agent emails the manager
asking if the booking is confirmed; the manager writes back; we need
to decide whether the reply counts as a confirmation.

A keyword match ("does it contain 'yes'?") is fragile — "yes, but only
if..." and "yes please" both pass; "yep", "sure", "confirmed",
"we'll do it" all fail; "no problem" passes for the WRONG reason. A
classifier captures the intent instead.

We use a fake sklearn-style classifier so the example has zero external
dependencies. Swap in `transformers.pipeline("text-classification",
model="distilbert-base-uncased-finetuned-sst-2-english")` and the
rest of the code is unchanged — that's the whole point of the
Verifier protocol.

## Run

    python -m examples.classifier_rule.run

## What it demonstrates

  * 6 test replies (3 clearly affirmative, 3 clearly negative)
  * All six are classified correctly and fire the right rule
  * Verifier score and reason appear in the structured half's output
    — the audit trail explains WHY the rule fired
  * Escalation path when the classifier's confidence is low
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sovereign_agent.halves.structured import Rule, StructuredHalf
from sovereign_agent.halves.verifiers import ClassifierVerifier, LLMJudgeVerifier
from sovereign_agent.session.directory import create_session

# ---------------------------------------------------------------------------
# Fake sklearn-style classifier (zero deps).
#
# In production, replace with either:
#
#   from sklearn.pipeline import Pipeline
#   ...your_sklearn_model...
#
#   OR
#
#   from transformers import pipeline
#   classifier = pipeline("text-classification", model="...")
#
# ClassifierVerifier auto-detects which interface you passed and
# handles both. No other code changes.
# ---------------------------------------------------------------------------


@dataclass
class FakeSentimentClassifier:
    """A toy "sentiment" classifier that looks for a handful of
    affirmative/negative cue phrases. Mimics sklearn's predict_proba
    interface: returns [[p_negative, p_positive]] for each input.

    In real code you'd use a trained model (sklearn, transformers,
    whatever). The point of this example is that ClassifierVerifier
    doesn't care — as long as the object has `predict_proba`, the
    rule just works.
    """

    # Cue phrases that indicate confirmation. Order roughly by strength.
    _AFFIRMATIVE = (
        "confirmed",
        "confirm",
        "yes",
        "yep",
        "sure",
        "we'll do it",
        "happy to",
        "go ahead",
        "sounds good",
        "all good",
        "fine by me",
    )
    _NEGATIVE = (
        "can't",
        "cannot",
        "not available",
        "unable",
        "declined",
        "no thanks",
        "sorry",
        "another time",
    )

    def predict_proba(self, batch: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in batch:
            tl = text.lower()
            pos_hits = sum(1 for cue in self._AFFIRMATIVE if cue in tl)
            neg_hits = sum(1 for cue in self._NEGATIVE if cue in tl)
            # Simple confidence calc. Real models learn this; this one
            # just maps hits to a probability.
            if pos_hits == 0 and neg_hits == 0:
                p_pos = 0.5  # ambiguous
            elif neg_hits > pos_hits:
                p_pos = max(0.05, 0.3 - 0.1 * neg_hits)
            else:
                p_pos = min(0.98, 0.7 + 0.1 * pos_hits)
            out.append([1.0 - p_pos, p_pos])
        return out


# ---------------------------------------------------------------------------
# Build the verifier and the StructuredHalf rules
# ---------------------------------------------------------------------------


def _build_fake_verifier() -> ClassifierVerifier:
    """Offline-mode verifier: fake sklearn-style classifier, zero deps."""
    return ClassifierVerifier(
        classifier=FakeSentimentClassifier(),
        input_builder=lambda data: data["manager_reply"],
        threshold=0.8,  # require strong confidence, not 50/50
        name="manager_affirmative",
    )


def _build_real_verifier() -> LLMJudgeVerifier:
    """Real-mode verifier: an LLM judging whether the reply is affirmative.

    This is the scenario's core claim under test: swap the classifier
    for an LLM judge — a completely different backend — without
    changing StructuredHalf, Rule, or any audit-trail code. Same
    VerifierResult contract, same {verifier_reason, verifier_score}
    keys land in the trace.
    """
    from sovereign_agent._internal.llm_client import OpenAICompatibleClient
    from sovereign_agent.config import Config

    cfg = Config.from_env()
    client = OpenAICompatibleClient(base_url=cfg.llm_base_url, api_key_env=cfg.llm_api_key_env)
    return LLMJudgeVerifier(
        client=client,
        model=cfg.llm_executor_model,
        prompt_template=(
            "You are a strict compliance classifier. A pub manager has "
            "replied to a booking request. Classify their reply as "
            "AFFIRMATIVE (a clear yes, they confirm the booking) or NOT "
            "AFFIRMATIVE (anything else: decline, hedging, ambiguous, "
            "needs-to-check).\n\n"
            "Reply: {manager_reply}\n\n"
            'Respond with JSON ONLY: {{"decision": true|false, "reason": "..."}}. '
            "decision=true means AFFIRMATIVE. "
            "Be strict; on any doubt, hedging, or conditional language, return false."
        ),
        name="manager_affirmative_llm",
    )


def _build_structured_half(verifier) -> StructuredHalf:
    def _commit_booking(data: dict) -> dict:
        return {
            "action": "committed",
            "venue": data["venue"],
            "party": data["party"],
            "notes": "Manager's reply classified as affirmative.",
        }

    def _escalate_to_human(data: dict) -> dict:
        return {
            "action": "escalated",
            "reason": "manager reply was NOT classified as affirmative; human review needed",
        }

    return StructuredHalf(
        rules=[
            Rule(
                name="manager_confirmed",
                condition=verifier,  # <-- verifier (classifier OR LLM judge)
                action=_commit_booking,
            ),
            # Fallback: any other reply escalates. Equivalent to a
            # catch-all "we didn't get a clear yes, ask a human."
            Rule(
                name="manager_ambiguous_or_declined",
                condition=lambda _d: True,
                action=_escalate_to_human,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# Test replies
# ---------------------------------------------------------------------------

_REPLIES: list[tuple[str, str, str]] = [
    # (label, expected_rule, text)
    ("affirmative", "manager_confirmed", "Yes, we'll do it. Book for 19:30."),
    ("affirmative", "manager_confirmed", "Confirmed. Deposit instructions attached."),
    ("affirmative", "manager_confirmed", "Sure, go ahead — all good on our side."),
    ("negative", "manager_ambiguous_or_declined", "Sorry, we can't host that night."),
    ("negative", "manager_ambiguous_or_declined", "Unable to accommodate — another time?"),
    (
        "ambiguous",
        "manager_ambiguous_or_declined",
        "Let me check with the kitchen and get back to you.",
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_scenario(real: bool = False) -> None:
    if real:
        verifier = _build_real_verifier()
        classifier_label = f"LLMJudgeVerifier ({verifier.model})"
        threshold_label = "n/a (LLM returns binary decision)"
    else:
        verifier = _build_fake_verifier()
        classifier_label = "FakeSentimentClassifier (offline, zero deps)"
        threshold_label = "0.8"

    half = _build_structured_half(verifier)
    with tempfile.TemporaryDirectory() as td:
        sessions_dir = Path(td) / "sessions"
        sessions_dir.mkdir()
        session = create_session(
            scenario="classifier-rule-demo",
            task="Classify manager replies and commit or escalate.",
            sessions_dir=sessions_dir,
        )
        print(f"Session {session.session_id}")
        print(f"  verifier:   {classifier_label}")
        print(f"  threshold:  {threshold_label}")
        print()
        print(f"{'label':<12} {'expected':<30} {'fired':<30} {'score':>6}  reply")
        print("-" * 120)

        correct = 0
        for label, expected_rule, text in _REPLIES:
            payload = {
                "data": {
                    "manager_reply": text,
                    "venue": "Haymarket Tap",
                    "party": 4,
                }
            }
            result = await half.run(session, payload)
            fired_rule = result.output.get("rule", "(no rule)")
            score = result.output.get("verifier_score")
            score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "--"
            reason = result.output.get("verifier_reason", "")

            match = fired_rule == expected_rule
            if match:
                correct += 1
            marker = "✓" if match else "✗"

            # Shorten reply for table display.
            reply_short = text[:60] + "..." if len(text) > 60 else text
            print(
                f"{marker} {label:<10} {expected_rule:<30} {fired_rule:<30} "
                f"{score_str:>6}  {reply_short}"
            )
            if not match:
                print(f"    verifier reason: {reason}")

        print("-" * 120)
        print(f"Correct: {correct}/{len(_REPLIES)}")

        # Show what appears in the structured half's output — this is
        # the audit trail a compliance reviewer would read later.
        print()
        print("=== Last result's full output (what lands in the trace) ===")
        import json

        print(json.dumps(result.output, indent=2, default=str))

        print()
        print("=== What this proves ===")
        print(
            "  * The rule's `condition` is a ClassifierVerifier instead of a "
            "lambda,\n    and the rest of StructuredHalf is unchanged."
        )
        print(
            "  * Every rule firing records `verifier_reason` and "
            "`verifier_score`\n    in its output — the audit trail explains "
            "WHY, not just WHAT."
        )
        print(
            "  * Swap FakeSentimentClassifier for a real sklearn pipeline or a\n"
            "    transformers `text-classification` pipeline and NO other code\n"
            "    changes are needed. That's the contract the protocol enforces."
        )


def main() -> None:
    import sys

    real = "--real" in sys.argv
    asyncio.run(run_scenario(real=real))


if __name__ == "__main__":
    main()
