"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.session.directory import create_session


@pytest.fixture()
def sessions_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sessions"
    d.mkdir()
    return d


@pytest.fixture()
def fresh_session(sessions_dir: Path):
    """A freshly-created session rooted in a tmp sessions_dir."""
    return create_session(
        scenario="test",
        task="test task",
        sessions_dir=sessions_dir,
    )
