"""Evaluation must use the selected guidance and cannot activate against changed state."""

import json

import pytest

from reference_organizations.store.agent import OfflineShopModel
from reference_organizations.store.evaluation import CASES, evaluate
from reference_organizations.store.improvement import change_skill
from sovereign_agent.assistant_context import (
    Skill,
    activate_skill,
    remember,
    skill_snapshot,
    stage_skill,
)
from sovereign_agent.cli import main
from sovereign_agent.database import Database


def stage(db, root, name, version="1", instructions="Read stock and draft in GBP."):
    path = root / f"{name}-{version}.toml"
    path.write_text(
        f"name={json.dumps(name)}\nversion={json.dumps(version)}\n"
        f"instructions={json.dumps(instructions)}\n"
    )
    return stage_skill(db, path)


def activate(db, name):
    activate_skill(
        db, name, "1", evaluate=lambda _: {"case": True}, required_cases=frozenset({"case"})
    )


def test_candidate_replaces_its_version_and_keeps_other_active_guidance():
    old = Skill(name="opening", version="1", instructions="OLD PROCEDURE")
    candidate = Skill(name="opening", version="2", instructions="CANDIDATE PROCEDURE")
    other = Skill(name="reporting", version="1", instructions="OTHER ACTIVE GUIDANCE")

    class InspectContext(OfflineShopModel):
        def complete(self, messages, *args, **kwargs):
            text = messages[0]["content"]
            assert "CANDIDATE PROCEDURE" in text and "OTHER ACTIVE GUIDANCE" in text
            assert "OLD PROCEDURE" not in text
            return super().complete(messages, *args, **kwargs)

    report = evaluate(InspectContext, cases=(CASES[0],), skill=candidate, skills=(old, other))
    assert report["passed"]
    assert [(item["name"], item["version"]) for item in report["skills"]] == [
        ("opening", "2"),
        ("reporting", "1"),
    ]


def test_cli_evaluates_active_guidance_without_copying_live_preferences(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("SOVEREIGN_AGENT_MODEL_MODE", raising=False)
    db = Database(tmp_path / "agent.sqlite")
    stage(db, tmp_path, "opening", instructions="ACTIVE OPENING PROCEDURE")
    activate(db, "opening")
    remember(db, "lucy", "private", "LIVE SESSION PRIVATE FACT", "operator")
    expected_state, _ = skill_snapshot(db)
    assert main(["agent", "evaluate", "--root", str(tmp_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    with open(result["report"]) as stream:
        report = json.load(stream)
    assert report["active_skill_state"] == expected_state
    assert report["skills"][0]["name"] == "opening"
    for row in report["cases"]:
        text = row["transcript"][0]["content"]
        assert "ACTIVE OPENING PROCEDURE" in text
        assert "LIVE SESSION PRIVATE FACT" not in text
    db.close()


def test_evaluator_cannot_change_the_candidate_it_claimed_to_test(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    stage(db, tmp_path, "opening")

    def mutate(candidate):
        candidate.instructions = "A different unevaluated procedure"
        return {"case": True}

    with pytest.raises(ValueError, match="changed the candidate"):
        activate_skill(db, "opening", "1", evaluate=mutate, required_cases=frozenset({"case"}))
    assert (
        db.connection.execute("SELECT count(*) FROM assistant_skills WHERE active=1").fetchone()[0]
        == 0
    )
    db.close()


def test_another_activation_during_evaluation_invalidates_the_result(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    stage(db, tmp_path, "opening")
    stage(db, tmp_path, "reporting")
    other = Database(db.path)

    def change_configuration(candidate):
        activate(other, "reporting")
        return {"case": True}

    with pytest.raises(PermissionError, match="configuration changed"):
        activate_skill(
            db, "opening", "1", evaluate=change_configuration, required_cases=frozenset({"case"})
        )
    assert (
        db.connection.execute("SELECT name FROM assistant_skills WHERE active=1").fetchone()[0]
        == "reporting"
    )
    other.close()
    db.close()


def test_full_improvement_path_reports_stale_without_activating(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    stage(db, tmp_path, "opening")
    stage(db, tmp_path, "reporting")
    other = Database(db.path)

    class ConfigurationChanges(OfflineShopModel):
        changed = False

        def complete(self, *args, **kwargs):
            if not ConfigurationChanges.changed:
                activate(other, "reporting")
                ConfigurationChanges.changed = True
            return super().complete(*args, **kwargs)

    result = change_skill(db, "opening", "1", ConfigurationChanges, tmp_path / "reports")
    assert result["passed"] is True and result["status"] == "STALE"
    assert (
        db.connection.execute("SELECT name FROM assistant_skills WHERE active=1").fetchone()[0]
        == "reporting"
    )
    event = db.connection.execute(
        "SELECT payload FROM events WHERE kind='assistant.skill.evaluated' "
        "ORDER BY rowid DESC LIMIT 1"
    ).fetchone()[0]
    assert json.loads(event)["activation_status"] == "STALE"
    other.close()
    db.close()
