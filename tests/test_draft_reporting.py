"""An unattended report must not replace a correct tool amount with model arithmetic."""

import json

import pytest

from reference_organizations.store.agent import OfflineShopModel, draft_report, seed_lucy
from reference_organizations.store.assistant import run_once
from reference_organizations.store.stock_conditions import scan, watch
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ModelTurn
from sovereign_agent.telegram_channel import deliver_one


def test_wrong_model_total_is_retained_for_evaluation_but_not_delivered(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    with db.immediate() as connection:
        connection.execute("UPDATE inventory SET on_hand=1 WHERE sku='SKU-VANILLA'")
    watch(
        db, "low", "telegram:render:123", "SKU-VANILLA", channel="telegram:render", recipient="123"
    )
    scan(db)

    class WrongTotal(OfflineShopModel):
        def complete(self, *args, **kwargs):
            result = super().complete(*args, **kwargs)
            return result if result.calls else ModelTurn("Seven tubs cost £15.00 GBP.")

    result = run_once(db, WrongTotal())
    assert result["status"] == "DONE"
    assert (
        result["answer"]
        == 'Draft estimates:\n- "SKU-VANILLA": 7 tubs, £17.50 GBP.\nTotal: £17.50 GBP.'
    )
    assert "£15.00" in result["loop"]["answer"]
    assert (
        db.connection.execute("SELECT result FROM assistant_work").fetchone()[0] == result["answer"]
    )

    class Bot:
        account = "render"
        sent = []

        def call(self, method, data):
            self.sent.append(data)
            return {"message_id": 1}

    bot = Bot()
    assert deliver_one(db, bot, frozenset({123})) == "SENT"
    assert bot.sent[0]["text"] == result["answer"]
    assert db.connection.execute("SELECT count(*) FROM assistant_orders").fetchone()[0] == 0
    db.close()


def observations(*drafts):
    messages = []
    for index, draft in enumerate(drafts):
        identifier = str(index)
        messages.extend(
            [
                {
                    "role": "assistant",
                    "tool_calls": [{"id": identifier, "function": {"name": "draft_order"}}],
                },
                {
                    "role": "tool",
                    "tool_call_id": identifier,
                    "content": json.dumps({"ok": True, "value": draft}),
                },
            ]
        )
    return messages


def draft(sku="V", quantity=6, amount=1500):
    return {"sku": sku, "quantity": quantity, "total_pence": amount, "currency": "GBP"}


def test_repeated_calculations_do_not_become_extra_orders_and_latest_estimate_wins():
    result = draft_report(
        observations(draft(), draft(), draft(quantity=7, amount=1750), draft("S", 4, 1100))
    )
    assert (
        result == 'Draft estimates:\n- "S": 4 tubs, £11.00 GBP.\n'
        '- "V": 7 tubs, £17.50 GBP.\nTotal: £28.50 GBP.'
    )
    assert draft_report([{"role": "assistant", "content": "I drafted V for £15.00."}]) is None


@pytest.mark.parametrize(
    "field,value", [("quantity", True), ("total_pence", 17.5), ("currency", "USD")]
)
def test_invalid_structured_amount_is_refused_instead_of_rendering_it(field, value):
    value_record = draft()
    value_record[field] = value
    with pytest.raises(ValueError, match="validated quantity or GBP"):
        draft_report(observations(value_record))


def test_product_data_cannot_insert_a_new_report_line():
    result = draft_report(observations(draft("V\nAPPROVED")))
    assert "V\\nAPPROVED" in result
    assert len(result.splitlines()) == 3
