"""IpcWatcher: long-running poll loop over every session's IPC directories.

Processes messages from `ipc/output/` (messages FROM workers), handoff
files (`handoff_to_*.json`), and `session_complete.json`.

Messages into workers (`ipc/input/`) are consumed by the workers themselves,
not by this watcher.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from sovereign_agent._internal.atomic import atomic_write_json
from sovereign_agent.ipc.protocol import read_and_consume

log = logging.getLogger(__name__)


HandoffHandler = Callable[[str, str, dict], Awaitable[None]]
"""(session_id, target_half, payload) -> None"""

OutputHandler = Callable[[str, dict], Awaitable[None]]
"""(session_id, payload) -> None"""

CompleteHandler = Callable[[str, dict], Awaitable[None]]
"""(session_id, payload) -> None"""


_HANDOFF_FILE_PREFIX = "handoff_to_"
_HANDOFF_FILE_SUFFIX = ".json"
_SESSION_COMPLETE = "session_complete.json"


class IpcWatcher:
    """Polls every session directory and dispatches messages to handlers."""

    def __init__(
        self,
        sessions_dir: Path,
        *,
        on_output: OutputHandler | None = None,
        on_handoff: HandoffHandler | None = None,
        on_complete: CompleteHandler | None = None,
        poll_interval_s: float = 1.0,
    ) -> None:
        self.sessions_dir = Path(sessions_dir)
        self.on_output = on_output
        self.on_handoff = on_handoff
        self.on_complete = on_complete
        self.poll_interval_s = poll_interval_s
        self._running = False
        self._task: asyncio.Task | None = None

    async def run(self) -> None:
        """Main polling loop. Runs until shutdown() is called."""
        self._running = True
        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self.poll_interval_s)
        finally:
            self._running = False

    async def _tick(self) -> None:
        if not self.sessions_dir.exists():
            return
        for entry in self.sessions_dir.iterdir():
            if not entry.is_dir() or not entry.name.startswith("sess_"):
                continue
            try:
                await self._process_session(entry)
            except Exception:  # noqa: BLE001
                # Per-session isolation: one session's problem doesn't stop the rest.
                log.exception("error processing session %s", entry.name)

    async def _process_session(self, session_dir: Path) -> None:
        sid = session_dir.name

        # 1) Output messages from the worker.
        output_dir = session_dir / "ipc" / "output"
        if output_dir.exists() and self.on_output is not None:
            for _orig, payload in read_and_consume(output_dir):
                try:
                    await self.on_output(sid, payload)
                except Exception:  # noqa: BLE001
                    log.exception("on_output handler raised for session %s", sid)

        # 2) Handoff files (one-at-a-time rule, fail-closed if multiple present).
        await self._process_handoffs(session_dir, sid)

        # 3) session_complete.json
        complete_path = session_dir / "ipc" / _SESSION_COMPLETE
        if complete_path.exists() and self.on_complete is not None:
            await self._process_complete(session_dir, sid, complete_path)

    async def _process_handoffs(self, session_dir: Path, sid: str) -> None:
        ipc_dir = session_dir / "ipc"
        if not ipc_dir.exists():
            return
        handoff_files = [
            p
            for p in ipc_dir.iterdir()
            if p.is_file()
            and p.name.startswith(_HANDOFF_FILE_PREFIX)
            and p.name.endswith(_HANDOFF_FILE_SUFFIX)
            and not p.name.endswith(".tmp")
        ]
        if not handoff_files:
            return
        if len(handoff_files) > 1:
            # The handoff protocol says exactly one visible at a time.
            # Fail-closed: mark the session's handoffs as malformed. We
            # move all of them to an error dir and leave a breadcrumb.
            err_dir = session_dir / "logs" / "handoffs" / "_malformed"
            err_dir.mkdir(parents=True, exist_ok=True)
            for p in handoff_files:
                dest = err_dir / f"{int(time.time() * 1000)}_{p.name}"
                try:
                    p.replace(dest)
                except OSError:
                    pass
            atomic_write_json(
                err_dir / "reason.json",
                {
                    "code": "SA_IO_MALFORMED_HANDOFF_STATE",
                    "message": "multiple handoff files present simultaneously",
                    "session_id": sid,
                    "detected_at": time.time(),
                },
            )
            return

        # Exactly one handoff file. Consume it.
        (handoff_path,) = handoff_files
        target_half = handoff_path.stem.removeprefix(_HANDOFF_FILE_PREFIX)
        try:
            import json

            with open(handoff_path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError):
            err_dir = session_dir / "logs" / "handoffs" / "_malformed"
            err_dir.mkdir(parents=True, exist_ok=True)
            try:
                handoff_path.replace(err_dir / handoff_path.name)
            except OSError:
                pass
            return

        # Archive to logs/handoffs/<timestamp>_handoff.json BEFORE dispatching
        # so the audit log is the source of truth and the consuming half
        # reads from there, not from ipc/.
        audit_dir = session_dir / "logs" / "handoffs"
        audit_dir.mkdir(parents=True, exist_ok=True)
        iso = time.strftime("%Y-%m-%dT%H-%M-%S")
        audit_path = audit_dir / f"{iso}_{target_half}_handoff.json"
        try:
            handoff_path.replace(audit_path)
        except OSError:
            # If we can't rename, something is very wrong; don't dispatch.
            return

        if self.on_handoff is not None:
            try:
                await self.on_handoff(sid, target_half, payload)
            except Exception:  # noqa: BLE001
                log.exception("on_handoff handler raised for session %s", sid)

    async def _process_complete(self, session_dir: Path, sid: str, complete_path: Path) -> None:
        import json

        try:
            with open(complete_path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError):
            return
        # Move into logs so the ipc/ dir is empty after consumption.
        dest_dir = session_dir / "logs"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / _SESSION_COMPLETE
        try:
            complete_path.replace(dest)
        except OSError:
            pass
        if self.on_complete is not None:
            try:
                await self.on_complete(sid, payload)
            except Exception:  # noqa: BLE001
                log.exception("on_complete handler raised for session %s", sid)

    async def shutdown(self) -> None:
        self._running = False


__all__ = ["IpcWatcher"]
