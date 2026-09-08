"""The report cannot disable its timer, including after the host runner dies."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time

import pytest

from sovereign_agent.sandbox_tool import run_python
from tests.test_sandbox_tool import settings


@pytest.mark.live
def test_report_cannot_signal_init_or_regain_privileges():
    source = """import os,signal,json
result={"uid":os.getuid(),"gid":os.getgid(),"groups":os.getgroups()}
for field in ("CapEff", "CapPrm", "CapAmb", "NoNewPrivs"):
    result[field]=next(line.split(":",1)[1].strip()
        for line in open("/proc/self/status") if line.startswith(field+":"))
for label, operation in (
    ("kill",lambda:os.kill(1,signal.SIGKILL)),
    ("stop",lambda:os.kill(1,signal.SIGSTOP)),
    ("uid",lambda:os.setuid(0)),("gid",lambda:os.setgid(0))
):
    try:
        operation()
        result["attempt_"+label]="ALLOWED"
    except PermissionError as e:
        result["attempt_"+label]=e.errno
print(json.dumps(result))
"""
    result = run_python(source, {}, **settings())
    assert result["status"] == "COMPLETED"
    proof = json.loads(result["output"])
    assert proof["uid"] == proof["gid"] == 65534 and proof["groups"] == []
    assert all(int(proof[k], 16) == 0 for k in ("CapEff", "CapPrm", "CapAmb"))
    assert proof["NoNewPrivs"] == "1"
    assert all(proof["attempt_" + k] == 1 for k in ("kill", "stop", "uid", "gid"))


@pytest.mark.live
def test_child_cannot_spoof_the_supervisor_timeout_exit():
    result = run_python("raise SystemExit(124)", {}, **settings())
    assert result["status"] == "TOOL_FAILED" and result["cleanup"] == "confirmed"


@pytest.mark.live
def test_deadline_survives_host_sigkill_with_detached_report_child():
    config = settings()
    environment = {"PATH": os.environ.get("PATH", os.defpath)}
    if config["docker_host"]:
        environment["DOCKER_HOST"] = config["docker_host"]

    def docker(*args):
        return subprocess.run(
            ["docker", *args],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout

    def own_containers(directory):
        names = docker(
            "ps", "--all", "--filter", "name=sovereign-teaching-", "--format", "{{.Names}}"
        )
        owned = []
        for name in names.splitlines():
            # Never remove a concurrent test or operator's container.
            try:
                info = json.loads(docker("inspect", name))[0]
            except subprocess.CalledProcessError:
                continue  # --rm can race inspection of an unrelated completed run.
            if any(m["Source"].startswith(directory + "/") for m in info["Mounts"]):
                owned.append((name, info["State"]["Running"]))
        return owned

    with tempfile.TemporaryDirectory(prefix="deadline-proof-", dir=config["scratch"]) as directory:
        config["scratch"] = directory
        source = (
            "import os,time; child=os.fork(); os.setsid() if child==0 else None; time.sleep(60)"
        )
        command = (
            "import json,sys;from pathlib import Path;"
            "from sovereign_agent.sandbox_tool import run_python;"
            "config=json.loads(sys.argv[1]);config['scratch']=Path(config['scratch']);"
            "run_python(sys.argv[2],{},seconds=5,**config)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", command, json.dumps(config), source],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                owned = own_containers(directory)
                if owned and owned[0][1]:
                    # Prove the untrusted child reached exec before killing the host.
                    probe = (
                        "from pathlib import Path;"
                        "print(any(b'/input/program.py' in p.read_bytes().split(bytes([0])) "
                        "for p in Path('/proc').glob('[0-9]*/cmdline')))"
                    )
                    if (
                        docker(
                            "exec", "--user=65534:65534", owned[0][0], "python", "-I", "-c", probe
                        ).strip()
                        == "True"
                    ):
                        break
                time.sleep(0.02)
            else:
                pytest.fail("report did not start before the test deadline")
            process.send_signal(signal.SIGKILL)
            process.communicate(timeout=3)
            assert process.returncode == -signal.SIGKILL
            deadline = time.monotonic() + 7
            while own_containers(directory) and time.monotonic() < deadline:
                time.sleep(0.1)
            assert own_containers(directory) == []
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
            for name, _ in own_containers(directory):
                docker("rm", "--force", name)
