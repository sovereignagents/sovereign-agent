"""Prove candidate guidance is evaluated before activation and rollback."""

import hashlib
import json
import tempfile
import tomllib
from pathlib import Path

from reference_organizations.store.agent import OfflineShopModel
from reference_organizations.store.improvement import change_skill
from sovereign_agent.assistant_context import skill_snapshot, stage_skill
from sovereign_agent.database import Database
from sovereign_agent.events import append_event
from sovereign_agent.model_turn import ModelTurn


class FollowsCandidate(OfflineShopModel):
    """A deterministic policy fixture, not a measure of language-model quality."""

    def complete(self, messages, *args, **kwargs):
        turn = super().complete(messages, *args, **kwargs)
        if "Report every amount in euros." in messages[0]["content"]:
            return ModelTurn(
                turn.content.replace("pence GBP", "euros"), turn.calls, turn.output_tokens
            )
        return turn


def main():
    original = tomllib.loads(
        (Path(__file__).parents[1] / "skills" / "opening-check-v1.toml").read_text()
    )
    with tempfile.TemporaryDirectory(prefix="lucy-improvement-") as temporary:
        root = Path(temporary)
        db = Database(root / "agent.sqlite")
        reports = root / "reports"

        def stage(version, instructions, name=original["name"]):
            path = root / f"{name}-{version}.toml"
            assert not path.exists()
            path.write_text(
                "name="
                + json.dumps(name)
                + "\nversion="
                + json.dumps(version)
                + "\ninstructions="
                + json.dumps(instructions)
                + "\nrequires="
                + json.dumps(original["requires"])
                + "\n"
            )
            skill = stage_skill(db, path)
            with db.immediate():
                append_event(
                    db,
                    "assistant.skill.proposed",
                    {
                        "name": skill.name,
                        "version": skill.version,
                        "candidate_sha256": hashlib.sha256(
                            skill.model_dump_json().encode()
                        ).hexdigest(),
                        "feedback_source": "fixture/lucy/brief-1",
                        "request": "Keep amounts in GBP and make the closing sentence concise.",
                        "scope": "Operator-staged test proposal; does not grant tool authority.",
                    },
                )
            return skill

        stage("1", original["instructions"])
        assert (
            change_skill(db, original["name"], "1", FollowsCandidate, reports)["status"]
            == "ACTIVATED"
        )
        stage("2", original["instructions"] + "\nReport every amount in euros.")
        bad = change_skill(db, original["name"], "2", FollowsCandidate, reports)
        assert bad["status"] == "REJECTED"
        assert skill_snapshot(db)[1][0].version == "1"
        print(
            "Regressing guidance:",
            bad["status"],
            "active version",
            skill_snapshot(db)[1][0].version,
        )
        stage("3", original["instructions"] + "\nKeep the closing sentence concise.")
        good = change_skill(db, original["name"], "3", FollowsCandidate, reports)
        assert good["status"] == "ACTIVATED"
        print("Passing candidate:", good["status"])
        rolled = change_skill(db, original["name"], "1", FollowsCandidate, reports, rollback=True)
        assert rolled["status"] == "ROLLED_BACK"
        print("Earlier activated version:", rolled["status"])
        stage("4", original["instructions"] + "\nRetain source names in explanations.")
        stage("1", "Keep reports concise.", name="reporting")
        other = Database(db.path)

        class ConcurrentChange(FollowsCandidate):
            changed = False

            def complete(self, *args, **kwargs):
                if not ConcurrentChange.changed:
                    ConcurrentChange.changed = True
                    assert (
                        change_skill(other, "reporting", "1", FollowsCandidate, reports)["status"]
                        == "ACTIVATED"
                    )
                return super().complete(*args, **kwargs)

        stale = change_skill(db, original["name"], "4", ConcurrentChange, reports)
        assert stale["status"] == "STALE" and stale["passed"]
        print("Configuration changes during evaluation:", stale["status"])
        assert [(s.name, s.version) for s in skill_snapshot(db)[1]] == [
            (original["name"], "1"),
            ("reporting", "1"),
        ]
        for result in (bad, good, rolled, stale):
            raw = Path(result["report"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == result["sha256"]
            assert json.loads(raw)["acceptance"]["status"] in {"REVIEW_REQUIRED", "REJECTED"}
        print(
            "Retained version rows:",
            db.connection.execute("SELECT count(*) FROM assistant_skills").fetchone()[0],
        )
        print("Retained evaluation reports:", len(list(reports.glob("*.json"))))
        proposals = db.connection.execute(
            "SELECT count(*) FROM events WHERE kind='assistant.skill.proposed'"
        ).fetchone()[0]
        assert proposals == 5
        print("Proposals retain feedback provenance:", proposals)
        other.close()
        db.close()
        reopened = Database(root / "agent.sqlite")
        assert [(s.name, s.version) for s in skill_snapshot(reopened)[1]] == [
            (original["name"], "1"),
            ("reporting", "1"),
        ]
        print("Active configuration survives reopen:", True)
        reopened.close()


if __name__ == "__main__":
    main()
