**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** FINDING

# A report deadline must survive its host runner

Authority is the operator-delegated self-contained teaching scope. This decision
changes the container bootstrap, not purchasing authority or the installed
source budget. The pinned Python image and Docker engine remain operator-owned.

The original host-side finally cleanup was insufficient after SIGKILL. On the
isolated Linux teaching engine, a report container remained running6.06seconds
after killing its host runner despite a five-second limit. The probe removed
only its own exact container. Preserve that failed-boundary receipt.

The repair supplies a read-only trusted PID1 Python supervisor inside the
container. Its only bootstrap capabilities are SETUID and SETGID. It forks,
clears supplementary groups and drops the report child to UID/GID65534 before
exec. The supervisor never evaluates report code or reads its output. It waits
for the direct child or its independent monotonic deadline, then exits. Docker's
PID namespace terminates remaining descendants when PID1 exits. The child has
zero effective, permitted and ambient capabilities and no-new-privileges.
The distinct UID prevents it from stopping or killing PID1. This is a measured
bootstrap trade-off: it is no longer accurate to say every container process
runs as65534. The untrusted report does; the trusted supervisor is container root
with those two capabilities, under the same read-only mount, network, memory,
CPU, process and descriptor restrictions. No privileged-container mode or host
socket is mounted.

Seven opt-in Linux tests passed: filesystem, network, secret and identity
restrictions; ordinary deadline; output overflow; privileged identity and
supervisor signal refusal; child-exit124 cannot spoof the supervisor timeout;
actual host SIGKILL with a detached report descendant; and current database
stock traversing the actual model-loop/dispatcher/container report path. The
separate before/after orphan probes record the original defect and the repair.
The first live-suite attempt lacked pytest in the installed service release;
a separate frozen-lock development environment was built under scratch. The
next attempt found the host docker-top probe unavailable; the final probe reads
exact process arguments inside the container instead. The seven successful
cases are not inferred from Docker flags.

Limits remain: kernel, Docker daemon, image and operator configuration are
trusted. These tests do not prove freedom from kernel exploits. An unavailable
host/daemon may prevent cleanup observation. Hard-killing the host runner can
leave its bounded input directory; its execution deadline still ends the
container while the host kernel and engine are operating. Ordinary returns
confirm container absence and remove the temporary directory. Output remains
untrusted and cannot grant spending authority.

MCP is a separate local executable boundary. Ten actual stdio-peer cases exposed
boolean/numeric response identities matching integer1 and malformed tool names.
The client now demands its exact integer request identity and nonempty string
names in object entries. Unsupported responses close the server process group.
These bounded protocol checks do not sandbox an operator-approved MCP server.
The book will not claim that prompt injection is solved or unique to this work.
