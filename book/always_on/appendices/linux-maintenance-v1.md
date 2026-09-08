# Linux maintenance: preserve state while changing code

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

This recipe supports Chapter 15's construction. It uses the same Linux user services and SQLite state as the runtime. The accompanying evidence records an actual Ubuntu host upgrade, account recovery and compatible-code rollback. It is not a substitute for completing the chapter or observing a real phone interaction.

Use immutable release directories containing the committed source and their own frozen virtual environments. Keep the writable state directory outside those releases. Both `agent.env` and `research.env` belong to the operator, have mode 0600, and remain outside source control. Do not print their contents while collecting evidence.

## Inspect before switching

Choose the current and target release paths explicitly. Do not infer the current executable from whichever virtual environment happens to be on your terminal's PATH. Read `ExecStart` in both installed units and verify that the paths belong to this installation.

```bash
systemctl --user cat sovereign-agent.service sovereign-agent-research.service
systemctl --user show sovereign-agent.service sovereign-agent-research.service --property=ActiveState,SubState,MainPID,NRestarts
```

In the examples below, set `LUCY_STATE`, `LUCY_CURRENT` and `LUCY_TARGET` to your absolute state and release directories. The service installer accepts paths without spaces or systemd expansion characters. Install the target's environment from its committed lock before changing a running service:

```bash
cd "$LUCY_TARGET"
uv sync --frozen --no-dev --python 3.14
```

Review the target's migration and authority changes. A matching set of schema numbers is necessary for a code-only rollback, but does not prove that the older code preserves the current authority contract. In particular, a release without supplier account fencing must not operate a recovered account merely because some table columns look familiar.

Run this preflight with the **target release's interpreter**. It reads the existing database using SQLite's read-only mode without constructing `Database`, so even historical executables lacking the new startup guard can be checked before opening the state for work:

```bash
"$LUCY_TARGET/.venv/bin/python" - "$LUCY_STATE/agent.sqlite" <<'PY'
import sqlite3
import sys
from pathlib import Path
from sovereign_agent.database import MIGRATIONS

path = Path(sys.argv[1]).resolve()
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
known = {version for version, _ in MIGRATIONS}
unknown = applied - known
if unknown:
    raise SystemExit(f"REFUSED: target does not understand migrations {sorted(unknown)}")
print("Known schema; pending migrations:", sorted(known - applied))
PY
```

A refusal leaves the running services alone. Do not delete migration stamps to bypass it, run a historical binary against unknown state, or replace the database with an old file to make the error disappear. Choose compatible code or design an explicit forward repair. The current loader also rejects unknown migrations before journal-mode changes and refuses malformed existing migration ledgers.

## Stop both workers and preserve a backup

Use the current release to uninstall its own units. This stops the processes and removes the old `ExecStart` definitions. The installer deliberately refuses to overwrite another release's unit, and the uninstaller checks ownership before removing one.

```bash
"$LUCY_CURRENT/.venv/bin/sovereign-agent" agent service uninstall --root "$LUCY_STATE"
"$LUCY_CURRENT/.venv/bin/sovereign-agent" agent service uninstall --root "$LUCY_STATE" --research-worker
"$LUCY_CURRENT/.venv/bin/sovereign-agent" agent backup "$LUCY_STATE/before-upgrade.sqlite" --root "$LUCY_STATE"
```

The backup destination must be new. A repeated command refuses instead of replacing the earlier evidence. SQLite's backup API includes committed state consistently; copying only the live main database file can miss content still in its WAL. Record the backup's release/schema alongside its path. Protect it as sensitive business state.

Stopping both workers is part of the compatibility contract. A startup check cannot stop an old process that already opened the database. Coordinate other tools that can write this state as well. A supplier request already admitted before shutdown may still finish remotely; the shutdown sequence cannot recall an external effect.

## Migrate and start the target

Open state with the target while the workers are stopped. The `status` action opens the database and applies known forward migrations. Inspect its health output before installing the new units.

```bash
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent status --root "$LUCY_STATE"
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent service install --root "$LUCY_STATE"
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent service install --root "$LUCY_STATE" --research-worker
systemctl --user is-active sovereign-agent.service sovereign-agent-research.service
```

An active process is only the first observation. Enqueue a bounded read-only stock request and verify a completed result from the service, then compare retained orders, inventory and spending with the pre-switch observations. A service that repeatedly restarts or holds work indefinitely has not passed the upgrade simply because installation exited zero.

User-service availability after reboot also depends on the host's user-manager configuration. The executed host proof used an enabled lingering user manager; both services came back after an actual VM reboot. Check that host setting deliberately in deployment rather than assuming an open development login will remain forever.

## Roll back code without rolling back business history

For a reviewed, schema-compatible prior release, repeat the preflight and stop/install sequence with the release roles exchanged. Keep the same state. Verify a new work result and retained business records again. The recorded experiment switched from `cec0452` to `313ac06`, back to `cec0452`, and returned to `313ac06`, all at schema 24. The two accepted orders and £26 spending remained unchanged, and service work completed after each switch.

The same experiment refused the older schema-22 release because migrations 23 and 24 were unknown to it. A pre-upgrade schema-22 backup still exists as evidence; it was not installed over the current account to force a downgrade. This distinction matters whenever external events have occurred since the backup.

## Restore is a separate recovery operation

A restore changes authority and starts paused. The source snapshot must have the same schema as the active database; if it is older, migrate a **copy** with the current release and retain the original backup. Inspect that copy before restoring. The restore API preserves the active database inode so old connections do not become independent writers to an abandoned file.

Resuming requires the controlled supplier's complete retained account history, an epoch fence and an exact-digest recovery plan. The plan must contain fresh per-SKU physical counts and explicit delivery observations, including receipts newer than the local backup. Do not treat backup inventory as a current count. Do not infer that missing model usage was zero; grant any fresh model allowance explicitly and retain the incomplete-history marker.

The Linux experiment backed up before six vanilla tubs were accepted and received, then four strawberry tubs were accepted afterward. Restoring lost the later local history. Reconciliation recovered both receipts, set vanilla physical stock to the explicitly observed eight tubs, retained four pending strawberry tubs, recorded 2600 pence once, and refused the old supplier client and work owner. Repeating the same recovery plan did not renew its grant. The actual main service then completed a fresh stock request without another purchase.

The supplier used in this proof is controlled loopback teaching infrastructure with retained history and an epoch-aware write boundary. Its temporary process was stopped afterward. A real provider lacking complete discovery or an equivalent fence requires a different recovery contract; an empty lookup is not proof that an old request cannot arrive later.

See `docs/evidence/always-on/linux-operation-v1.json`, `linux-maintenance-v1.json` and `linux-maintenance-return-v1.json` for pinned observations. The final acceptance chapter combines these operational mechanisms with the rest of Lucy's day.
