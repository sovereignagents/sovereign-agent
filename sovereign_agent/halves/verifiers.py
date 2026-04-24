"""Verifiers: pluggable truth-tests for rules and tool arguments (v0.2, Module 4).

## Why this exists

In v0.1.0, `Rule.condition` was a lambda:

    Rule(
        name="deposit_ok",
        condition=lambda d: d["deposit_gbp"] <= 300,
        action=_confirm_booking,
    )

This works for arithmetic, but rules in real scenarios often need to decide
things that aren't simple numbers:

  * "Is this email polite?" — a classifier's job.
  * "Is this SQL query safe to execute?" — another model or a rule engine.
  * "Does this argument match the customer's stated constraints?" — an
    LLM judge.

A lambda can't do these things cleanly. You end up either:
  1. Smuggling a model call into the lambda body (makes the rule untestable
     in isolation, couples the half to a specific client), or
  2. Moving the decision out of StructuredHalf entirely (loses the
     audit-trail benefits and the escalation path).

`Verifier` is the interface that lets you plug in any decision procedure —
deterministic, classifier-based, LLM-based — and have StructuredHalf treat
them uniformly. `Rule.condition` and `Rule.escalate_if` both accept either
a plain callable (backwards-compatible) or a `Verifier`.

## The protocol

Every verifier answers one question: given `data`, should this rule fire?

    class Verifier(Protocol):
        async def evaluate(self, data: dict) -> VerifierResult: ...

The return is a dataclass, not a bool. This matters:

  * Rules need to log WHY they matched or didn't — for debugging and for
    compliance. A bare bool throws away that information.
  * Classifier-based verifiers have confidence scores that belong in the
    trace.
  * LLM judges have reasons that are extremely useful during development.

## Built-in verifiers

  LambdaVerifier(fn): wraps a `(data) -> bool` for the common case.
  ClassifierVerifier(classifier, threshold): wraps anything exposing a
    `predict_proba(text)` interface (sklearn, transformers pipelines).
  LLMJudgeVerifier(client, model, prompt_template): wraps an LLM with a
    judging prompt. Returns structured JSON { "decision": bool, "reason": str }.

Each is a thin adapter. None of them reach out to the network at import
time — you pass in the classifier or client when you build the verifier.

See docs/verifiers.md for extended examples.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from sovereign_agent._internal.llm_client import ChatMessage, LLMClient


@dataclass
class VerifierResult:
    """Structured answer from a Verifier.

    Fields:
      ok: the bool the calling code uses as "did the rule fire?"
      reason: short human-readable explanation (always filled in).
      score: optional numeric score — only set by probabilistic verifiers.
        Range and meaning are verifier-specific; compare against thresholds
        documented by that verifier. Pure deterministic checks should leave
        this as None.
      raw: optional verifier-specific raw output, kept for debugging.
        Do NOT rely on its shape in production code.
    """

    ok: bool
    reason: str = ""
    score: float | None = None
    raw: dict | None = None


@runtime_checkable
class Verifier(Protocol):
    """The v0.2 interface for rule conditions and escalation checks.

    Implementers provide a single async method. Sync wrappers are fine
    via LambdaVerifier. See module docstring for rationale.
    """

    async def evaluate(self, data: dict) -> VerifierResult: ...


# ---------------------------------------------------------------------------
# Built-in verifiers
# ---------------------------------------------------------------------------


class LambdaVerifier:
    """Wraps a plain `(data) -> bool` callable as a Verifier.

    This is what StructuredHalf uses internally to preserve backwards
    compatibility with existing rules whose `condition` is a lambda.

    Example:
        LambdaVerifier(lambda d: d["deposit_gbp"] <= 300, name="deposit_under_300")
    """

    def __init__(
        self,
        fn: Callable[[dict], bool],
        *,
        name: str | None = None,
    ) -> None:
        self.fn = fn
        self.name = name or getattr(fn, "__name__", "lambda")

    async def evaluate(self, data: dict) -> VerifierResult:
        try:
            ok = bool(self.fn(data))
        except Exception as exc:  # noqa: BLE001
            return VerifierResult(
                ok=False,
                reason=f"{self.name} raised {type(exc).__name__}: {exc}",
                raw={"error": str(exc)},
            )
        return VerifierResult(
            ok=ok,
            reason=f"{self.name} returned {ok}",
        )


class ClassifierVerifier:
    """Wraps a probabilistic classifier with a threshold.

    Expects `classifier` to expose either:
      * `predict_proba(input) -> list[float]` — first element is the
        score for the positive class (sklearn convention, threshold as
        a float in [0,1]), OR
      * `__call__(input) -> list[dict]` — returns [{"label": str, "score": float}]
        matching the transformers pipeline convention; the verifier
        fires if the top label is `positive_label` with score ≥ threshold.

    Which path we take is auto-detected at construction time. If neither
    attribute works, we raise at evaluate() time with a clear error.

    The `input_builder` lets you turn a rule's `data` dict into whatever
    the classifier expects (usually a string).

    Example (transformers pipeline):
        from transformers import pipeline
        sentiment = pipeline("text-classification", model="...")
        v = ClassifierVerifier(
            classifier=sentiment,
            input_builder=lambda d: d["email_body"],
            positive_label="POSITIVE",
            threshold=0.8,
        )
    """

    def __init__(
        self,
        classifier: Any,
        *,
        input_builder: Callable[[dict], Any],
        threshold: float = 0.5,
        positive_label: str | None = None,
        name: str | None = None,
    ) -> None:
        self.classifier = classifier
        self.input_builder = input_builder
        self.threshold = threshold
        self.positive_label = positive_label
        self.name = name or classifier.__class__.__name__
        # Detect the interface once.
        self._uses_predict_proba = hasattr(classifier, "predict_proba")
        # Don't eagerly call __call__ — it could be heavyweight. We'll
        # dispatch in evaluate().

    async def evaluate(self, data: dict) -> VerifierResult:
        try:
            model_input = self.input_builder(data)
        except Exception as exc:  # noqa: BLE001
            return VerifierResult(
                ok=False,
                reason=f"{self.name}: input_builder raised: {exc}",
                raw={"error": str(exc)},
            )

        try:
            if self._uses_predict_proba:
                # sklearn: predict_proba returns [[p_neg, p_pos]] for a
                # single sample. Be tolerant of either nested or flat.
                probs = self.classifier.predict_proba([model_input])[0]
                # Convention: last column is positive class.
                score = float(probs[-1])
                ok = score >= self.threshold
                return VerifierResult(
                    ok=ok,
                    reason=(
                        f"{self.name}: p(positive)={score:.3f} "
                        f"{'≥' if ok else '<'} threshold={self.threshold}"
                    ),
                    score=score,
                    raw={"probs": list(map(float, probs))},
                )
            # Fall back to calling the classifier directly
            # (transformers pipeline style).
            result = self.classifier(model_input)
            # transformers pipelines return [{"label": ..., "score": ...}]
            # but can also return a single dict. Normalise.
            if isinstance(result, list) and result:
                top = result[0]
            elif isinstance(result, dict):
                top = result
            else:
                return VerifierResult(
                    ok=False,
                    reason=f"{self.name}: unrecognised classifier output shape",
                    raw={"result": repr(result)[:200]},
                )
            label = top.get("label", "")
            score = float(top.get("score", 0.0))
            if self.positive_label is None:
                # If no positive_label was specified, we treat any top
                # result with score ≥ threshold as "ok". This is rarely
                # what you want — we log a warning in the reason.
                ok = score >= self.threshold
                return VerifierResult(
                    ok=ok,
                    reason=(
                        f"{self.name}: top label={label!r} score={score:.3f} "
                        f"{'≥' if ok else '<'} threshold={self.threshold} "
                        f"(no positive_label set — ANY label qualifies)"
                    ),
                    score=score,
                    raw={"top": top},
                )
            ok = label == self.positive_label and score >= self.threshold
            return VerifierResult(
                ok=ok,
                reason=(
                    f"{self.name}: label={label!r} score={score:.3f} "
                    f"(target={self.positive_label!r}, threshold={self.threshold})"
                ),
                score=score,
                raw={"top": top},
            )
        except Exception as exc:  # noqa: BLE001
            return VerifierResult(
                ok=False,
                reason=f"{self.name} raised {type(exc).__name__}: {exc}",
                raw={"error": str(exc)},
            )


class LLMJudgeVerifier:
    """Wraps an LLM as a verifier. The LLM receives a prompt built from
    `prompt_template.format(**data, rendered_data=...)` and is asked to
    return JSON with `decision` (bool) and `reason` (str).

    This is the "elm as judge" pattern: useful when the decision is
    fuzzy ("is this email polite?", "does this match the user's
    intent?") and you don't have a specialised classifier.

    IMPORTANT — TRADE-OFFS:
      * LLM judges are slower than classifiers (hundreds of ms to
        several seconds) and cost tokens.
      * They are non-deterministic at temperature > 0. Keep temperature
        at 0.0 for production use.
      * They can still hallucinate. A rule driven by an LLM judge
        should never be the LAST line of defence for a high-stakes
        action; combine with a deterministic check after.

    Example:
        judge = LLMJudgeVerifier(
            client=my_client,
            model="qwen3-235b-a22b-instruct",
            prompt_template=(
                "You are a compliance check. The following booking "
                "request was received:\\n\\n{rendered_data}\\n\\n"
                "Does it comply with our policies? Respond with JSON: "
                '{{"decision": true|false, "reason": "..."}}. '
                "Be strict; on any doubt return false."
            ),
        )
    """

    def __init__(
        self,
        *,
        client: LLMClient,
        model: str,
        prompt_template: str,
        name: str = "llm_judge",
        temperature: float = 0.0,
    ) -> None:
        self.client = client
        self.model = model
        self.prompt_template = prompt_template
        self.name = name
        self.temperature = temperature

    async def evaluate(self, data: dict) -> VerifierResult:
        rendered_data = json.dumps(data, indent=2, default=str)
        # Two-phase format: first try format() with data as kwargs (so
        # `{field}` substitutions work); always provide `rendered_data`
        # as a fallback for templates that just want the whole payload.
        try:
            prompt = self.prompt_template.format(**data, rendered_data=rendered_data)
        except (KeyError, IndexError):
            # Template referenced a field that's not in data. Fall
            # back to rendered_data-only substitution.
            prompt = self.prompt_template.replace("{rendered_data}", rendered_data)

        try:
            response = await self.client.chat(
                model=self.model,
                messages=[ChatMessage(role="user", content=prompt)],
                temperature=self.temperature,
            )
        except Exception as exc:  # noqa: BLE001
            return VerifierResult(
                ok=False,
                reason=f"{self.name}: LLM call failed: {exc}",
                raw={"error": str(exc)},
            )

        raw_content = (response.content or "").strip()
        # Defensive JSON parse — decision 7, the same reflex we use for
        # planner output. Strip markdown fences if present.
        parsed = _parse_judge_json(raw_content)
        if parsed is None:
            return VerifierResult(
                ok=False,
                reason=(
                    f"{self.name}: response was not parseable JSON. "
                    f"Treating as 'deny'. Raw: {raw_content[:200]}"
                ),
                raw={"raw_response": raw_content},
            )

        decision = bool(parsed.get("decision", False))
        reason = str(parsed.get("reason", ""))
        return VerifierResult(
            ok=decision,
            reason=f"{self.name}: {reason}" if reason else f"{self.name}: decision={decision}",
            raw={"raw_response": raw_content, "parsed": parsed},
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_judge_json(raw: str) -> dict | None:
    """Defensive JSON parser for LLM judge responses. Strips markdown
    fences and extracts the first {...} block if surrounding prose is
    present. Returns None on failure."""
    if not raw:
        return None
    s = raw.strip()
    # Strip ``` fences.
    if s.startswith("```"):
        # ```json\n{...}\n``` or ```\n{...}\n```
        parts = s.split("```")
        # Prefer the second block (after the opening fence).
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if stripped.startswith("{"):
                s = stripped
                break
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Last resort: find the first {...} block.
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return None


def as_verifier(x: Verifier | Callable[[dict], bool] | None) -> Verifier | None:
    """Normalise a rule's condition/escalate_if field into a Verifier.

    StructuredHalf uses this at rule-evaluation time so both legacy
    lambda-based rules and new Verifier-based rules work in the same loop.

      * None        → None (caller handles absent field)
      * Verifier    → returned unchanged
      * callable    → wrapped in a LambdaVerifier
    """
    if x is None:
        return None
    if isinstance(x, Verifier):
        return x
    if callable(x):
        return LambdaVerifier(x)
    raise TypeError(f"expected Verifier or callable(data)->bool, got {type(x).__name__}")


__all__ = [
    "ClassifierVerifier",
    "LLMJudgeVerifier",
    "LambdaVerifier",
    "Verifier",
    "VerifierResult",
    "as_verifier",
]
