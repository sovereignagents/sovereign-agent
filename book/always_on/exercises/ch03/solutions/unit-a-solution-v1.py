"""Instructor solution for Chapter 3 Unit A. Excluded from the student release."""


def decide_admission(case):
    if case["used_calls"] >= case["max_calls"]:
        return "MODEL_CALL_LIMIT"
    if case["spent"] + case["next_cost"] > case["budget"]:
        return "MODEL_COST_LIMIT"
    return "CALL"
