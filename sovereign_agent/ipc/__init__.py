"""Filesystem IPC with atomic rename. Decisions 3 and 4."""

from sovereign_agent.ipc.protocol import (
    CLOSE_SENTINEL_NAME,
    READ_GRACE_MS,
    clear_close_sentinel,
    is_close_sentinel,
    read_and_consume,
    send_input,
    write_close_sentinel,
    write_ipc_message,
)
from sovereign_agent.ipc.watcher import IpcWatcher

__all__ = [
    "CLOSE_SENTINEL_NAME",
    "READ_GRACE_MS",
    "write_ipc_message",
    "write_close_sentinel",
    "is_close_sentinel",
    "clear_close_sentinel",
    "read_and_consume",
    "send_input",
    "IpcWatcher",
]
