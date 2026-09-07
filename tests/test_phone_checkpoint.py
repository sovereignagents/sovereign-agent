"""The phone checkpoint resumes durable intake and attributes outbox results by work ID."""

import json
import runpy
import sys
from pathlib import Path

from sovereign_agent.assistant_work import claim, finish
from sovereign_agent.database import Database
from sovereign_agent.telegram_channel import poll


def test_live_channel_entrypoint_resumes_prior_intake_and_delivers_existing_outbox(
    tmp_path, monkeypatch, capsys
):
    namespace = runpy.run_path(str(Path("book/always_on/checkpoints/ch06.py")))
    bot = namespace["OfflineBot"]([namespace["update"](1), namespace["update"](2)])
    db = namespace["initialize"](tmp_path / "agent.sqlite")
    ids = poll(db, bot, frozenset({123}))
    first = claim(db, "prior-worker", identifier=ids[0])
    finish(db, first, "DONE", "An earlier completed brief.")
    db.close()
    # A fresh process gets no new update IDs. Both its pending intake and the
    # earlier output still have to be read from durable records.
    bot.updates = []
    entrypoint = namespace["main"]
    monkeypatch.setitem(entrypoint.__globals__, "Telegram", lambda _: bot)
    monkeypatch.setenv("SOVEREIGN_AGENT_TELEGRAM_TOKEN", "123:TEST_ONLY")
    monkeypatch.setenv("SOVEREIGN_AGENT_OPERATORS", "123")
    monkeypatch.setattr(sys, "argv", ["ch06.py", "--telegram", "--root", str(tmp_path)])
    assert entrypoint() == 0
    output = capsys.readouterr().out
    report = json.loads(output[output.index("{") :])
    assert report["results"] == [{"work": ids[1], "draft_evidence": True, "delivery": "SENT"}]
    assert report["outbox_observations"] == ["SENT", "SENT"]
    assert len(bot.sent) == 2
    db = Database(tmp_path / "agent.sqlite")
    assert dict(db.connection.execute("SELECT id,delivery FROM assistant_work")) == dict.fromkeys(
        ids, "SENT"
    )
    db.close()
    assert entrypoint() == 1  # No work or delivery is silently counted as a new success.
    assert len(bot.sent) == 2
