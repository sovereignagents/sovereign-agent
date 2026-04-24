# Deployment

sovereign-agent v0.1.0 is meant to run on a single host: a Linux box, a Mac Mini, a laptop. That's the deliberate scope of "sovereign" — you own the compute, the data, and the failure modes.

This page collects the operational advice for that case. Multi-machine and hosted deployments are out of scope for v1.0 (see §6.3 of the architecture doc).

## Single-host layout

```
/var/lib/sovereign-agent/           # or wherever you point sessions_dir
└── sessions/
    ├── sess_<id1>/
    ├── sess_<id2>/
    └── archive/
        └── sess_<old>/             # moved here by the default cleanup task
```

Back up the whole `sessions/` tree. It contains every piece of state: `session.json` files, memory, ticket manifests, trace logs, workspace artifacts. Restore is `cp -r` — no database migration, no schema version to negotiate.

## Running the orchestrator

As a one-shot against a single task:

```bash
sovereign-agent run "Write a report on Q3 revenue and save it to workspace/report.md"
```

As a long-running process that picks up work as it arrives:

```bash
sovereign-agent serve
```

Under a process supervisor (systemd, supervisord, launchd, pm2 — pick your flavor):

```ini
# /etc/systemd/system/sovereign-agent.service
[Unit]
Description=sovereign-agent orchestrator
After=network.target

[Service]
Type=simple
User=sovereign
WorkingDirectory=/var/lib/sovereign-agent
EnvironmentFile=/etc/sovereign-agent/env
ExecStart=/usr/local/bin/sovereign-agent serve
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
```

SIGTERM triggers graceful shutdown — the orchestrator stops accepting new work but detaches active workers rather than killing them. On the next startup, any session whose state isn't terminal is resumed from disk.

## Environment

At minimum:

```bash
SOVEREIGN_AGENT_SESSIONS_DIR=/var/lib/sovereign-agent/sessions
NEBIUS_KEY=<your key>                  # or whichever provider you configured
```

For any non-default:

```bash
SOVEREIGN_AGENT_LLM_BASE_URL=https://api.tokenfactory.nebius.com/v1/
SOVEREIGN_AGENT_LLM_API_KEY_ENV=NEBIUS_KEY
SOVEREIGN_AGENT_LLM_PLANNER_MODEL=Qwen/Qwen3-Next-80B-A3B-Thinking
SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL=Qwen/Qwen3-32B
SOVEREIGN_AGENT_MAX_CONCURRENT=5
SOVEREIGN_AGENT_POLL_INTERVAL_S=1.0
```

## Mount allowlist

`~/.config/sovereign-agent/mount-allowlist.json` controls which host directories workers are allowed to read. Empty allowlist (the default) means no additional mounts — the safest possible start. Add roots only when a specific scenario needs them, and keep `allow_read_write: false` unless the scenario actually writes.

The file lives outside any path the agent can reach, by design. If you edit it, you don't need to restart the orchestrator — the default `allowlist_refresh` scheduled task re-reads it every 5 minutes.

## Observability

The always-on default is `logs/trace.jsonl` per session: one JSON object per line, zero dependencies. Read it with `jq`:

```bash
jq . sessions/sess_*/logs/trace.jsonl | less
```

Generate a markdown report for a session:

```bash
sovereign-agent report <session_id> > report.md
```

For dashboards, install the optional extras:

```bash
pip install sovereign-agent[evidently]      # LLMEval dashboards
pip install sovereign-agent[otel]           # OpenTelemetry export
```

Both backends read from `trace.jsonl` rather than replacing it, so the local file is always the source of truth.

## Backup / restore

Sessions are directories. Backup is `tar` or `rsync`:

```bash
tar -czf sovereign-agent-$(date +%F).tar.gz /var/lib/sovereign-agent/sessions/
```

Restore is untar into place. No migration. No versioning ceremony.

## Resource sizing

- **CPU:** minimal. The agent spends most of its time waiting on LLM calls.
- **Memory:** `max_concurrent × ~100MB` is a generous upper bound for the Python process footprint. Spawning containers (when that lands) would add per-container overhead.
- **Disk:** dominated by trace logs and memory files. For a busy system, budget a few GB per week per session and archive completed sessions weekly (the default scheduled task does this).
- **Network:** whatever your LLM provider's pricing scheme charges for.

## What not to do

- Do not point `sessions_dir` at a shared filesystem. Atomic rename guarantees are weaker across NFS/SMB and the framework doesn't try to work around it.
- Do not run two orchestrators against the same `sessions_dir`. There is no lease/coordination layer between instances — they will both try to work on the same sessions and results are undefined. If you need that, you need a multi-machine deployment, which is out of scope for v1.0.
- Do not try to edit `session.json` by hand. Use `sovereign-agent sessions show` to inspect, and let the framework write.
