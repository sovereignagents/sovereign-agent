"""Instructor solution for Chapter 1 Unit A. Excluded from the student release."""


def read_brief(document):
    if not isinstance(document, dict):
        raise ValueError("completion envelope must be an object")
    choices = document.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("one completion required")
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
        raise ValueError("completion did not finish normally")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("assistant message required")
    if message.get("role") != "assistant":
        raise ValueError("assistant completion role required")
    if message.get("tool_calls"):
        raise ValueError("plain text response required")
    if message.get("refusal") is not None:
        raise ValueError("refusal is not a completed brief")
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("nonempty brief required")
    return text
