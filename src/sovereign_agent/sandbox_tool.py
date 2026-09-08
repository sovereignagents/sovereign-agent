"""One digest-pinned, networkless Python container tool. No host fallback."""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

# Trusted PID 1 reads no report output. A different UID prevents the report
# from disabling its deadline; exiting PID 1 terminates the container's tasks.
_CONTAINER_INIT = """import os, sys, time
end = time.monotonic() + float(sys.argv[1])
child = os.fork()
if child == 0:
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)
    os.execv(sys.executable, [sys.executable, "-I", "-B", "/input/program.py"])
while time.monotonic() < end:
    finished, status = os.waitpid(child, os.WNOHANG)
    if finished:
        os._exit(0 if os.waitstatus_to_exitcode(status) == 0 else 1)
    time.sleep(0.01)
os._exit(124)
"""


def run_python(
    source: str,
    data: Any,
    *,
    image: str,
    scratch: Path,
    docker_host: str | None = None,
    seconds: float = 5,
    maximum_output: int = 16_384,
) -> dict[str, Any]:
    """Mount only a newly constructed input directory; credentials are not copied.

    The Docker daemon and image supply the OS boundary. This function does not
    prove Docker's kernel isolation or make arbitrary host executables safe.
    Output is untrusted data even when containment succeeds.
    """
    if os.name != "posix" or not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9./:_-]*@sha256:[a-f0-9]{64}", image
    ):
        raise ValueError("POSIX and an explicit digest-pinned image are required")
    if (
        not 0 < seconds <= 30
        or not 128 <= maximum_output <= 65_536
        or len(source.encode()) > 16_384
    ):
        raise ValueError("invalid sandbox limits")
    encoded = json.dumps(data, allow_nan=False).encode()
    if len(encoded) > 65_536:
        raise ValueError("sandbox input exceeds byte limit")
    environment = {"PATH": os.environ.get("PATH", os.defpath)}
    if docker_host:
        if not docker_host.startswith("unix:///"):
            raise ValueError("teaching sandbox requires a local Docker socket")
        environment["DOCKER_HOST"] = docker_host
    probe = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        timeout=5,
        env=environment,
    )
    if probe.returncode:
        raise OSError("pinned image or Docker engine unavailable; execution refused")
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = "sovereign-teaching-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="tool-", dir=scratch) as directory:
        inputs = Path(directory) / "input"
        if "," in str(inputs.absolute()):
            raise ValueError("sandbox scratch path cannot contain mount-option separators")
        inputs.mkdir(mode=0o755)
        for filename, content in (
            ("program.py", source.encode()),
            ("data.json", encoded),
            ("runner.py", _CONTAINER_INIT.encode()),
        ):
            path = inputs / filename
            path.write_bytes(content)
            path.chmod(0o444)
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network=none",
            "--log-driver=none",
            "--read-only",
            "--cap-drop=ALL",
            "--cap-add=SETUID",
            "--cap-add=SETGID",
            "--security-opt=no-new-privileges",
            "--pids-limit=32",
            "--memory=64m",
            "--cpus=1",
            "--ulimit",
            "nofile=64:64",
            "--user=0:0",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=8m",
            "--mount",
            f"type=bind,src={inputs.absolute()},dst=/input,readonly",
            "--entrypoint=python",
            image,
            "-I",
            "-B",
            "/input/runner.py",
            str(seconds),
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=environment,
            start_new_session=True,
        )
        assert process.stdout
        output = bytearray()
        outcome = "COMPLETED"
        deadline = time.monotonic() + seconds
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    if not selector.select(max(0, deadline - time.monotonic())):
                        outcome = "TIME_LIMIT"
                        break
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > maximum_output:
                        outcome = "OUTPUT_LIMIT"
                        break
            if outcome == "COMPLETED":
                try:
                    code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                    if code:
                        outcome = "TIME_LIMIT" if code == 124 else "TOOL_FAILED"
                except subprocess.TimeoutExpired:
                    outcome = "TIME_LIMIT"
        finally:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
            process.stdout.close()
            subprocess.run(
                ["docker", "rm", "--force", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                env=environment,
            )
            # `--rm` may already have removed it. Inspect absence, not rm's exit.
            remaining = subprocess.run(
                ["docker", "ps", "--all", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
                env=environment,
            )
            if remaining.returncode or remaining.stdout.strip():
                raise OSError("sandbox cleanup could not be confirmed")
    return {
        "status": outcome,
        "output": bytes(output[:maximum_output]).decode(errors="replace"),
        "image": image,
        "network": "none",
        "input_mount": "read-only",
        "cleanup": "confirmed",
    }
