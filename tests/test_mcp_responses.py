"""Malformed responses from a real stdio peer must fail at the client boundary."""

import json
import sys

import pytest

from sovereign_agent.mcp_client import MCPClient

PEER = """import json, sys
case=json.loads(sys.argv[1])
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request:
        continue
    result=({'protocolVersion':'2025-06-18','capabilities':{'tools':{}}}
            if request['method']=='initialize' else {'tools':case['tools']})
    identifier=case.get('first_id',request['id']) if request['id']==1 else request['id']
    print(json.dumps({'jsonrpc':'2.0','id':identifier,'result':result}),flush=True)
"""


@pytest.mark.parametrize("identifier", [True, 1.0, "1", None])
def test_response_identity_must_match_integer_request_type(identifier):
    with pytest.raises(ValueError, match="identity"):
        MCPClient(
            [sys.executable, "-c", PEER, json.dumps({"first_id": identifier, "tools": []})],
            allowed=frozenset(),
            environment={},
        )


@pytest.mark.parametrize("tool", [None, [], {}, {"name": []}, {"name": ""}, {"name": 3}])
def test_discovery_refuses_malformed_tool_identity(tool):
    with pytest.raises(ValueError, match="tool"):
        MCPClient(
            [sys.executable, "-c", PEER, json.dumps({"tools": [tool]})],
            allowed=frozenset(),
            environment={},
        )
