"""Explicit hosting and SQLite maintenance; restored authority starts paused."""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from sovereign_agent.database import Database


def health(db: Database) -> dict[str, Any]:
    states = {
        row[0]: row[1]
        for row in db.connection.execute(
            "SELECT status,count(*) FROM assistant_work GROUP BY status"
        )
    }
    oldest = db.connection.execute(
        "SELECT min(created) FROM assistant_work WHERE status IN ('READY','RUNNING','BLOCKED')"
    ).fetchone()[0]
    return {
        "paused": bool(
            db.connection.execute("SELECT paused FROM assistant_control WHERE id=1").fetchone()[0]
        ),
        "work": states,
        "oldest_work_seconds": 0 if oldest is None else max(0, time.time() - oldest),
        "uncertain_orders": db.connection.execute(
            "SELECT count(*) FROM assistant_orders WHERE status IN ('UNKNOWN','SENDING')"
        ).fetchone()[0],
        "uncertain_deliveries": db.connection.execute(
            "SELECT count(*) FROM assistant_reports WHERE channel LIKE 'telegram:%' "
            "AND delivery IN ('UNKNOWN','SENDING')"
        ).fetchone()[0],
    }


def backup(db: Database, destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("backup destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation makes double runs a refusal, not replacement of evidence.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(destination) as snapshot:
            db.connection.backup(snapshot)
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("backup integrity check failed")
        with destination.open("rb") as stream:
            os.fsync(stream.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def restore(db: Database, source: Path) -> None:
    """Pause the active database, invalidate old holders, then copy a checked snapshot.

    Keep the same database inode: replacing the path would strand old connections
    on an independently writable database. SQLite backup replaces its contents
    under SQLite's locks. A process already admitted to the supplier may still
    complete remotely; restoring never claims to recall it.
    """
    if source.resolve() == db.path.resolve() or not source.is_file():
        raise ValueError("a separate existing backup is required")
    with sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True) as snapshot:
        if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("restore source is corrupt")
        versions = {row[0] for row in snapshot.execute("SELECT version FROM schema_migrations")}
        if versions != db.applied_versions():
            raise ValueError("restore requires the same schema version; migrate a copy first")
        # Prepare the restored image before disturbing active state.
        with tempfile.TemporaryDirectory(prefix="sovereign-restore-") as temporary:
            image = Path(temporary) / "restored.sqlite"
            epoch = uuid.uuid4().hex
            with sqlite3.connect(image) as prepared:
                snapshot.backup(prepared)
                prepared.execute(
                    "UPDATE assistant_control SET epoch=?,paused=1 WHERE id=1", (epoch,)
                )
                prepared.execute(
                    "UPDATE assistant_work SET generation=generation+1,owner=NULL,expires=NULL,"
                    "status=CASE WHEN status='RUNNING' THEN 'READY' ELSE status END"
                )
                # Old approvals can be reconciled, but cannot authorize a new send.
                prepared.execute("UPDATE assistant_orders SET revoked=1,approved_until=0")
                prepared.commit()
                with db.immediate() as connection:
                    connection.execute("UPDATE assistant_control SET paused=1 WHERE id=1")
                marker = db.path.with_suffix(".authority")
                replacement = marker.with_name(marker.name + "." + epoch)
                with replacement.open("x") as stream:
                    stream.write(epoch)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(replacement, marker)
                prepared.backup(db.connection)
    # Deliberately no automatic resume: the operator must reconcile the supplier's
    # account, including effects newer than this snapshot, and reauthorize work.


def unit_text(root: Path, executable: Path, *, research: bool = False) -> str:
    root, executable = root.resolve(), executable.resolve()
    # systemd has expansion rules distinct from shell quoting. Keep the tutorial's
    # installation path deliberately narrow rather than invent an escaping DSL.
    if any(not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)) for path in (root, executable)):
        raise ValueError(
            "service paths must be absolute and contain no spaces or expansion characters"
        )
    worker_flag = " --research-worker" if research else ""
    env_file = "research.env" if research else "agent.env"
    return f"""[Unit]
Description=Lucy's always-on teaching agent
After=network-online.target

[Service]
Type=simple
WorkingDirectory={root}
ExecStart={executable} agent serve --root {root}{worker_flag}
EnvironmentFile={root}/{env_file}
Restart=on-failure
RestartSec=10
TimeoutStopSec=90
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={root}

[Install]
WantedBy=default.target
"""


def service(action: str, root: Path, executable: Path, *, research: bool = False) -> dict[str, Any]:
    if sys.platform != "linux":
        raise ValueError("service installation requires Linux and a user systemd manager")
    if action not in {"install", "status", "uninstall"}:
        raise ValueError("invalid service action")
    name = "sovereign-agent-research.service" if research else "sovereign-agent.service"
    path = Path.home() / ".config/systemd/user" / name
    if action == "install":
        env = root.resolve() / ("research.env" if research else "agent.env")
        if not env.is_file() or env.stat().st_mode & 0o077:
            raise ValueError("create the worker environment file with mode 0600 first")
        content = unit_text(root, executable, research=research)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text() != content:
            raise FileExistsError("different service already installed")
        path.write_text(content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=20)
        subprocess.run(["systemctl", "--user", "enable", "--now", name], check=True, timeout=20)
    elif action == "uninstall":
        if path.exists() and path.read_text() != unit_text(root, executable, research=research):
            raise ValueError("refuse to remove another installation")
        subprocess.run(["systemctl", "--user", "disable", "--now", name], check=True, timeout=20)
        path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=20)
    result = subprocess.run(
        ["systemctl", "--user", "show", name, "--property=ActiveState,SubState"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return {
        "action": action,
        "unit": str(path),
        "status": result.stdout.strip(),
        "exit_code": result.returncode,
    }
