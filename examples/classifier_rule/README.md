# Example: classifier rule

## What it shows

Module 4 in action. A StructuredHalf rule whose `condition` is a
`ClassifierVerifier` — a text classifier decides whether the rule
fires, not a hand-written lambda.

Six manager-reply strings are classified:

| Type | Expected | Example |
|---|---|---|
| Affirmative | fires `manager_confirmed` | "Yes, we'll do it. Book for 19:30." |
| Affirmative | fires `manager_confirmed` | "Confirmed. Deposit instructions attached." |
| Affirmative | fires `manager_confirmed` | "Sure, go ahead — all good on our side." |
| Negative | escalates | "Sorry, we can't host that night." |
| Negative | escalates | "Unable to accommodate — another time?" |
| Ambiguous | escalates | "Let me check with the kitchen and get back." |

Score `0.8` threshold: clearly-affirmative replies clear it, everything
else falls through to the escalation rule.

## Run

```bash
python -m examples.classifier_rule.run
```

No external dependencies. The classifier is a 20-line stand-in.

## Swapping in a real classifier

The example uses a `FakeSentimentClassifier` so it runs anywhere. In
production, replace just the one line:

```python
# Instead of:
classifier = FakeSentimentClassifier()

# Use one of:
from sklearn.pipeline import Pipeline
classifier = joblib.load("sentiment.joblib")   # sklearn path

# or:
from transformers import pipeline
classifier = pipeline(
    "text-classification",
    model="distilbert-base-uncased-finetuned-sst-2-english",
)
```

`ClassifierVerifier` auto-detects which interface you passed
(`predict_proba` vs callable returning `[{"label": ..., "score": ...}]`)
and handles both. The rest of the `Rule` and `StructuredHalf` code
does not change.

## The one line that matters

```python
Rule(
    name="manager_confirmed",
    condition=manager_affirmative,   # <-- ClassifierVerifier, not a lambda
    action=_commit_booking,
)
```

`Rule.condition` accepts either a callable (legacy — still works) or a
`Verifier` (new). The structured half handles the protocol mismatch
internally.

## What the audit trail shows

When the classifier rule fires, the structured half's output carries
the verifier's reasoning:

```json
{
  "rule": "manager_confirmed",
  "result": {"action": "committed", "venue": "Haymarket Tap"},
  "verifier_reason": "manager_affirmative: p(positive)=0.900 >= threshold=0.8",
  "verifier_score": 0.9
}
```

Six months later, a compliance reviewer opens `logs/trace.jsonl` and
sees exactly WHY this booking was committed, not just that it was.
This is the structural difference between "an LLM decided" and "a
classifier decided with 90% confidence."

## When to reach for each verifier type

| Verifier | Use when |
|---|---|
| `LambdaVerifier` | Numeric thresholds, whitelist checks — deterministic logic |
| `ClassifierVerifier` | Text classification with labelled training data |
| `LLMJudgeVerifier` | Fuzzy semantic checks that don't have enumerable criteria |

Speed, cost, and determinism all go down as you move down the list.
Use the simplest one that answers your actual question.
