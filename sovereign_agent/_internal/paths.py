"""Cross-platform user-data directories for sovereign-agent.

Students and users who run `python -m chapters.chapter_01_session.demo`
should be able to inspect the session files afterwards without having
the demo pollute their git working tree. The correct place for these
files is a platform-appropriate user-data directory:

    Linux:   ~/.local/share/sovereign-agent/
    macOS:   ~/Library/Application Support/sovereign-agent/
    Windows: %LOCALAPPDATA%\\sovereign-agent\\

This mirrors what fastai, Hugging Face datasets, jupyter, and every
other well-behaved Python library does. It keeps the repo clean and
makes demos reproducible from any working directory.

We implement this with stdlib only — no `platformdirs` dependency —
because this is boring, stable code that doesn't deserve an external
package. XDG Base Directory on Linux is a published spec; macOS and
Windows paths are conventional and stable.

Environment override: set ``SOVEREIGN_AGENT_DATA_DIR`` to any path to
force all user-data artifacts somewhere else. Tests and CI use this to
pin artifacts into a tmp dir.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_APP_NAME = "sovereign-agent"
_OVERRIDE_ENV = "SOVEREIGN_AGENT_DATA_DIR"


def user_data_dir() -> Path:
    """Return the platform-appropriate user-data directory for the app.

    The directory is created if it does not exist. The returned path
    is always absolute.

    Honours ``$SOVEREIGN_AGENT_DATA_DIR`` if set — useful for tests
    that need to redirect artifacts into a tmp dir, and for users who
    keep these on external storage.
    """
    if override := os.environ.get(_OVERRIDE_ENV):
        path = Path(override).expanduser().resolve()
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / _APP_NAME
    elif sys.platform == "win32":
        # LOCALAPPDATA is the conventional location for app data on
        # Windows. Fall back to the user's home if it's unset (rare).
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / _APP_NAME
    else:
        # Linux and other Unixes — follow XDG Base Directory spec.
        # https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / _APP_NAME

    path.mkdir(parents=True, exist_ok=True)
    return path


def demo_sessions_dir(chapter: str) -> Path:
    """Return the directory where a chapter demo should write sessions.

    Example:

        >>> demo_sessions_dir("ch1")
        PosixPath('/home/rod/.local/share/sovereign-agent/demos/ch1')

    The directory is created if it does not exist. Safe to call
    repeatedly; calls are idempotent.
    """
    path = user_data_dir() / "demos" / chapter
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def example_sessions_dir(example_name: str, *, persist: bool) -> Iterator[Path]:
    """Yield a sessions root suitable for an example scenario.

    If ``persist=True`` (e.g. ``--real`` mode), artifacts land under the
    platform-conventional user-data directory, matching where the chapter
    demos also write:

        Linux:   ~/.local/share/sovereign-agent/examples/<example_name>/
        macOS:   ~/Library/Application Support/sovereign-agent/examples/<example_name>/
        Windows: %LOCALAPPDATA%\\sovereign-agent\\examples\\<example_name>\\

    This is the XDG-equivalent per-platform default — same pattern as
    pip, uv, HuggingFace, PyTorch, and every other well-behaved Python
    library. It keeps example artifacts out of the user's CWD (important:
    sovereign-agent ships on pypi; CWD is wherever the user happens to
    have run the command and writing there would be hostile).

    Set ``SOVEREIGN_AGENT_DATA_DIR=<path>`` to pin artifacts somewhere
    specific — external storage, a project-local directory, or anywhere
    else. Artifacts then land under ``<path>/examples/<example_name>/``.

    Real-LLM runs burn tokens and their traces are the most interesting
    to inspect afterwards. The entry-point script prints the resolved
    path (shell-quoted) at the end of the run, so you don't have to
    guess where to look.

    Otherwise (``persist=False``) a tempdir is used and evaporates when
    the context exits. Offline (FakeLLMClient) runs are deterministic
    and cheap to reproduce, so persistence would just accumulate stale
    state.

    Example:

        >>> with example_sessions_dir("research_assistant", persist=True) as root:
        ...     session = create_session(..., sessions_dir=root)
    """
    if persist:
        root = user_data_dir() / "examples" / example_name
        root.mkdir(parents=True, exist_ok=True)
        yield root
    else:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "sessions"
            root.mkdir()
            yield root


__all__ = ["user_data_dir", "demo_sessions_dir", "example_sessions_dir"]
