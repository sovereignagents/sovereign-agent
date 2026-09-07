"""Malformed remote envelopes produce bounded model failure, not host exceptions."""

import json

import pytest

from sovereign_agent.agent_loop import run_loop
from sovereign_agent.http_transport import HTTPResult
from sovereign_agent.model_turn import HTTPModel
from sovereign_agent.tool_dispatch import Dispatcher


def envelope(message=None, *, usage=None, choices=None):
    return {
        "choices": choices
        if choices is not None
        else [
            {
                "finish_reason": "stop",
                "message": message if message is not None else {"content": "ok"},
            }
        ],
        "usage": usage if usage is not None else {"completion_tokens": 1},
    }


@pytest.mark.parametrize(
    "document",
    [
        [],
        None,
        envelope(choices=[]),
        envelope(choices=[[]]),
        envelope(choices=[{"message": {"content": "one"}}, {"message": {"content": "two"}}]),
        envelope(message=[]),
        envelope(usage=[]),
        envelope(message={"content": 0}),
        envelope(message={"content": False}),
        envelope(message={"tool_calls": {}}),
        envelope(message={"tool_calls": [None] * 33}),
    ],
)
def test_invalid_remote_shape_is_a_model_failure(monkeypatch, document):
    monkeypatch.setattr(
        "sovereign_agent.model_turn.request",
        lambda *args, **kwargs: HTTPResult(200, json.dumps(document).encode()),
    )
    result = run_loop(HTTPModel(), Dispatcher([], allowed=frozenset()), [])
    assert result.status == "MODEL_FAILED"
    assert result.model_calls == 1 and result.tool_calls == 0


def test_valid_single_reply_still_flows_through_the_owned_loop(monkeypatch):
    monkeypatch.setattr(
        "sovereign_agent.model_turn.request",
        lambda *args, **kwargs: HTTPResult(200, json.dumps(envelope()).encode()),
    )
    result = run_loop(HTTPModel(), Dispatcher([], allowed=frozenset()), [])
    assert result.status == "COMPLETED" and result.answer == "ok"
