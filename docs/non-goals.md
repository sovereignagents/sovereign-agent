# Durable non-goals

A non-goal is removed only by a recorded authorization and a matching
`CHANGELOG.md` entry. It is not removed by a convenient pull request.

Read with [roadmap.md](roadmap.md) (sequence) and [API.md](API.md) (what the
0.x line promises). Historical v0.3 refusals that still hold for 0.x are also
in [v0.3-non-goals.md](v0.3-non-goals.md).

The 1.x educational line is authorized by
[ruling 2026-08-25 educational reset](rulings/2026-08-25-educational-reset.md).
That ruling does **not** move tag `v0.7.0` and does **not** rewrite the 0.x
contract.

---

## Through v0.7 (0.x line)

These items remain normative for `sovereign-agent<1`.

### No Sandcastle

No Sandcastle dependency, adapter, service, or invocation path. The v0.3
prohibition in [v0.3-non-goals.md](v0.3-non-goals.md) remains in force through
v0.7.

### No governance decisions in this package (0.x only)

On the v0.5–v0.7 line, Sovereign Agent does not decide organizational
authority, accept SOWs, or interpret Zero Employee policy. It executes under
evidence and admissions it is given. ZeoCore also must not import Zero
Employee governance code.

This non-goal is **superseded for Sovereign Agent 1.x** by holding 2 of the
educational-reset ruling: 1.x may contain the minimum governance necessary to
teach and run an end-to-end outcome. It remains in force for published 0.x
releases.

### No second reusable capability schema

Reusable actions on the 0.x line are ZeoCore capabilities. This package does
not grow a parallel capability type system. Runtime evidence types
(`RuntimeCapabilityAssertion`, `RuntimeCapabilityManifest`) are not a second
authoring schema.

### No generic workflow language

No graph DSL, BPMN, or general-purpose workflow product. Session directories,
tickets, and runtime commands remain the 0.x execution model.

### No Kubernetes, Nomad, or cloud autoscaler

v0.7 may add production worker and fleet control on hosts the operator already
runs. It does not add a cluster scheduler or cloud autoscaler.

### No multi-region control plane

One control identity per deployment. Multi-region failover is not authorized
through v0.7.

### No general secrets or object-storage product

Credentials stay in operator-owned env/files. Artifacts stay in session
directories. This is not a secrets manager or an S3 competitor.

### No multi-repository atomic execution

A governed execution targets one configured repository identity. Cross-repo
atomic commits are out of scope.

### No silent isolation or network downgrade

If a caller requested a sandbox minimum or network policy, the runtime fails
closed rather than silently running weaker. Isolation and network claims must
be ENFORCED. `DockerWorker` is a real digest-pinned backend; absence of an
engine or digest is still a refusal, never a silent downgrade.

---

## Sovereign Agent 1.x (educational line)

Authorized 2026-08-25. See the
[SOW metadata](sows/sovereign-agent-v1-educational-control-plane.md) and
[migration guide](migration-v0.7-to-v1.md).

1.x **does** include minimum local governance (outcomes, SOWs, rulings,
authority, acceptance) in order to teach a complete organization.

The [2026-09-07 always-on teaching ruling](rulings/2026-09-07-always-on-teaching-scope.md)
authorizes one Telegram adapter, a bounded MCP client, local versioned skills,
an explicit OS-supervised service, and an optional isolated container tool in
this distribution. These are educational implementations; ZeoCore remains
optional. The exclusions below apply outside that bounded teaching scope.

1.x still refuses:

- distributed fleet scheduling, Docker, Podman, SSH workers, Kubernetes, or
  cloud autoscaling
- HTTP APIs, Unix-socket services, web dashboards, Slack, email, webhooks, or
  voice as core features
- direct model-API SDKs and a ZeoCore runtime dependency
- a generic workflow language, plugin marketplace, or second capability
  framework
- general-purpose secrets management
- silent background daemons (teaching default is a foreground supervisor;
  live hosting is an explicit `service` command)
- claiming equivalent sandbox guarantees across providers
- claiming “zero humans” (zero employees, not zero human participation)

---

## How to change this list

1. File authorization (1.x holdings are recorded in this repository under
   `docs/rulings/`; corpus filing follows when `sow_repo` is set).
2. Record the reversal in `CHANGELOG.md` under the release that reverses it,
   and edit this file in the same change.
3. Sandcastle remains refused through v0.7 without a further reversal. 1.x
   also does not add Sandcastle.
4. Tag `v0.7.0` is never moved.
