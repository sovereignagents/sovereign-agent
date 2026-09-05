from __future__ import annotations

import subprocess
import sys

from sovereign_agent.cli import main


def test_help_is_offline_and_teaches_the_purpose(capsys) -> None:
    try:
        main(["--help"])
    except SystemExit as error:
        assert error.code == 0
    output = capsys.readouterr().out
    assert "outcomes" in output
    assert "doctor" in output


def test_doctor_accepts_supported_environment(capsys) -> None:
    assert main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert "Python:" in output
    assert "Pydantic:" in output
    assert "Providers:" in output
    assert "scripted" in output
    assert "Ready for the offline curriculum." in output


def test_module_entry_point_reports_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "sovereign_agent", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "sovereign-agent 1.4.0"
