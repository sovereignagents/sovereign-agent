# Example: isolated worker

## What it shows

Module 2 in action. A subprocess worker whose filesystem view is
**kernel-confined** to the session directory — no Docker, no daemon,
no image.

The probe:

1. Writes `sandbox_probe.txt` inside the session dir → **allowed**.
2. Reads `/etc/shadow` (Linux) or `/etc/sudoers` (macOS) → **denied** if
   the sandbox is enforcing.
3. Reads `/etc/hosts` (a normally-world-readable file NOT in the
   allow-list) → **denied** on a working sandbox, **allowed** if
   running unconfined.

## Run

```bash
python -m examples.isolated_worker.run
```

## What you'll see on different hosts

| Host | Selected policy | Forbidden read | Meaning |
|---|---|---|---|
| Modern Linux (≥ 5.13) | `LandlockPolicy` | **DENIED** | Kernel is enforcing |
| macOS (any recent) | `SandboxExecPolicy` | **DENIED** | Apple sandbox is enforcing |
| Older Linux / Windows | `NoOpPolicy` + warning | **ALLOWED** | Platform lacks the primitive |

On a host where the sandbox is enforcing, the probe cannot escape even
if the subprocess runs with elevated privileges. Landlock is applied
AT the kernel; there is no user-space way around it.

## The one line that matters

```python
from sovereign_agent._internal.isolation import detect_best_policy
from sovereign_agent.orchestrator.worker import SubprocessWorker

worker = SubprocessWorker(
    isolation_policy=detect_best_policy(),   # <-- picks the strongest available
    allow_network=False,
)
```

`detect_best_policy()` returns the best primitive for the host and
falls back to `NoOpPolicy` with a warning if none are available. You
never silently run unconfined.

## Fail-closed behaviour

If you pass `LandlockPolicy()` explicitly on a kernel that doesn't
support it, the shim refuses to `exec` the child and exits non-zero
with a clear message. You do not accidentally run unconfined just
because the kernel is old — you get an error.

```
landlock_shim: Landlock not available on this kernel
(ABI probe returned -1, errno=38). Requires Linux >=5.13.
```

## Caveats

- Network isolation is advisory for Landlock < ABI 4 (Linux < 6.7). On
  older kernels, `--deny-network` is accepted but not enforced. The
  shim logs this fact so you know.
- `sandbox-exec(1)` is marked deprecated by Apple ("SBPL is SPI"). It
  still works through at least macOS 15 but has no long-term
  commitment. If it ever goes away, we swap the macOS backend for
  Endpoint Security without changing the policy's public interface.
