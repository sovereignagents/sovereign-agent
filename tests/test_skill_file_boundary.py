"""The skill byte bound applies to the open file, including replacement and growth."""

import os
import subprocess
import sys

import pytest

from sovereign_agent.assistant_context import read_skill


def test_growth_after_metadata_check_is_bounded(tmp_path, monkeypatch):
    path = tmp_path / "skill.toml"
    path.write_bytes(b"small")
    original_stat = os.fstat
    original_open = os.fdopen
    requested = []

    def grow(descriptor):
        observed = original_stat(descriptor)
        path.write_bytes(b"x" * 2_000_000)
        return observed

    class Reader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, maximum):
            requested.append(maximum)
            return self.stream.read(maximum)

    monkeypatch.setattr(os, "fstat", grow)
    monkeypatch.setattr(os, "fdopen", lambda *args: Reader(original_open(*args)))
    with pytest.raises(ValueError, match="beyond byte limit"):
        read_skill(path)
    assert requested == [16_385]


def test_replacement_after_open_does_not_change_selected_file(tmp_path, monkeypatch):
    path = tmp_path / "skill.toml"
    path.write_bytes(b"selected")
    original = os.fstat

    def replace(descriptor):
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"different")
        replacement.replace(path)
        return original(descriptor)

    monkeypatch.setattr(os, "fstat", replace)
    assert read_skill(path) == b"selected"
    assert path.read_bytes() == b"different"


def test_byte_limit_and_nonregular_file_refusal(tmp_path):
    path = tmp_path / "skill.toml"
    path.write_bytes(b"x" * 16_384)
    assert len(read_skill(path)) == 16_384
    path.write_bytes(b"x" * 16_385)
    with pytest.raises(ValueError, match="regular"):
        read_skill(path)
    with pytest.raises(ValueError, match="regular"):
        read_skill(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="regular"):
        read_skill(link)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX file boundary")
def test_fifo_is_refused_without_waiting_for_a_writer(tmp_path):
    path = tmp_path / "pipe"
    os.mkfifo(path)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; "
            "from sovereign_agent.assistant_context import read_skill; "
            "read_skill(Path(__import__('sys').argv[1]))",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode != 0
    assert "regular local skill file required" in completed.stderr
