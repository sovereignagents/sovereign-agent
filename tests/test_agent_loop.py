"""Independent edge cases for the learner-owned loop and its real shop tools."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from reference_organizations.store.agent import OfflineShopModel, seed_lucy, shop_dispatcher
from sovereign_agent.agent_loop import Limits, run_loop
from sovereign_agent.database import Database
from sovereign_agent.model_turn import Message, ModelError, ModelTurn, ToolCall
from sovereign_agent.tool_dispatch import Dispatcher, ExecutableTool


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    quantity: int


class Script:
    def __init__(self, *turns: ModelTurn) -> None:
        self.turns = iter(turns)
        self.inputs: list[list[Message]] = []

    def complete(
        self,
        messages: list[Message],
        tools: list[Message],
        *,
        timeout: float,
        max_output_tokens: int,
    ) -> ModelTurn:
        self.inputs.append(copy.deepcopy(messages))
        return next(self.turns)


def call(identity: str = "a", name: str = "count", quantity: object = 2) -> ToolCall:
    return ToolCall(id=identity, name=name, arguments={"quantity": quantity})


def dispatcher(seen: list[int], *, consequential: bool = False) -> Dispatcher:
    return Dispatcher(
        [
            ExecutableTool(
                "count",
                "Count",
                Args,
                lambda args: seen.append(args.quantity) or args.quantity,
                consequential,
            )
        ],
        allowed=frozenset({"count"}),
    )


def test_loop_feeds_observation_to_model_without_mutating_input() -> None:
    model = Script(ModelTurn(calls=(call(),)), ModelTurn("two"))
    seen: list[int] = []
    original = [{"role": "user", "content": "count"}]
    result = run_loop(model, dispatcher(seen), original)
    assert result.status == "COMPLETED" and result.answer == "two"
    assert seen == [2] and len(original) == 1
    assert model.inputs[1][-1]["tool_call_id"] == "a"
    assert '"value": 2' in model.inputs[1][-1]["content"]


@pytest.mark.parametrize(
    "requested", [call(name="missing"), call(quantity=True), call(quantity="2"), call(quantity=2.5)]
)
def test_bad_arguments_and_unknown_tools_never_invoke_handler(requested: ToolCall) -> None:
    seen: list[int] = []
    assert dispatcher(seen).invoke(requested)["ok"] is False
    assert not seen


def test_no_write_authority_and_duplicate_batch_do_not_call_handler() -> None:
    seen: list[int] = []
    assert (
        dispatcher(seen, consequential=True).invoke(call())["error"] == "write_authority_required"
    )
    result = run_loop(Script(ModelTurn(calls=(call(), call()))), dispatcher(seen), [])
    assert result.status == "REPEATED_CALL_ID" and not seen


def test_repeated_call_from_later_turn_does_not_repeat_tool() -> None:
    seen: list[int] = []
    result = run_loop(
        Script(ModelTurn(calls=(call(),)), ModelTurn(calls=(call(),))), dispatcher(seen), []
    )
    assert result.status == "REPEATED_CALL_ID" and seen == [2]


def test_limits_stop_before_model_or_before_batch() -> None:
    seen: list[int] = []
    model = Script()
    result = run_loop(
        model,
        dispatcher(seen),
        [{"role": "user", "content": "x" * 200}],
        limits=Limits(context_bytes=100),
    )
    assert result.status == "CONTEXT_LIMIT" and not model.inputs
    result = run_loop(
        Script(ModelTurn(calls=(call("a"), call("b")))),
        dispatcher(seen),
        [],
        limits=Limits(tool_calls=1),
    )
    assert result.status == "TOOL_LIMIT" and not seen
    result = run_loop(
        Script(ModelTurn(calls=(call(),))), dispatcher(seen), [], limits=Limits(model_calls=1)
    )
    assert result.status == "MODEL_CALL_LIMIT"


def test_late_model_response_does_not_execute_tools() -> None:
    ticks = iter([0.0, 0.0, 0.0, 2.0])
    seen: list[int] = []
    result = run_loop(
        Script(ModelTurn(calls=(call(),))),
        dispatcher(seen),
        [],
        limits=Limits(seconds=1),
        clock=lambda: next(ticks),
    )
    assert result.status == "TIME_LIMIT" and not seen


def test_oversized_result_is_not_forwarded_and_failures_are_bounded() -> None:
    d = Dispatcher(
        [ExecutableTool("count", "Count", Args, lambda _: "x" * 1000)],
        allowed=frozenset({"count"}),
        max_result_bytes=128,
    )
    assert d.invoke(call()) == {"ok": False, "error": "result_too_large"}
    result = run_loop(Script(ModelTurn(output_tokens=2000)), d, [])
    assert result.status == "INVALID_USAGE"


def test_empty_tools_can_still_answer() -> None:
    result = run_loop(Script(ModelTurn("Hello")), Dispatcher([], allowed=frozenset()), [])
    assert result.answer == "Hello" and result.tool_calls == 0


def test_lucy_draft_uses_sqlite_observations_and_changes_no_stock(tmp_path: Path) -> None:
    db = Database(tmp_path / "shop.db")
    seed_lucy(db)
    before = list(db.connection.execute("SELECT sku,on_hand FROM inventory ORDER BY sku"))
    result = run_loop(
        OfflineShopModel(),
        shop_dispatcher(db),
        [{"role": "user", "content": "What should Lucy order?"}],
    )
    assert result.status == "COMPLETED"
    assert "SKU-VANILLA: 6 units, 1500 pence GBP" in result.answer
    assert "SKU-STRAWBERRY: 4 units, 1100 pence GBP" in result.answer
    assert "SKU-CHOCOLATE" not in result.answer
    assert [tuple(x) for x in before] == [
        tuple(x) for x in db.connection.execute("SELECT sku,on_hand FROM inventory ORDER BY sku")
    ]
    with db.transaction():
        db.connection.execute("UPDATE inventory SET on_hand=9 WHERE sku='SKU-VANILLA'")
    seed_lucy(db)
    result = run_loop(
        OfflineShopModel(), shop_dispatcher(db), [{"role": "user", "content": "What now?"}]
    )
    assert "SKU-VANILLA" not in result.answer
    db.close()


def test_model_failure_has_a_terminal_result() -> None:
    class Broken(Script):
        def complete(self, *args: object, **kwargs: object) -> ModelTurn:
            raise ModelError("unreachable")

    result = run_loop(Broken(), Dispatcher([], allowed=frozenset()), [])
    assert result.status == "MODEL_FAILED"
