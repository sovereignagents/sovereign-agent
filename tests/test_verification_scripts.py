from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_script(name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_runtime_dependency_gate() -> None:
    result = run_script("verify_runtime_dependencies.py")
    assert result.stdout.strip() == "pydantic"


def test_source_budget_gate() -> None:
    result = run_script("verify_source_budget_v2.py")
    assert "modules=" in result.stdout
    assert "root_exports=" in result.stdout


def test_release_gate_bootstraps_venv_in_a_fresh_interpreter(
    tmp_path: Path, monkeypatch: object
) -> None:
    script = ROOT / "scripts" / "verify_release_candidate.py"
    spec = importlib.util.spec_from_file_location("release_candidate_gate", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    calls: list[list[str]] = []

    def fake_run(argv: list[str], cwd: Path | None = None) -> tuple[int, str]:
        del cwd
        calls.append(argv)
        if argv[1:4] == ["-m", "build", "--wheel"]:
            dist_dir = Path(argv[-1])
            dist_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "sovereign_agent-test-py3-none-any.whl").touch()
        if argv[1:4] == ["-m", "venv", "--clear"]:
            venv_python = Path(argv[-1]) / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.touch()
        return 0, ""

    monkeypatch.setattr(gate, "run", fake_run)  # type: ignore[attr-defined]
    failures: list[str] = []
    assert gate.build_and_install_wheel(failures, tmp_path) == tmp_path / "venv"
    assert failures == []
    assert [sys.executable, "-m", "venv", "--clear", str(tmp_path / "venv")] in calls
