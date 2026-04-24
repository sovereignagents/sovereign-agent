# Lesson: <short descriptive title>

**Paper:** *<Paper title>* — <authors>, <year>. arXiv:<id>.

**Status:** <draft | published | deprecated>.

**Related chapters:** chapter_XX_<slug> (if any).

**Related extensions:** `sovereign_agent/<path>/<file>.py`.

## Hypothesis

One paragraph. What did we expect to see when we implemented this here? Why is this question worth asking?

## Implementation

How did the paper's technique translate into a sovereign-agent extension? What was straightforward? What required adaptation? If any of the paper's assumptions don't hold in our setup, say so here.

Point at the specific files the new implementation lives in:

- `sovereign_agent/<path>/<module>.py` — the new class/function
- `tests/unit/test_<thing>.py` — unit tests for the new code
- `lessons/<slug>/implementation.py` — this lesson's re-export

## Setup

- **Scenarios tested:** list them. Reuse `examples/` scenarios where possible so lessons are comparable across time.
- **Baseline:** the existing sovereign-agent extension this replaces or augments.
- **Variant:** the new extension.
- **Metrics:** which signals are we actually measuring? (plan_coherence, total_tool_calls, final_success_rate, planner_tokens_in, wall_clock_ms, etc.)
- **Runs per condition:** at least 3 to give a sense of variance. More if the metric is noisy.
- **Seeds / temperature:** temperature=0 where possible for reproducibility.

## Results

A brief table — baseline column vs. variant column — across your chosen metrics. Then a paragraph or two of prose interpretation. Be specific and honest. If the variant didn't help, or helped only on some scenarios, say so.

| Metric | Baseline | Variant | Notes |
|---|---|---|---|
| example | 0.00 | 0.00 | |

## What we learned

One or two sentences that would still be worth reading a year from now. This is the payload of the lesson — everything else is scaffolding.

## When to use this

Practical guidance. A reader scanning the lessons feed should be able to decide in under a minute whether this technique applies to their problem.

## Pointers

- arXiv: <link>
- Code: `sovereign_agent/<path>/<file>.py`
- Related lessons: `lessons/YYYY-MM-<other-slug>/`
