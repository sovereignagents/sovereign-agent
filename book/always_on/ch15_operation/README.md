# Chapter 15 — Deploy and maintain the agent

Lucy's agent can now receive work, ask for approval and recover an uncertain order. Those abilities are useful only while a host runs the program and preserves its records. Closing a terminal must not silently end the morning routine. Updating the code must not discard yesterday's purchases. Restoring a backup must not persuade the supplier that an old approval is new authority.

This chapter turns our existing bounded worker into an installed Linux service. We keep one writable state directory outside immutable release directories, use the operating system's service manager and distinguish process health from business progress. Then we construct the backup and restore boundary and recover an older local snapshot against a separate supplier account.

The deployment is deliberately modest: one Linux host, one user service for shop work, an optional second service for bounded research, SQLite and operator-owned environment files. A maintained service manager supplies restart behavior. We still own the decisions about work, permissions, receipts and reconciliation. The machine's availability remains a condition of the promise, not something an agent loop can manufacture.

## Learning objectives

Construct a systemd unit for the bounded worker; distinguish liveness from progress; inspect work age and uncertain outcomes; create a consistent, protected backup; restore without preserving obsolete authority; preflight an upgrade before stopping services; and verify that a compatible rollback preserves business history.

The portable deliverable is a maintenance checkpoint that creates real SQLite state and a separate loopback supplier process. It restores an older snapshot, rejects stale authority, reconciles later receipts and completes fresh work. The Linux deliverable is an installed service whose release, state, reboot behavior and completed work are recorded separately. Neither a generated unit nor a green portable checkpoint proves that the host started it.

## Put code, state and credentials in deliberate places

An immutable release contains the committed source, lockfile and its virtual environment. A state directory contains the database, authority marker, evaluation records and operator configuration. We choose the release when installing the unit rather than depending on an interactive shell's activated environment. This gives an upgrade a visible target and leaves the previous code available for a reviewed rollback.

For the following commands, choose three absolute paths without spaces or systemd expansion characters. `LUCY_CURRENT` is the release named by the installed unit, `LUCY_TARGET` is the reviewed replacement, and `LUCY_STATE` is the existing writable state directory. For a first installation, there is no current service to uninstall. The commands are a host recipe and are not executed by the portable manuscript checker.

```bash
export LUCY_STATE=/srv/lucy/state
export LUCY_TARGET=/srv/lucy/releases/reviewed-release
cd "$LUCY_TARGET"
uv sync --frozen --no-dev --python 3.14
mkdir -p "$LUCY_STATE"
chmod 700 "$LUCY_STATE"
```

Use the committed lock. A fresh dependency resolution during an urgent maintenance window changes two things at once: the application and the dependency set. The lock does not certify every dependency's behavior, but it makes the environment being installed identifiable. Record the source commit and Python version with the release rather than using a folder name as evidence of its contents.

Create `agent.env` and, if using research, `research.env` locally with mode 0600. The research environment does not need a Telegram token or purchasing configuration. An empty environment file is sufficient for the offline teaching model. A live model and channel require the operator's actual configuration. Do not paste credentials into the manuscript, source tree or proof bundle.

| Location | What belongs there | What a backup must preserve |
| --- | --- | --- |
| Immutable release | Source commit, lockfile, virtual environment | Identity and a reproducible installation path |
| Writable state | SQLite records, authority marker, evaluation artifacts | Consistent database plus retained external artifacts |
| Operator environment | Channel token, allowlist, model configuration | Separately protected configuration and recovery access |
| Supplier account | Accepted orders and current account epoch | Independent discovery; a local copy is insufficient |

The database backup function below snapshots SQLite only. It does not copy skill source files, saved evaluation JSON, environment files or the supplier database. A complete maintenance runbook inventories those separately. Active skill content and versions held in SQLite survive its backup, but an evaluation row pointing to a missing report file is not a complete evidence archive.

```mermaid
flowchart LR
    release[Reviewed release and frozen environment] --> unit[User service]
    env[Operator environment file] --> unit
    unit --> state[Writable state directory]
    state --> snapshot[Consistent local backup]
    unit --> supplier[Independent supplier account]
```

**Figure:** The service combines an explicit release with persistent state while the supplier keeps an independent history.

## Construct the host contract

The unit starts the same `agent serve` command we developed earlier. It does not put a second scheduler inside the language model. The process receives signals, runs bounded passes and waits between them. Waiting does not call the model. A failed process can be restarted by systemd; eligible abandoned work is then recovered through the [durable claims from Chapter 10](../ch10_worker_recovery/README.md).

Paths are deliberately restricted. systemd unit files have expansion rules that differ from shell quoting. Accepting arbitrary strings and placing quotation marks around them would create an escaping language inside a teaching installer. Here, an unsupported installation path produces a refusal that the builder can resolve by selecting a supported path.

**Listing:** Construct a service unit with an explicit executable and writable state.

```python
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


unit = unit_text(
    Path("/srv/lucy/state"),
    Path("/srv/lucy/releases/one/.venv/bin/sovereign-agent"),
)
print("Restart on failure:", "Restart=on-failure" in unit)
print("Bounded shutdown:", "TimeoutStopSec=90" in unit)
print(
    "Research uses a separate environment:",
    "research.env"
    in unit_text(Path("/srv/lucy/state"), Path("/usr/bin/sovereign-agent"), research=True),
)
try:
    unit_text(Path("/srv/lucy with spaces"), Path("/usr/bin/sovereign-agent"))
except ValueError:
    print("Unsupported path refused")
```

```text
Restart on failure: True
Bounded shutdown: True
Research uses a separate environment: True
Unsupported path refused
```

`Restart=on-failure` restarts a process after a failure, not after every intentional clean stop. `RestartSec=10` spaces failed starts. `TimeoutStopSec=90` gives the bounded loop time to stop before systemd's final termination policy applies. That timeout does not guarantee an external request has been recalled. The supplier may have accepted a request before the process received its stop signal.

The filesystem settings reduce writable paths and isolate temporary files where the host supports them. They do not transform every host subprocess into the constrained report container from Chapter 11. `NoNewPrivileges` constrains later privilege gain; it does not remove credentials the program already has. Inspect the host's actual unit diagnostics and use the report tool's separate boundary when executing generated code.

The installation function checks the environment file, refuses to overwrite a different unit and uses bounded subprocess calls. Its status result includes systemctl's exit code and reported state. A caller must inspect those values. Returning a dictionary is not itself proof that a unit is active or that Lucy has received a result.

```python
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


print("Service function constructed:", callable(service))
print("Host installation requires:", "Linux user systemd manager")
```

```text
Service function constructed: True
Host installation requires: Linux user systemd manager
```

The two fixed unit names deliberately support one teaching shop per Linux user. A second independent shop is an architectural extension, not a reason to overwrite the first unit. `service uninstall` verifies the unit belongs to the requested release and root before removing it. This ownership check makes a mistaken path visible during maintenance.

## Install, then prove useful work

For a first installation, initialize the state with the target release, prepare the environment files and install the main service. Install the research service only if the bounded delegation experiment justifies keeping it. Both commands use the release's actual executable; the source checkout's location on another machine is irrelevant to the host.

```bash
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent init --root "$LUCY_STATE"
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent service install --root "$LUCY_STATE"
systemctl --user show sovereign-agent.service --property=ActiveState,SubState,MainPID,NRestarts
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent ask "Prepare a stock brief." --id deployment-proof-1 --enqueue-only --root "$LUCY_STATE"
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent status --root "$LUCY_STATE"
```

The first observation is an active process. The second is a durable request. The decisive application observation is that this request becomes `DONE` with a grounded result while the service, rather than the invoking terminal, does the work. Inspect the request ID; an older successful item does not prove the newly installed executable handled the test.

An offline model run proves this path without spending tokens or depending on a model provider. A separate live-model run establishes that the configured endpoint works. The phone path adds its own evidence: allowlisted intake, stable session, completed work and observed delivery. These observations answer different questions, so do not substitute one for another.

User services also depend on the lifetime of the user manager. The isolated Linux host used for this chapter had lingering enabled and both services returned after an actual VM reboot. A builder must deliberately configure and verify that behavior on their host. A service running during an open login does not prove it will start unattended after the next boot.

## Observe work age and uncertain outcomes

Process liveness is a narrow fact. A live process may be waiting for a supplier, unable to reach a model, repeatedly failing a tool or holding an approval that Lucy has not answered. We therefore summarize durable business state as well as the host's process state. The health function is read-only and uses the database as its source.

```python
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
            "SELECT count(*) FROM assistant_work WHERE channel LIKE 'telegram:%' "
            "AND delivery IN ('UNKNOWN','SENDING')"
        ).fetchone()[0],
    }


from reference_organizations.store.agent import seed_lucy
from sovereign_agent.assistant_work import enqueue

temporary = tempfile.TemporaryDirectory(prefix="lucy-ch15-")
root = Path(temporary.name)
db = Database(root / "agent.sqlite")
seed_lucy(db)
enqueue(db, "morning", "lucy", "Prepare a stock brief.")
observation = health(db)
print("Paused:", observation["paused"])
print("Ready work:", observation["work"]["READY"])
print("Age is nonnegative:", observation["oldest_work_seconds"] >= 0)
print("Uncertain orders:", observation["uncertain_orders"])
```

```text
Paused: False
Ready work: 1
Age is nonnegative: True
Uncertain orders: 0
```

Oldest work age uses the creation time of ready, running and blocked work. It is a backlog signal, not a precise measure of time since the last useful step. A blocked approval may be correctly waiting for Lucy. Pair the age with the work's status and history before deciding that a worker is broken.

The service logs status and work identity rather than prompts or channel credentials. Read them with the host's journal tool and correlate the work ID with its records. The current service also emits idle statuses; for a long-running installation, inspect journal retention and volume. A small program can produce an unnecessarily large log if it reports every idle pass forever.

| Observation | What it supports | Next investigation when concerning |
| --- | --- | --- |
| ActiveState and MainPID | A service process is active now | Unit definition, last exit and restart count |
| Oldest eligible work age | Work has remained unfinished | Approval, dependency, lease and retry history |
| Uncertain orders | External completion needs discovery | Existing operation IDs and supplier receipts |
| Uncertain deliveries | Outbound communication may have arrived | Delivery records and channel-specific policy |
| Model allowance records | Reserved calls and configured cost estimates | Actual provider billing and incomplete-history markers |

The health dictionary does not include every operating metric. Model usage is stored in daily accounting records, and actual provider charges require the provider's billing evidence. A zero configured estimate does not mean a live model was free. Chapter 12's cost and latency reports remain useful, but they measure particular scenarios rather than the entire host's operating bill.

## Construct a consistent backup

SQLite can keep committed changes in its write-ahead log. Copying only the main database file while the service runs can omit those changes. The backup API asks SQLite to produce a consistent snapshot across its own storage mechanism. It avoids inventing a file-copy protocol for a live database.

The destination is created exclusively with restrictive permissions. A repeated command refuses to replace the earlier snapshot. After copying, we check SQLite integrity and synchronize the file. This is evidence about the resulting database file, not a promise that every storage device or filesystem will survive every power failure. The host backup plan must still account for its own durability and retention requirements.

```python
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


snapshot = backup(db, root / "before.sqlite")
with sqlite3.connect(snapshot) as saved:
    print("Snapshot integrity:", saved.execute("PRAGMA integrity_check").fetchone()[0])
    print("Snapshot work:", saved.execute("SELECT count(*) FROM assistant_work").fetchone()[0])
try:
    backup(db, snapshot)
except FileExistsError:
    print("Repeated destination refused")
print("Private snapshot permissions:", snapshot.stat().st_mode & 0o077 == 0)
```

```text
Snapshot integrity: ok
Snapshot work: 1
Repeated destination refused
Private snapshot permissions: True
```

Keep the snapshot's source release and schema identity beside it. Retain a copy outside the host whose failure you are preparing for, using an operator-selected storage and access policy. This chapter does not implement a cloud backup service. Its concrete contract is the consistent file, its protected handling and a rehearsed restore path.

A successful backup is incomplete operational evidence until someone has restored it into a controlled environment and inspected its meaning. Byte integrity can coexist with obsolete business facts. Our failure experiment deliberately uses such a snapshot: it is internally consistent and still predates accepted supplier orders.

## Restore records without restoring obsolete authority

Suppose the morning snapshot contains an approved vanilla order. During the day, the supplier accepts it, the delivery arrives and a strawberry order is accepted too. Restoring the morning snapshot loses those later local records. It does not remove the supplier's accepted orders or take the delivered tubs back out of the freezer.

Restore therefore starts paused. It changes the authority epoch, invalidates worker generations and revokes old approvals. It preserves the database inode, using SQLite's backup machinery to replace the contents. Replacing the pathname with a different database file would leave existing connections attached to the old inode and create competing writable histories.

```mermaid
sequenceDiagram
    participant O as Operator
    participant D as Active database
    participant B as Checked snapshot
    participant S as Supplier account
    O->>B: Validate schema and integrity
    O->>D: Pause and replace authority epoch
    B->>D: Copy prepared paused image through SQLite
    O->>S: Fence account and inspect retained receipts
    O->>D: Apply exact plan with current physical counts
    D-->>O: Reconciled state and explicit fresh allowance
```

**Figure:** A restored snapshot remains paused until external receipts and current observations establish a new operating state.

The restore function constructs a prepared image before disturbing active state. It requires the same migration set as the current database. An older snapshot must be migrated as a copy with reviewed current code; preserve the original as evidence. Removing migration stamps to force compatibility would conceal the very fact the precondition is checking.

```python
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


from sovereign_agent.assistant_work import claim, assert_current

holder = claim(db, "before-restore")
old_connection = Database(db.path)
inode = db.path.stat().st_ino
restore(db, snapshot)
print("Database inode preserved:", db.path.stat().st_ino == inode)
print("Restored state paused:", health(db)["paused"])
print("New worker withheld:", claim(db, "replacement") is None)
try:
    assert_current(old_connection.connection, holder)
except PermissionError:
    print("Old open connection refused")
old_connection.close()
db.close()
temporary.cleanup()
```

```text
Database inode preserved: True
Restored state paused: True
New worker withheld: True
Old open connection refused
```

There is deliberately no automatic resume line. A process that already passed an external write boundary may still complete remotely. Local epoch replacement prevents newly admitted local writes by obsolete holders; it cannot travel backward through a supplier's network request. Account recovery needs the supplier's independent boundary and history.

## Reconcile the account with current observations

The controlled supplier implements an account epoch and a complete retained receipt export. Inspection rotates its write epoch using the restored authority identity. Old supplier clients can no longer submit new orders with their previous epoch. Repeating inspection for the same restored authority does not invent a new account each time.

Inspection returns a plan template with unknown physical counts. That is intentional. A receipt can establish that the supplier accepted six tubs; it cannot establish that the delivery arrived, that no tubs were sold or that the freezer count matches the old snapshot. The operator supplies fresh per-SKU physical counts and explicit delivery observations.

The plan is bound to exact bytes by a digest and has a freshness requirement. Recovery checks the operator, paused authority, account, receipt set, product set, delivery observations and model grants before activating the restored state. A changed plan requires its own digest. Repeating the same accepted plan does not spend again or renew its fresh model allowance.

In the chapter checkpoint, the snapshot contains one order. The independent supplier contains two accepted orders. Vanilla has actually been received, bringing physical stock to eight; four strawberry tubs remain pending. Recovery imports both receipts and records 2600 pence once. The old supplier client is then deliberately used for an attempted order and is refused.

```mermaid
flowchart TD
    snapshot[One order in morning snapshot] --> paused[Paused restore]
    receipts[Two retained supplier receipts] --> plan[Exact recovery plan]
    counts[Current physical counts and delivery observations] --> plan
    paused --> plan
    plan --> result[Two reconciled orders and 2600 pence spent]
    result --> fresh[Explicit fresh model allowance]
    result --> history[Historical usage remains incomplete]
```

**Figure:** Recovery combines independent receipts and present observations without pretending that lost usage history has been reconstructed.

The fresh allowance is a new authorization. Lost model-call accounting does not become zero simply because the snapshot cannot show later usage. The runtime retains an incomplete-history marker, and repeating the recovery plan cannot refresh an exhausted grant. This distinction lets the shop resume bounded work without claiming to know the unrecorded past.

A supplier without complete discovery or an equivalent write fence needs a different recovery contract. An empty search result does not prove that a previously admitted request cannot arrive later. The educational supplier makes those requirements inspectable; it does not establish that every commercial supplier offers them.

## Upgrade and roll back without erasing the day

Install the target release's frozen environment before stopping the current services. Read its known migration set and compare it with the existing database using SQLite's read-only mode. Do this with the target interpreter, without constructing `Database`, so the preflight cannot accidentally migrate state while deciding whether the target understands it.

The actual Linux experiment first upgraded schema 24 to schema 25 for the approval-basis change. It then attempted the older schema-24 release and received a refusal before either service was stopped. That is the desired failure: leave the known working system available while reporting why the requested downgrade is invalid.

For a compatible upgrade, stop both workers and coordinate any other writers. Preserve a new backup, open the state with the target to apply reviewed forward migrations, install its units and enqueue a unique read-only request. Compare orders, inventory and spending before and after the switch. A new `DONE` result plus unchanged retained business facts is stronger evidence than installation output alone.

```bash
"$LUCY_CURRENT/.venv/bin/sovereign-agent" agent service uninstall --root "$LUCY_STATE"
"$LUCY_CURRENT/.venv/bin/sovereign-agent" agent service uninstall --root "$LUCY_STATE" --research-worker
"$LUCY_CURRENT/.venv/bin/sovereign-agent" agent backup "$LUCY_STATE/before-upgrade.sqlite" --root "$LUCY_STATE"
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent status --root "$LUCY_STATE"
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent service install --root "$LUCY_STATE"
"$LUCY_TARGET/.venv/bin/sovereign-agent" agent service install --root "$LUCY_STATE" --research-worker
```

Only uninstall the research service if it belongs to this installation. The complete preflight and ownership checks are in the [Linux maintenance appendix](../appendices/linux-maintenance-v1.md). The abbreviated sequence here assumes those checks have already passed. It is not permission to run an arbitrary old executable against current state because the directory still exists.

Code rollback keeps the business state. A prior release must understand the current schema and preserve the authority contract. Matching migration numbers are necessary, but they do not prove that an older implementation enforces a later security repair. Review the actual change before choosing a fallback release.

Restoring an old database to make old code start is a different operation. It can erase local knowledge of orders that still exist remotely and therefore enters the paused reconciliation path. Keep these two operations distinct in the runbook and in the evidence: code replacement preserves history; state recovery reconstructs an authorized present from incomplete local history.

## Failure experiment and learner verification

### Exercise 1: restore the day against retained receipts

Run the portable checkpoint from the repository root. It uses temporary local state, an actual supplier process and authored physical observations. It does not alter installed services or contact a real supplier. Its systemd line is an explicit limit on what this command proves.

```bash
uv run --python 3.14 python book/always_on/checkpoints/ch15.py
```

### Expected observations

Expected observations include a preserved database inode, refusal of the old connection and supplier epoch, one local order after restore followed by two reconciled orders, 2600 pence expenditure, eight vanilla tubs on hand, four strawberry tubs pending and fresh work becoming `DONE`. The historical model-usage flag remains incomplete.

### Exercise 2: prove work after the terminal closes

For the host experiment, record the exact release and unit paths, main process identities, restart counters and a unique completed request. Stop the terminal session and verify another scheduled request. Reboot the isolated host and verify the service and fresh work again. Inspect retained business records after the reboot; old successful logs alone cannot establish that the new process handled anything.

The committed Linux receipts distinguish these observations from the portable checkpoint. Earlier host proofs include an actual VM reboot, worker termination, backup, account recovery and compatible code switches. The latest release installation preserves the same two orders, stock and 2600-pence expenditure. Those finite experiments do not establish a month of uptime or an uninterrupted-service guarantee.

### Exercise 3: refuse unsafe maintenance inputs

For an adversarial exercise, attempt to restore the active database onto itself, reuse a backup destination, use an unsupported unit path and supply a changed recovery digest. Each should refuse before it can silently replace evidence or regain authority. Then attempt a downgrade whose code does not know the newest migration; the current service must remain untouched by the preflight refusal.

For an operating exercise, define a useful alert threshold for work age in Lucy's shop. A morning brief waiting five minutes may warrant attention; a large order awaiting an explicit approval may be correctly blocked for hours. State the business reason for the threshold and the record you would inspect before restarting anything. Restarting a healthy process cannot supply missing approval.

## Summary

We constructed the host unit and maintenance boundary around the same bounded runtime. Immutable releases make the selected code visible, while persistent state survives process replacement. Health observations distinguish liveness from unfinished work and uncertain effects. SQLite backup produces a consistent local snapshot, and restore invalidates old authority rather than treating old records as permission to repeat the day.

Account recovery requires more than file integrity. The controlled supplier's fence and retained receipts combine with current physical observations and an exact plan. A fresh model allowance permits bounded progress while the incomplete-history marker keeps the lost past visible. A compatible code rollback preserves these records instead of replacing them with a convenient older database.

### Active recall

Why can copying only the live SQLite file miss committed work? Why preserve the active database inode during restore? What can an accepted supplier receipt establish about physical stock? Why does a matching schema not fully justify a code rollback? Which observation proves the service handled a new request after reboot? Why must replaying a recovery plan avoid granting another model allowance?

### Vocabulary

A release identifies immutable code and its environment. A user service is managed by the host's user-level service manager. A consistent snapshot reflects SQLite's committed state at a valid point. An authority epoch invalidates prior holders across restore. Account reconciliation combines external receipts with present observations. A code rollback changes the executable while retaining compatible business history.

The next chapter combines the mechanisms into Lucy's accelerated business day. Its final report must distinguish orders, deliveries, approvals, work and expenditure, and every reported result must lead back to the records that support it.
