"""Tests for v0.2 Module 4 — Verifier protocol.

Covers:
  * LambdaVerifier wrapping of (data) -> bool callables
  * ClassifierVerifier with both sklearn-style (predict_proba) and
    transformers-style (__call__) backends, including the threshold
    and positive_label semantics
  * LLMJudgeVerifier with defensive JSON parsing (the same reflex
    we apply to planner output — this time for judge output)
  * as_verifier() normalisation — protocol or callable or None
  * StructuredHalf now accepts Verifier-based conditions
    side-by-side with legacy lambda-based conditions (backward compat)
  * VerifierResult.reason is surfaced into the HalfResult output, so
    classifier-driven rules record WHY they fired
"""

from __future__ import annotations

import pytest

from sovereign_agent._internal.llm_client import (
    ChatResponse,
    FakeLLMClient,
    LLMClient,
    ScriptedResponse,
)
from sovereign_agent.halves.structured import Rule, StructuredHalf
from sovereign_agent.halves.verifiers import (
    ClassifierVerifier,
    LambdaVerifier,
    LLMJudgeVerifier,
    as_verifier,
)

# ---------------------------------------------------------------------------
# LambdaVerifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lambda_verifier_true_case() -> None:
    v = LambdaVerifier(lambda d: d["x"] > 10, name="x_over_10")
    r = await v.evaluate({"x": 42})
    assert r.ok is True
    assert "True" in r.reason
    assert r.score is None


@pytest.mark.asyncio
async def test_lambda_verifier_false_case() -> None:
    v = LambdaVerifier(lambda d: d["x"] > 10, name="x_over_10")
    r = await v.evaluate({"x": 3})
    assert r.ok is False


@pytest.mark.asyncio
async def test_lambda_verifier_swallows_exceptions() -> None:
    """A raising lambda must not propagate — it becomes ok=False with a reason.
    Otherwise a single bad rule would crash the whole StructuredHalf."""
    v = LambdaVerifier(lambda d: d["missing_key"] > 0, name="bad_fn")
    r = await v.evaluate({})
    assert r.ok is False
    assert "KeyError" in r.reason or "missing_key" in r.reason


# ---------------------------------------------------------------------------
# ClassifierVerifier — sklearn path (predict_proba)
# ---------------------------------------------------------------------------


class _FakeSklearnClassifier:
    """Minimal predict_proba stand-in, no sklearn dependency."""

    def __init__(self, prob_positive: float) -> None:
        self.prob_positive = prob_positive

    def predict_proba(self, batch):  # type: ignore[no-untyped-def]
        # sklearn returns [[p_neg, p_pos]] for binary.
        return [[1.0 - self.prob_positive, self.prob_positive]] * len(batch)


@pytest.mark.asyncio
async def test_classifier_verifier_sklearn_over_threshold() -> None:
    clf = _FakeSklearnClassifier(prob_positive=0.92)
    v = ClassifierVerifier(
        classifier=clf,
        input_builder=lambda d: d["text"],
        threshold=0.8,
        name="toxicity",
    )
    r = await v.evaluate({"text": "hello"})
    assert r.ok is True
    assert r.score == pytest.approx(0.92)
    assert "0.92" in r.reason or "0.920" in r.reason
    assert r.raw is not None and "probs" in r.raw


@pytest.mark.asyncio
async def test_classifier_verifier_sklearn_under_threshold() -> None:
    clf = _FakeSklearnClassifier(prob_positive=0.30)
    v = ClassifierVerifier(
        classifier=clf,
        input_builder=lambda d: d["text"],
        threshold=0.8,
        name="toxicity",
    )
    r = await v.evaluate({"text": "hello"})
    assert r.ok is False
    assert r.score == pytest.approx(0.30)


@pytest.mark.asyncio
async def test_classifier_verifier_input_builder_errors_are_caught() -> None:
    clf = _FakeSklearnClassifier(prob_positive=0.99)
    v = ClassifierVerifier(
        classifier=clf,
        input_builder=lambda d: d["missing_field"],
        threshold=0.5,
    )
    r = await v.evaluate({})
    assert r.ok is False
    assert "input_builder" in r.reason


# ---------------------------------------------------------------------------
# ClassifierVerifier — transformers pipeline path (__call__)
# ---------------------------------------------------------------------------


class _FakeTransformersPipeline:
    """Mimics `transformers.pipeline("text-classification", ...)`.

    Returns [{"label": str, "score": float}] for each input.
    """

    def __init__(self, label: str, score: float) -> None:
        self.label = label
        self.score = score

    def __call__(self, text):  # type: ignore[no-untyped-def]
        return [{"label": self.label, "score": self.score}]


@pytest.mark.asyncio
async def test_classifier_verifier_transformers_correct_label_above_threshold() -> None:
    pipe = _FakeTransformersPipeline(label="POSITIVE", score=0.88)
    v = ClassifierVerifier(
        classifier=pipe,
        input_builder=lambda d: d["email"],
        threshold=0.7,
        positive_label="POSITIVE",
        name="polite",
    )
    r = await v.evaluate({"email": "Dear Sir, ..."})
    assert r.ok is True
    assert r.score == pytest.approx(0.88)


@pytest.mark.asyncio
async def test_classifier_verifier_transformers_wrong_label() -> None:
    """Top label is something OTHER than positive_label — must be False
    even if score is high."""
    pipe = _FakeTransformersPipeline(label="NEGATIVE", score=0.99)
    v = ClassifierVerifier(
        classifier=pipe,
        input_builder=lambda d: d["email"],
        threshold=0.5,
        positive_label="POSITIVE",
    )
    r = await v.evaluate({"email": "hi"})
    assert r.ok is False


# ---------------------------------------------------------------------------
# LLMJudgeVerifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_judge_verifier_parses_clean_json() -> None:
    client = FakeLLMClient(
        [ScriptedResponse(content='{"decision": true, "reason": "email is polite"}')]
    )
    v = LLMJudgeVerifier(
        client=client,
        model="fake",
        prompt_template="Is this polite? {rendered_data}",
    )
    r = await v.evaluate({"email": "Dear customer, thank you."})
    assert r.ok is True
    assert "polite" in r.reason


@pytest.mark.asyncio
async def test_llm_judge_verifier_parses_markdown_fenced_json() -> None:
    """MiniMax-M2.5 wraps JSON in fences ~40% of the time. Judge responses
    are no different — verifier must tolerate."""
    client = FakeLLMClient(
        [
            ScriptedResponse(
                content=(
                    "Sure, here's my decision:\n\n"
                    "```json\n"
                    '{"decision": false, "reason": "tone is aggressive"}\n'
                    "```\n"
                )
            )
        ]
    )
    v = LLMJudgeVerifier(
        client=client,
        model="fake",
        prompt_template="Is this polite? {rendered_data}",
    )
    r = await v.evaluate({"email": "YOU MUST REPLY NOW."})
    assert r.ok is False
    assert "aggressive" in r.reason


@pytest.mark.asyncio
async def test_llm_judge_verifier_unparseable_is_deny() -> None:
    """Malformed judge output must NOT silently pass. Default is deny."""
    client = FakeLLMClient([ScriptedResponse(content="I think... well, maybe? Hard to say.")])
    v = LLMJudgeVerifier(
        client=client,
        model="fake",
        prompt_template="{rendered_data}",
    )
    r = await v.evaluate({"x": 1})
    assert r.ok is False
    assert "not parseable" in r.reason or "deny" in r.reason.lower()


@pytest.mark.asyncio
async def test_llm_judge_verifier_llm_error_is_deny() -> None:
    class _FailingClient(LLMClient):
        async def chat(self, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("network down")

    v = LLMJudgeVerifier(
        client=_FailingClient(),
        model="fake",
        prompt_template="{rendered_data}",
    )
    r = await v.evaluate({"x": 1})
    assert r.ok is False
    assert "network down" in r.reason


@pytest.mark.asyncio
async def test_llm_judge_verifier_template_formatting_with_data_fields() -> None:
    """prompt_template.format() should be able to reference data fields
    directly, not just {rendered_data}."""
    captured = []

    class _SpyClient(LLMClient):
        async def chat(self, *, model, messages, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(messages[0].content)
            return ChatResponse(content='{"decision": true, "reason": "ok"}')

    v = LLMJudgeVerifier(
        client=_SpyClient(),
        model="fake",
        prompt_template="Check this venue: {venue_id}, deposit: {deposit_gbp}",
    )
    await v.evaluate({"venue_id": "venue_hay", "deposit_gbp": 200})
    assert "venue_hay" in captured[0]
    assert "200" in captured[0]


# ---------------------------------------------------------------------------
# as_verifier() normalisation
# ---------------------------------------------------------------------------


def test_as_verifier_none_passthrough() -> None:
    assert as_verifier(None) is None


def test_as_verifier_wraps_callable() -> None:
    out = as_verifier(lambda d: True)
    assert isinstance(out, LambdaVerifier)


def test_as_verifier_returns_verifier_unchanged() -> None:
    v = LambdaVerifier(lambda d: True)
    assert as_verifier(v) is v


def test_as_verifier_rejects_non_callable() -> None:
    with pytest.raises(TypeError, match="expected Verifier or callable"):
        as_verifier(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# StructuredHalf integration — Verifier in the wild
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_structured_half_accepts_lambda_condition_legacy(fresh_session) -> None:
    """The pre-v0.2 form still works: condition is a bare lambda."""
    fired = {"count": 0}

    def _action(data):  # type: ignore[no-untyped-def]
        fired["count"] += 1
        return {"booked": True}

    half = StructuredHalf(
        rules=[
            Rule(
                name="deposit_ok",
                condition=lambda d: d["deposit_gbp"] <= 300,
                action=_action,
            )
        ]
    )
    result = await half.run(fresh_session, {"data": {"deposit_gbp": 200}})
    assert result.success
    assert fired["count"] == 1
    # v0.2: even for lambda-backed rules, verifier_reason is surfaced.
    assert "verifier_reason" in result.output


@pytest.mark.asyncio
async def test_structured_half_accepts_verifier_condition(fresh_session) -> None:
    """The v0.2 form: condition is an explicit Verifier instance."""
    clf = _FakeSklearnClassifier(prob_positive=0.9)
    cond = ClassifierVerifier(
        classifier=clf,
        input_builder=lambda d: d.get("email", ""),
        threshold=0.8,
        name="polite",
    )

    def _action(data):  # type: ignore[no-untyped-def]
        return {"approved": True}

    half = StructuredHalf(
        rules=[
            Rule(
                name="polite_email",
                condition=cond,
                action=_action,
            )
        ]
    )
    result = await half.run(fresh_session, {"data": {"email": "Dear customer, ..."}})
    assert result.success
    assert result.output["verifier_score"] == pytest.approx(0.9)
    assert "polite" in result.output["verifier_reason"]


@pytest.mark.asyncio
async def test_structured_half_verifier_score_surfaces_in_output(
    fresh_session,
) -> None:
    """For probabilistic verifiers, the score belongs in the audit trail."""
    clf = _FakeSklearnClassifier(prob_positive=0.73)
    cond = ClassifierVerifier(
        classifier=clf,
        input_builder=lambda d: d["text"],
        threshold=0.5,
        name="sentiment",
    )
    half = StructuredHalf(
        rules=[
            Rule(
                name="positive_sentiment",
                condition=cond,
                action=lambda d: {"msg": "cheerful"},
            )
        ]
    )
    result = await half.run(fresh_session, {"data": {"text": "hi"}})
    assert result.success
    assert result.output["verifier_score"] == pytest.approx(0.73)


@pytest.mark.asyncio
async def test_structured_half_escalates_via_verifier(fresh_session) -> None:
    """escalate_if can also be a Verifier — e.g., 'is this payment
    fraudulent?' gated by a classifier."""
    fraud_clf = _FakeSklearnClassifier(prob_positive=0.95)
    fraud_check = ClassifierVerifier(
        classifier=fraud_clf,
        input_builder=lambda d: d.get("transaction", ""),
        threshold=0.9,
        name="fraud_detector",
    )

    half = StructuredHalf(
        rules=[
            Rule(
                name="process_payment",
                condition=lambda d: d.get("amount", 0) > 0,
                escalate_if=fraud_check,  # classifier-based escalation
                action=lambda d: {"processed": True},
            )
        ]
    )
    result = await half.run(
        fresh_session,
        {"data": {"amount": 100, "transaction": "suspicious_pattern"}},
    )
    assert not result.success
    assert result.next_action == "escalate"
    assert "fraud_detector" in result.output["verifier_reason"]


@pytest.mark.asyncio
async def test_structured_half_mixed_verifier_and_lambda_rules(
    fresh_session,
) -> None:
    """You can mix rule types freely — StructuredHalf doesn't care."""
    # Rule 1: deterministic, lambda.
    # Rule 2: verifier-backed.
    clf = _FakeSklearnClassifier(prob_positive=0.85)
    polite = ClassifierVerifier(
        classifier=clf,
        input_builder=lambda d: d.get("text", ""),
        threshold=0.8,
    )

    half = StructuredHalf(
        rules=[
            Rule(
                name="explicit_approval",
                condition=lambda d: d.get("status") == "approved",
                action=lambda d: {"via": "explicit"},
            ),
            Rule(
                name="polite_enough",
                condition=polite,
                action=lambda d: {"via": "polite"},
            ),
        ]
    )

    # First data triggers rule 1.
    r1 = await half.run(fresh_session, {"data": {"status": "approved"}})
    assert r1.success and r1.output["result"]["via"] == "explicit"

    # Second data triggers rule 2.
    r2 = await half.run(fresh_session, {"data": {"status": "pending", "text": "thanks!"}})
    assert r2.success and r2.output["result"]["via"] == "polite"


@pytest.mark.asyncio
async def test_structured_half_verifier_exception_escalates(
    fresh_session,
) -> None:
    """If a Verifier's evaluate() itself raises (not just returns ok=False
    with a reason), the rule must escalate cleanly — never propagate."""

    class _ExplodingVerifier:
        async def evaluate(self, data):  # type: ignore[no-untyped-def]
            raise RuntimeError("kaboom")

    half = StructuredHalf(
        rules=[
            Rule(
                name="will_explode",
                condition=_ExplodingVerifier(),  # type: ignore[arg-type]
                action=lambda d: {},
            )
        ]
    )
    result = await half.run(fresh_session, {"data": {"x": 1}})
    assert not result.success
    assert result.next_action == "escalate"
    assert "condition raised" in result.summary
