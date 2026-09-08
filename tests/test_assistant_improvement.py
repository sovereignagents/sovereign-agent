"""A regressing candidate must not replace an active skill; rollback is evaluated."""

import json

import pytest

from reference_organizations.store.agent import OfflineShopModel
from reference_organizations.store.improvement import change_skill
from sovereign_agent.assistant_context import stage_skill
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ModelTurn


def test_candidate_evaluation_activation_and_rollback_retain_history(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    for version in ("1", "2", "3"):
        path = tmp_path / f"opening-{version}.toml"
        path.write_text(
            f'name = "opening"\nversion = "{version}"\n'
            'instructions = "Read stock and draft shortages in GBP."\n'
        )
        stage_skill(db, path)
    reports = tmp_path / "reports"
    with pytest.raises(ValueError, match="previously activated"):
        change_skill(db, "opening", "1", OfflineShopModel, reports, rollback=True)
    assert change_skill(db, "opening", "1", OfflineShopModel, reports)["status"] == "ACTIVATED"

    class Regressing(OfflineShopModel):
        def complete(self, *args, **kwargs):
            reply = super().complete(*args, **kwargs)
            return ModelTurn(
                reply.content.replace("pence GBP", "euros"), reply.calls, reply.output_tokens
            )

    result = change_skill(db, "opening", "2", Regressing, reports)
    assert result["status"] == "REJECTED"
    assert (
        db.connection.execute("SELECT version FROM assistant_skills WHERE active=1").fetchone()[0]
        == "1"
    )
    assert change_skill(db, "opening", "3", OfflineShopModel, reports)["status"] == "ACTIVATED"
    assert (
        change_skill(db, "opening", "1", OfflineShopModel, reports, rollback=True)["status"]
        == "ROLLED_BACK"
    )
    assert (
        db.connection.execute("SELECT version FROM assistant_skills WHERE active=1").fetchone()[0]
        == "1"
    )
    assert db.connection.execute("SELECT count(*) FROM assistant_skills").fetchone()[0] == 3
    files = list(reports.glob("*.json"))
    assert len(files) == 4
    assert sum(json.loads(path.read_text())["passed"] for path in files) == 3
    assert all(path.stat().st_mode & 0o077 == 0 for path in files)
