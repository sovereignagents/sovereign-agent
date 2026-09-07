# A dated map of architectural decisions

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

The decisions in the chapters are intended to remain useful when the reference projects change. This appendix fixes the evidence used in this construction draft. Links point to exact commits, not a moving main branch. The stated interpretation is ours unless the cited source explicitly documents the rationale.

| Project and pin | Primary evidence | Use in this book |
| --- | --- | --- |
| OpenClaw `354538083db0a8728e16238cbd0b7a304416ff24` | [Gateway architecture](https://github.com/openclaw/openclaw/blob/354538083db0a8728e16238cbd0b7a304416ff24/docs/concepts/architecture.md) | Chapters 1 and 6 compare a gateway's channel/session boundary with one thin adapter. |
| OpenClaw, same pin | [Session writer delivery authority](https://github.com/openclaw/openclaw/blob/354538083db0a8728e16238cbd0b7a304416ff24/src/auto-reply/reply/session-writer-delivery-authority.ts) | Chapter 10 compares concrete fencing scopes. OpenClaw has fencing; we make no claim that ours is unique. |
| NanoClaw `acc69a70962af6707aa8a6abba699bdaa7da95f8` | [README](https://github.com/nanocoai/nanoclaw/blob/acc69a70962af6707aa8a6abba699bdaa7da95f8/README.md) | Chapter 3 examines the documented choice to delegate reasoning to the Claude Agent SDK, against our owned loop. |
| NanoClaw, same pin | [Host sweep](https://github.com/nanocoai/nanoclaw/blob/acc69a70962af6707aa8a6abba699bdaa7da95f8/src/host-sweep.ts) | Chapter 7 examines events as hints and a durable rescan after missed events. |
| NanoClaw, same pin | [Container runner](https://github.com/nanocoai/nanoclaw/blob/acc69a70962af6707aa8a6abba699bdaa7da95f8/src/container-runner.ts) | Chapter 11 compares retaining a session with terminating a bounded report. It does not claim NanoClaw lacks recovery. |
| Hermes `d538f4e9297d7fa46193f638215d002d7a22edd7` | [Memory tool](https://github.com/NousResearch/hermes-agent/blob/d538f4e9297d7fa46193f638215d002d7a22edd7/tools/memory_tool.py) | Chapter 4 compares prompt memory and the documented cache-prefix rationale with explicit preference records. |
| Hermes, same pin | [Skills tool](https://github.com/NousResearch/hermes-agent/blob/d538f4e9297d7fa46193f638215d002d7a22edd7/tools/skills_tool.py) | Chapters 5 and 13 inspect progressive skill disclosure and shared-skill provenance; that helper does not establish the project's complete activation policy. |

## Recheck a comparison before extending it

Read the linked function and its callers at the pin. Identify the problem it solves and the boundary within which its checks apply. Quote only a short documented rationale, then label any inference about trade-offs. An experiment that would change our choice is more useful than a ranking of entire projects by one feature.

Do not extrapolate module counts, vulnerability anecdotes or a single observed default into claims about a whole project's security. The feedback that motivated this edition contained assertions of absent fencing and unsupported field-wide comparisons. Source inspection corrected those claims. They are not repeated as selling points.

NemoClaw and OpenShell are candidates for a later deployment comparison, not audited reference implementations in this edition's current map. Adding them requires a distinct teaching decision and pinned primary evidence. The optional [Zeocore bridge](zeocore-interop-v2.md) is a separately executed interoperability example, not a fourth substitute for the loop.
