"""A setup challenge discovers a private sender without treating a display name as identity."""

import copy
import runpy

import pytest

MATCH = runpy.run_path("book/always_on/appendices/telegram_identity_v1.py")["matching_operators"]


def message(actor=123, text="unpredictable-setup-challenge"):
    return {
        "update_id": 1,
        "message": {
            "from": {"id": actor, "is_bot": False},
            "chat": {"id": actor, "type": "private"},
            "text": text,
        },
    }


def test_exact_private_challenge_and_repeated_delivery_identify_one_account():
    incoming = message()
    assert MATCH([incoming, copy.deepcopy(incoming)], "unpredictable-setup-challenge") == 123
    assert MATCH([incoming], "another-challenge") is None
    assert MATCH([], "unpredictable-setup-challenge") is None


@pytest.mark.parametrize(
    "changed", ["group", "bot", "boolean_sender", "boolean_chat", "other_chat", "malformed_sender"]
)
def test_unqualified_sender_is_not_discovered(changed):
    incoming = message(actor=1)
    data = incoming["message"]
    if changed == "group":
        data["chat"]["type"] = "group"
    elif changed == "bot":
        data["from"]["is_bot"] = True
    elif changed == "boolean_sender":
        data["from"]["id"] = True
    elif changed == "boolean_chat":
        data["chat"]["id"] = True
    elif changed == "other_chat":
        data["chat"]["id"] = 999
    else:
        data["from"] = []
    assert MATCH([incoming], "unpredictable-setup-challenge") is None


def test_multiple_accounts_and_oversized_batches_are_refused():
    with pytest.raises(ValueError, match="multiple accounts"):
        MATCH([message(123), message(456)], "unpredictable-setup-challenge")
    with pytest.raises(ValueError, match="batch"):
        MATCH([message()] * 101, "unpredictable-setup-challenge")
