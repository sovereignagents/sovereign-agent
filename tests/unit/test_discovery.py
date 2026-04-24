"""Tests for the Discovery protocol (Pattern A)."""

from __future__ import annotations

import pytest

from sovereign_agent.discovery import Discoverable, discover_all, discoverable, validate_schema
from sovereign_agent.errors import ValidationError


def _valid_schema() -> dict:
    return {
        "name": "t",
        "kind": "tool",
        "description": "x",
        "parameters": {"type": "object"},
        "returns": {"type": "object"},
        "error_codes": [],
        "examples": [{"input": {}, "output": {}}],
        "version": "0.1.0",
    }


def test_valid_schema_passes() -> None:
    validate_schema(_valid_schema())


def test_missing_required_field_fails() -> None:
    s = _valid_schema()
    del s["name"]
    with pytest.raises(ValidationError):
        validate_schema(s)


def test_empty_examples_fails() -> None:
    s = _valid_schema()
    s["examples"] = []
    with pytest.raises(ValidationError):
        validate_schema(s)


def test_invalid_kind_fails() -> None:
    s = _valid_schema()
    s["kind"] = "not-a-kind"
    with pytest.raises(ValidationError):
        validate_schema(s)


def test_non_dict_fails() -> None:
    with pytest.raises(ValidationError):
        validate_schema("not a dict")  # type: ignore[arg-type]


def test_discoverable_decorator_catches_missing_method() -> None:
    with pytest.raises(TypeError):

        @discoverable  # type: ignore[arg-type]
        class BadExtension:
            name = "bad"


def test_discoverable_decorator_accepts_good_class() -> None:
    @discoverable
    class GoodExtension:
        name = "good"

        def discover(self) -> dict:
            return _valid_schema()

    assert GoodExtension().name == "good"


def test_discover_all_returns_one_schema_per_extension() -> None:
    class Ext:
        def __init__(self, n: str) -> None:
            self.name = n

        def discover(self) -> dict:
            s = _valid_schema()
            s["name"] = self.name
            return s

    out = discover_all([Ext("a"), Ext("b"), Ext("c")])
    assert [o["name"] for o in out] == ["a", "b", "c"]


def test_discoverable_protocol_runtime_check() -> None:
    class Thing:
        name = "x"

        def discover(self) -> dict:
            return _valid_schema()

    assert isinstance(Thing(), Discoverable)
