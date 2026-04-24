"""Tests for Config loading."""

from __future__ import annotations

from pathlib import Path

from sovereign_agent.config import Config


def test_from_env_reads_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_AGENT_MAX_CONCURRENT", "42")
    monkeypatch.setenv("SOVEREIGN_AGENT_LLM_PLANNER_MODEL", "foo/bar")
    cfg = Config.from_env()
    assert cfg.max_concurrent == 42
    assert cfg.llm_planner_model == "foo/bar"


def test_from_env_coerces_types(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_AGENT_POLL_INTERVAL_S", "0.25")
    monkeypatch.setenv("SOVEREIGN_AGENT_BARE_MODE", "true")
    cfg = Config.from_env()
    assert cfg.poll_interval_s == 0.25
    assert cfg.bare_mode is True


def test_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[sovereign_agent]
max_concurrent = 9
llm_planner_model = "weird/model"
"""
    )
    cfg = Config.from_toml(path)
    assert cfg.max_concurrent == 9
    assert cfg.llm_planner_model == "weird/model"


def test_validate_catches_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("NEBIUS_KEY", raising=False)
    cfg = Config()
    issues = cfg.validate()
    assert any("NEBIUS_KEY" in i for i in issues)


def test_validate_catches_bad_concurrency() -> None:
    cfg = Config(max_concurrent=0)
    issues = cfg.validate()
    assert any("max_concurrent" in i for i in issues)
