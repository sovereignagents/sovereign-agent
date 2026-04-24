"""Worker entrypoint (v0.2, Module 2).

This module is executed as a standalone process via:

    python -m sovereign_agent.orchestrator.worker_entrypoint \\
        --session-id sess_xxx \\
        --session-dir /path/to/sessions/sess_xxx

It advances the session by one step:

  1. Loads session.json.
  2. Builds a planner and executor from the session's config.
  3. Calls the appropriate advance function based on session state.
  4. Writes any state changes back to session.json (via Session APIs).
  5. Prints a JSON summary line to stdout as its LAST output.
  6. Exits 0 on success, non-zero on failure.

The module is intentionally small. All the real work lives in the
framework; this entrypoint is glue. That keeps the subprocess startup
cost down and makes it easy for Docker to wrap the same binary
without any image-specific logic.

## Why a JSON summary line, not a return value?

Subprocess boundaries mean we can't return a dataclass. We agreed a
convention: the LAST line of stdout is a JSON object with keys
`terminal`, `advanced`, `summary`. Anything before that is free-form
logging. The parent process (SubprocessWorker) parses just the last
line. This is the same pattern `kubectl`, `docker`, and `git` use for
machine-readable output.

## Why not a socket or pipe?

Because the session directory is already a contract. Adding a socket
means a new IPC format, a new schema, a new failure mode. The JSON
summary line is the smallest possible extension over the existing
"session directory is the source of truth" design.

## Running this via Docker

A DockerWorker invokes this same entrypoint inside a container that has
the session directory bind-mounted at the same path. Because the
entrypoint takes `--session-dir` as an argument and reads/writes only
that path (plus its own network for LLM calls), it is host-agnostic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sovereign-agent-worker",
        description="Advance one session by one step. See module docstring.",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        help="The session to advance. Must exist under --session-dir's parent.",
    )
    parser.add_argument(
        "--session-dir",
        required=True,
        type=Path,
        help="Absolute path to this session's directory.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG/INFO/WARNING/ERROR). Default INFO.",
    )
    return parser.parse_args(argv)


async def _advance(session_id: str, session_dir: Path) -> dict:
    """One-step advance for this process. Returns the summary dict that
    will be JSON-serialised to stdout.

    For v0.2 initial landing: mirrors what the in-process BareWorker
    does, just from a new process. The shared logic lives in
    orchestrator.main._advance_once — we import it here rather than
    duplicating.
    """
    # Imported lazily so `python -m ... --help` works without spinning
    # up the whole framework.
    from sovereign_agent.orchestrator.main import advance_session_once

    try:
        outcome = await advance_session_once(
            session_id=session_id,
            session_dir=session_dir,
        )
    except Exception as exc:  # noqa: BLE001
        # Never bubble — we want a structured exit. The orchestrator
        # reads stderr too and will see the traceback.
        log.exception("worker entrypoint failed")
        return {
            "terminal": False,
            "advanced": False,
            "summary": f"worker raised {type(exc).__name__}: {exc}",
        }

    return {
        "terminal": outcome.terminal,
        "advanced": outcome.advanced,
        "summary": outcome.summary,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    session_dir = args.session_dir.resolve()
    if not session_dir.exists():
        print(
            json.dumps(
                {
                    "terminal": False,
                    "advanced": False,
                    "summary": f"session dir not found: {session_dir}",
                }
            )
        )
        return 2

    summary = asyncio.run(_advance(args.session_id, session_dir))
    # CONTRACT: last line of stdout is JSON.
    print(json.dumps(summary))
    # Exit 0 even on "not advanced" — that's a normal outcome, not a
    # process failure. Non-zero exit is reserved for process-level bugs.
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
