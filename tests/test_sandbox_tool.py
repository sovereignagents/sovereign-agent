"""Container behavior is a separate opt-in proof, never inferred from CLI flags."""

import json
import os
from pathlib import Path

import pytest

from sovereign_agent.sandbox_tool import run_python


def test_unpinned_image_refuses_without_executing_code(tmp_path):
    with pytest.raises(ValueError):
        run_python(
            "raise RuntimeError('must not run on host')",
            {},
            image="python:latest",
            scratch=tmp_path,
        )


def settings():
    image = os.environ.get("SOVEREIGN_AGENT_SANDBOX_IMAGE")
    if not image:
        pytest.skip("set an installed digest-pinned sandbox image for OS-boundary proof")
    return {
        "image": image,
        "scratch": Path(os.environ.get("SOVEREIGN_AGENT_SANDBOX_SCRATCH", "/tmp")),
        "docker_host": os.environ.get("SOVEREIGN_AGENT_DOCKER_HOST"),
    }


@pytest.mark.live
def test_container_enforces_files_network_identity_and_secret_boundaries(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_AGENT_TELEGRAM_TOKEN", "PRIVATE_SENTINEL_NEVER_FORWARD")
    source = """import json,os,socket
results={"uid":os.getuid(),"interfaces":socket.if_nameindex(),"secret":os.getenv("SOVEREIGN_AGENT_TELEGRAM_TOKEN"),"data":json.load(open("/input/data.json"))}
for label,path in (("input_write","/input/forbidden"),("root_write","/usr/local/forbidden")):
    try:
        open(path,"w").write("bad")
        results[label]="ALLOWED"
    except OSError as error:
        results[label]=error.errno
sock=socket.socket()
sock.settimeout(.2)
try:
    sock.connect(("198.51.100.1",443))
    results["network"]="ALLOWED"
except OSError as error:
    results["network"]=error.errno
print(json.dumps(results))
"""
    result = run_python(source, {"stock": 2}, **settings())
    assert result["status"] == "COMPLETED" and result["cleanup"] == "confirmed"
    proof = json.loads(result["output"])
    assert proof["uid"] == 65534 and proof["interfaces"] == [[1, "lo"]]
    assert proof["secret"] is None and proof["data"] == {"stock": 2}
    assert proof["input_write"] in {13, 30} and proof["root_write"] in {13, 30}
    assert (
        proof["network"] == 101
    )  # ENETUNREACH, not a timeout that also passes on a normal network.


@pytest.mark.live
@pytest.mark.parametrize(
    ("source", "expected"),
    [("while True: pass", "TIME_LIMIT"), ('print("x"*100000)', "OUTPUT_LIMIT")],
)
def test_container_timeout_and_output_limit_remove_the_process(source, expected):
    result = run_python(source, {}, seconds=0.5, maximum_output=256, **settings())
    assert result["status"] == expected and result["cleanup"] == "confirmed"
    assert len(result["output"].encode()) <= 256
