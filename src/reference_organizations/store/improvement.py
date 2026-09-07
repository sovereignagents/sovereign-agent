"""Operator-requested skill evaluation, activation and evaluated rollback."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reference_organizations.store.evaluation import CASES, candidate_checks, evaluate
from sovereign_agent.assistant_context import Skill, activate_skill
from sovereign_agent.database import Database
from sovereign_agent.events import append_event
from sovereign_agent.model_turn import Model


def save_report(root: Path, report: dict[str, Any]) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / (uuid.uuid4().hex + ".json")
    raw = (json.dumps(report, indent=2) + "\n").encode()
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return path, hashlib.sha256(raw).hexdigest()


def change_skill(
    db: Database,
    name: str,
    version: str,
    model_factory: Callable[[], Model],
    report_root: Path,
    *,
    repeats: int = 1,
    rollback: bool = False,
    model_label: str = "offline fixture",
) -> dict[str, Any]:
    row = db.connection.execute(
        "SELECT content FROM assistant_skills WHERE name=? AND version=?", (name, version)
    ).fetchone()
    if row is None:
        raise ValueError("stage the exact candidate before requesting activation")
    if (
        rollback
        and not db.connection.execute(
            "SELECT 1 FROM events WHERE kind='assistant.skill.activated' "
            "AND json_extract(payload,'$.name')=? AND json_extract(payload,'$.version')=? LIMIT 1",
            (name, version),
        ).fetchone()
    ):
        raise ValueError("rollback requires a previously activated version")
    skill = Skill.model_validate_json(row["content"])
    report = evaluate(model_factory, skill=skill, repeats=repeats)
    report["model_label"] = model_label
    report["operation"] = "rollback" if rollback else "activation"
    path, digest = save_report(report_root, report)
    checks = candidate_checks(report)
    required = frozenset(f"{case.name}:{repeat}" for case in CASES for repeat in range(repeats))
    if report["passed"]:
        activate_skill(db, name, version, evaluate=lambda _: checks, required_cases=required)
    with db.immediate():
        append_event(
            db,
            "assistant.skill.evaluated",
            {
                "name": name,
                "version": version,
                "passed": report["passed"],
                "report": path.name,
                "sha256": digest,
                "rollback": rollback,
            },
        )
    return {
        "status": ("ROLLED_BACK" if rollback else "ACTIVATED") if report["passed"] else "REJECTED",
        "passed": report["passed"],
        "name": name,
        "version": version,
        "report": str(path),
        "sha256": digest,
        "interpretation": "Passing named scenario checks is bounded evidence. "
        "The offline model does not measure a skill's language-model quality.",
    }
