"""Tests for the structured error taxonomy (Pattern C)."""

from __future__ import annotations

import pytest

from sovereign_agent.errors import (
    CANONICAL_CODES,
    ErrorCategory,
    ExternalError,
    SystemError,
    ToolError,
    ValidationError,
    is_canonical,
    wrap_unexpected,
)


def test_code_category_prefix_consistency() -> None:
    for category, codes in CANONICAL_CODES.items():
        prefix = f"SA_{category.value}_"
        for code in codes:
            assert code.startswith(prefix), (code, category)


def test_agents_can_branch_on_category() -> None:
    errors = [
        SystemError(code="SA_SYS_OOM", message="oom"),
        ValidationError(code="SA_VAL_BAD_TYPE", message="bad type"),
        ExternalError(code="SA_EXT_RATE_LIMITED", message="rl"),
        ToolError(code="SA_TOOL_EXECUTION_FAILED", message="fail"),
    ]
    categories = [e.category for e in errors]
    assert categories == [
        ErrorCategory.SYS,
        ErrorCategory.VAL,
        ErrorCategory.EXT,
        ErrorCategory.TOOL,
    ]


def test_code_category_mismatch_rejected() -> None:
    # You cannot instantiate a ValidationError with a SA_SYS_ code.
    with pytest.raises(ValueError):
        ValidationError(code="SA_SYS_OOM", message="wrong prefix")


def test_wrap_unexpected_preserves_cause() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        wrapped = wrap_unexpected(exc)
    assert isinstance(wrapped, SystemError)
    assert wrapped.code == "SA_SYS_UNEXPECTED"
    assert wrapped.cause is not None
    assert "boom" in wrapped.message


def test_wrap_unexpected_does_not_double_wrap() -> None:
    original = ValidationError(code="SA_VAL_BAD_TYPE", message="x")
    assert wrap_unexpected(original) is original


def test_external_error_defaults_retriable() -> None:
    e = ExternalError(code="SA_EXT_TIMEOUT", message="slow")
    assert e.retriable is True


def test_validation_error_not_retriable_by_default() -> None:
    e = ValidationError(code="SA_VAL_BAD_TYPE", message="x")
    assert e.retriable is False


def test_is_canonical() -> None:
    assert is_canonical("SA_EXT_RATE_LIMITED")
    assert not is_canonical("SA_CUSTOM_FOO")


def test_to_dict_serializable() -> None:
    import json

    e = ValidationError(code="SA_VAL_BAD_TYPE", message="x", context={"k": 1})
    d = e.to_dict()
    # round-trips as JSON
    json.dumps(d)
    assert d["code"] == "SA_VAL_BAD_TYPE"
    assert d["category"] == "VAL"
    assert d["retriable"] is False


def test_sovereign_error_str_includes_code() -> None:
    e = ToolError(code="SA_TOOL_NOT_FOUND", message="nope")
    assert "SA_TOOL_NOT_FOUND" in str(e)
    assert "nope" in str(e)
