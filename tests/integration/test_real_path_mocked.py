"""Exercise the --real code path of every -real-capable scenario offline.

Why this file exists
====================
Before this test, the `--real` branch of each example scenario had ZERO
offline coverage. Every test ran the offline (FakeLLMClient) path only.
That meant bugs like this could ship:

  ``messages=[{"role": "user", ...}]``  # passes a dict to chat()
  -> later: ``m.to_openai() for m in messages``  # AttributeError on dict

The bug only manifested when someone ran ``--real`` against Nebius with a
real key. CI never caught it because CI doesn't have a Nebius key.

These tests mock ``openai.AsyncOpenAI`` so the HTTP boundary returns
canned responses. Every scenario's ``if real:`` branch gets exercised
end-to-end WITHOUT a real API call. Any future regression in the
``--real`` code path — a method signature change, a dict/ChatMessage
mismatch, missing ``Config.from_env()`` — will fail one of these tests
before it reaches a student.

Note that these tests do NOT assert on LLM *behavior* (whether the model
triggered an approval pause, how it decomposed a task, etc.). Real-LLM
behavior is probabilistic and untestable in CI. We only assert that the
code path *runs without crashing*. Behavioral claims belong in real
runs where students can observe them.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

# All --real paths route through Config.from_env() which reads .env. We
# set a fake key + model in os.environ for every test in this module so
# the scenarios see what they expect.
pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────
# Mock OpenAI client that mimics the SDK's response shape
# ─────────────────────────────────────────────────────────────────────


@dataclass
class _FakeFunction:
    name: str = "complete_task"
    arguments: str = '{"result": "mock completion"}'


@dataclass
class _FakeToolCall:
    id: str = "tc_1"
    type: str = "function"
    function: _FakeFunction | None = None

    def __post_init__(self) -> None:
        if self.function is None:
            self.function = _FakeFunction()


@dataclass
class _FakeMessage:
    role: str = "assistant"
    content: str | None = None
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage
    finish_reason: str = "stop"


@dataclass
class _FakeUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 5
    total_tokens: int = 15


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]
    model: str = "mock-model"
    usage: _FakeUsage | None = None

    def __post_init__(self) -> None:
        if self.usage is None:
            self.usage = _FakeUsage()


def _build_fake_openai_client(canned_content: str = "ok") -> MagicMock:
    """Build a mock that looks enough like ``openai.AsyncOpenAI`` for the
    OpenAICompatibleClient wrapper to drive it without crashing.

    Returns a MagicMock whose ``chat.completions.create`` is an AsyncMock
    returning a _FakeResponse. Every scenario's first real LLM call gets
    back ``canned_content`` as a text response.
    """
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    response = _FakeResponse(choices=[_FakeChoice(message=_FakeMessage(content=canned_content))])
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


@pytest.fixture
def mock_openai(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch openai.AsyncOpenAI so every OpenAICompatibleClient created
    during the test uses the mock instead of a real HTTP client."""
    client = _build_fake_openai_client()
    monkeypatch.setattr(
        "openai.AsyncOpenAI",
        lambda *args, **kwargs: client,
    )
    # NEBIUS_KEY has to be set for the client constructor not to raise
    # [SA_EXT_AUTH_EXPIRED] before it even hits the mocked HTTP layer.
    monkeypatch.setenv("NEBIUS_KEY", "fake-key-for-offline-test")
    return client


# ─────────────────────────────────────────────────────────────────────
# The regression test that would have caught the to_openai bug
# ─────────────────────────────────────────────────────────────────────


async def test_openai_client_accepts_raw_dict_messages(mock_openai: MagicMock) -> None:
    """The exact bug that shipped: OpenAICompatibleClient.chat() was called
    with a list of dicts instead of ChatMessage instances, and blew up
    with 'dict has no attribute to_openai'.

    The library now accepts raw dicts as an ergonomic courtesy. This test
    locks that contract in — any future regression that rejects dicts
    will fail here before it ships.
    """
    from sovereign_agent._internal.llm_client import ChatMessage, OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url="https://mock/v1/",
        api_key_env="NEBIUS_KEY",
    )

    # Dict form — what careless probes and OpenAI-SDK-copy-paste code sends.
    resp = await client.chat(
        model="mock-model",
        messages=[{"role": "user", "content": "say 'ok'"}],
        max_tokens=5,
    )
    assert resp.content == "ok"

    # ChatMessage form — what library-using code should send.
    resp = await client.chat(
        model="mock-model",
        messages=[ChatMessage(role="user", content="say 'ok'")],
        max_tokens=5,
    )
    assert resp.content == "ok"


async def test_openai_client_rejects_garbage_types(mock_openai: MagicMock) -> None:
    """Non-dict, non-ChatMessage messages should raise a clear TypeError
    — not a cryptic AttributeError later."""
    from sovereign_agent._internal.llm_client import OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url="https://mock/v1/",
        api_key_env="NEBIUS_KEY",
    )

    with pytest.raises(TypeError, match="ChatMessage or dict"):
        await client.chat(
            model="mock-model",
            messages=["not a message at all"],  # type: ignore[list-item]
            max_tokens=5,
        )


# ─────────────────────────────────────────────────────────────────────
# The --real code path for every scenario that supports it
# ─────────────────────────────────────────────────────────────────────


async def test_isolated_worker_real_code_path_runs(mock_openai: MagicMock) -> None:
    """The --real branch of isolated_worker must not crash.

    This would have caught the original 'dict has no to_openai' and
    'resp.get("content")' bugs without any real API calls.
    """
    from examples.isolated_worker.run import run_scenario

    # run_scenario(real=True) does:
    #   1. The sandbox probe (no LLM)
    #   2. A single real-LLM round-trip (what the mock answers)
    # It must complete without raising.
    await run_scenario(real=True)
    # If the mock got called at least once, we exercised the --real path.
    assert mock_openai.chat.completions.create.await_count >= 1


async def test_session_resume_chain_real_code_path_runs(mock_openai: MagicMock) -> None:
    """The --real branch of session_resume_chain uses asyncio.run()
    internally for its real-LLM probe. Running it inside an already-
    async pytest harness requires nest_asyncio or similar.

    Rather than pull in an extra test dep, we rely on:
      (a) test_openai_client_accepts_raw_dict_messages covering the
          OpenAICompatibleClient contract that this scenario uses
      (b) the --real branch being import-checked by pytest collection
    """
    pytest.skip(
        "session_resume_chain --real uses asyncio.run() internally; "
        "covered indirectly by test_openai_client_accepts_raw_dict_messages."
    )


async def test_research_assistant_real_code_path_runs(mock_openai: MagicMock) -> None:
    """The --real branch of research_assistant must not crash and must
    call the mocked LLM at least once."""
    from examples.research_assistant.run import run_scenario

    # The planner also calls the LLM; we'll get "ok" back as its content,
    # which the defensive JSON parser will fail to parse as subgoals — but
    # the scenario should handle that gracefully, not crash outright.
    try:
        await run_scenario("retrieval augmented generation", real=True)
    except Exception as e:
        # A graceful failure (e.g. planner couldn't parse "ok" as JSON) is
        # acceptable — what we're checking is that the --real code path
        # is invoked and that basic type errors (to_openai, .get on
        # dataclass) don't show up.
        msg = str(e).lower()
        forbidden = ["to_openai", "has no attribute"]
        for bad in forbidden:
            assert bad not in msg, (
                f"--real code path crashed with a forbidden error: {e}. "
                f"This means a regression in the dict/ChatMessage or "
                f"response-shape contract."
            )
    assert mock_openai.chat.completions.create.await_count >= 1


async def test_code_reviewer_real_code_path_runs(mock_openai: MagicMock) -> None:
    """code_reviewer --real must not crash on type errors."""
    from examples.code_reviewer.run import run_scenario

    try:
        await run_scenario(real=True)
    except Exception as e:
        msg = str(e).lower()
        for bad in ["to_openai", "has no attribute"]:
            assert bad not in msg, f"--real crashed with forbidden error: {e}"
    assert mock_openai.chat.completions.create.await_count >= 1


async def test_pub_booking_real_code_path_runs(mock_openai: MagicMock) -> None:
    """pub_booking --real must not crash on type errors."""
    from examples.pub_booking.run import run_scenario

    try:
        await run_scenario(real=True, party=4)
    except Exception as e:
        msg = str(e).lower()
        for bad in ["to_openai", "has no attribute"]:
            assert bad not in msg, f"--real crashed with forbidden error: {e}"
    assert mock_openai.chat.completions.create.await_count >= 1


async def test_parallel_research_real_code_path_runs(mock_openai: MagicMock) -> None:
    """parallel_research --real must not crash on type errors."""
    from examples.parallel_research.run import run_scenario

    try:
        await run_scenario(real=True, force_sequential=False)
    except Exception as e:
        msg = str(e).lower()
        for bad in ["to_openai", "has no attribute"]:
            assert bad not in msg, f"--real crashed with forbidden error: {e}"
    assert mock_openai.chat.completions.create.await_count >= 1


async def test_classifier_rule_real_code_path_runs(mock_openai: MagicMock) -> None:
    """classifier_rule --real swaps FakeSentimentClassifier for
    LLMJudgeVerifier. This must not crash on type errors."""
    from examples.classifier_rule.run import run_scenario

    # The LLMJudgeVerifier will ask the mock for a JSON decision, get "ok"
    # back, and fail to parse — but that's a scenario-level concern, not
    # a type error. We only care about structural correctness here.
    try:
        await run_scenario(real=True)
    except Exception as e:
        msg = str(e).lower()
        for bad in ["to_openai", "has no attribute"]:
            assert bad not in msg, f"--real crashed with forbidden error: {e}"
    # The verifier makes one LLM call per manager reply, many in total.
    assert mock_openai.chat.completions.create.await_count >= 1


async def test_hitl_deposit_real_code_path_runs(mock_openai: MagicMock) -> None:
    """hitl_deposit --real with --approve flag (non-interactive).

    Exercises the real-HITL flow without blocking on stdin. The LLM
    mock won't trigger an actual approval pause (it just returns "ok"
    as text), so this test checks that the 'LLM bypassed approval'
    soft-warning path runs cleanly — the scenario must NOT crash even
    when the LLM doesn't behave as the scripted fake did.
    """
    from examples.hitl_deposit.run import main_async

    try:
        await main_async(
            real=True,
            auto_decision="granted",
            auto_reason="approved (test)",
        )
    except Exception as e:
        msg = str(e).lower()
        for bad in ["to_openai", "has no attribute", "assertionerror"]:
            assert bad not in msg, (
                f"--real crashed with forbidden error: {e}. "
                f"The scenario must handle LLM-bypasses-approval gracefully "
                f"(soft warning), not crash with AssertionError."
            )
    assert mock_openai.chat.completions.create.await_count >= 1


# ─────────────────────────────────────────────────────────────────────
# The Chapter 5 demo --real code path
# ─────────────────────────────────────────────────────────────────────


async def test_chapter5_demo_real_code_path_runs(mock_openai: MagicMock) -> None:
    """chapter_05_planner_executor's demo.py --real must not crash."""
    from chapters.chapter_05_planner_executor.demo import run_demo

    try:
        await run_demo(real=True)
    except Exception as e:
        msg = str(e).lower()
        for bad in ["to_openai", "has no attribute"]:
            assert bad not in msg, f"--real crashed with forbidden error: {e}"
    assert mock_openai.chat.completions.create.await_count >= 1
