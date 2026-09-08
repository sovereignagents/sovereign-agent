"""Trace optional tools from a model call through the real adapter to its result."""

import json
import os
from pathlib import Path

import pytest

from reference_organizations.store.agent import seed_lucy
from reference_organizations.store.assistant import run_once
from reference_organizations.store.extra_tools import Sandbox, optional_tools
from sovereign_agent.assistant_work import enqueue
from sovereign_agent.database import Database
from sovereign_agent.model_turn import ModelTurn, ToolCall


class RequestTool:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments

    def complete(self, messages, *args, **kwargs):
        observations = [m for m in messages if m["role"] == "tool"]
        if not observations:
            return ModelTurn(calls=(ToolCall(id="one", name=self.name, arguments=self.arguments),))
        return ModelTurn(observations[-1]["content"])


def fixture(tmp_path):
    db = Database(tmp_path / "agent.sqlite")
    seed_lucy(db)
    enqueue(db, "one", "lucy", "Use the configured report tool.")
    return db


def test_model_request_reaches_real_mcp_server_and_persists_result(tmp_path):
    db = fixture(tmp_path)
    result = run_once(
        db, RequestTool("catalog_mcp", {}), extra_tools=tuple(optional_tools(db, mcp_catalog=True))
    )
    response = json.loads(result["answer"])
    assert response["ok"] is True
    catalog = json.loads(response["value"]["content"][0]["text"])
    assert catalog == [
        {"sku": "SKU-VANILLA", "name": "Vanilla"},
        {"sku": "SKU-CHOCOLATE", "name": "Chocolate"},
        {"sku": "SKU-STRAWBERRY", "name": "Strawberry"},
    ]
    assert (
        db.connection.execute(
            "SELECT count(*) FROM assistant_transcript WHERE message LIKE '%SKU-VANILLA%'"
        ).fetchone()[0]
        > 0
    )


def test_optional_tool_is_unavailable_until_operator_enables_it(tmp_path):
    db = fixture(tmp_path)
    result = run_once(db, RequestTool("catalog_mcp", {}))
    assert json.loads(result["answer"]) == {"ok": False, "error": "tool_not_allowed"}


@pytest.mark.live
def test_generated_report_reads_current_database_through_container(tmp_path):
    image = os.environ.get("SOVEREIGN_AGENT_SANDBOX_IMAGE")
    if not image:
        pytest.skip("explicit pinned image required for the real container experiment")
    db = fixture(tmp_path)
    with db.immediate() as connection:
        connection.execute("UPDATE inventory SET on_hand=123 WHERE sku='SKU-VANILLA'")
    sandbox = Sandbox(
        image,
        Path(os.environ["SOVEREIGN_AGENT_SANDBOX_SCRATCH"]),
        os.environ.get("SOVEREIGN_AGENT_DOCKER_HOST"),
    )
    code = (
        "import json\nrows=json.load(open('/input/data.json'))['stock']\n"
        "print(next(r['on_hand'] for r in rows if r['sku']=='SKU-VANILLA'))"
    )
    result = run_once(
        db,
        RequestTool("python_report", {"source": code}),
        extra_tools=tuple(optional_tools(db, sandbox=sandbox)),
    )
    response = json.loads(result["answer"])
    assert response["ok"] is True and response["value"]["status"] == "COMPLETED"
    assert response["value"]["output"] == "123\n"
    assert response["value"]["cleanup"] == "confirmed"
