# Field guide to the agent ecosystem

This book is deliberately framework-independent. Its mechanisms remain necessary whether
the provider is a script, a hosted model, a local model, or a networked agent. Current
protocols give those mechanisms recognizable interfaces, but they do not replace them.

This guide maps the book's vocabulary to the wider agent ecosystem. It is a translation
layer, not a claim that two concepts are identical.

## MCP connects models to capabilities

The [Model Context Protocol specification](https://modelcontextprotocol.io/specification/2025-06-18/index)
defines a client-server protocol for exposing prompts, resources, and tools. Its control
model is especially useful alongside Chapters 3 and 4: prompts are user-controlled,
resources are application-controlled, and tools are model-controlled requests whose
effects remain the host application's responsibility.

In this book's terms, MCP can describe and transport a capability. It does not decide that
a particular actor is authorized to use that capability for a particular statement of
work. Tool discovery still is not tool authority. A host still needs deny-first policy,
workspace and subject checks, explicit consent where required, and a durable receipt for
the action it actually committed.

MCP also makes the untrusted-data boundary concrete. Resources, tool results, and elicited
input may all contain text that looks like instruction. Chapter 3's rule still applies:
provider and external output enters as data, then schema and policy decide what the host
may do with it.

## A2A connects independent agents

The [Agent2Agent protocol specification](https://a2a-protocol.org/latest/specification/)
defines discovery through Agent Cards and a lifecycle built from messages, tasks, status,
and artifacts. It supports synchronous, streaming, and long-running asynchronous work
across agents that do not expose their internal memory or tools.

That makes A2A a natural transport for the delegation boundary built in Chapters 2, 5,
and 7. An A2A task can carry or refer to governed work; an artifact can carry a proposed
result; task status can report protocol progress. None of those facts alone proves this
book's `ACCEPTED` claim. The receiving organization still has to bind the remote actor to
current authority, validate the artifact, rerun outcome checks against the current world,
and preserve independent review.

The distinction is useful in both directions. This book does not need to invent a wire
protocol for agent interoperability, and an A2A implementation does not need to pretend
transport-level task completion is causal proof.

## OpenTelemetry records execution signals

The [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
provide common names for traces, metrics, events, resources, and attributes. The GenAI
conventions include agent, conversation, tool, retrieval, usage, and evaluation concepts.
Those conventions make operations from different libraries and providers easier to
correlate.

Chapters 1, 2, and 12 ask a narrower question: which observations are sufficient for the
claim being made? A span can show that a tool call occurred. It does not, by its presence,
prove that the correct subject changed, that the change came from this execution, or that
the world did not move afterward. Telemetry becomes evidence only when its identity,
inputs, timing, and relationship to the outcome satisfy the proof contract.

Use standard telemetry where it fits. Keep the evidence ledger's stronger causal and
retention requirements explicit rather than assuming a trace backend supplies them.

## OWASP names the adversary

The [OWASP Agentic AI threats and mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/)
organizes risks created when generative models gain memory, tools, goals, and autonomy.
Prompt injection, tool misuse, privilege abuse, memory poisoning, and cascading agent
failures are contemporary names for boundaries this book tests mechanically.

The mapping is direct but not complete:

- Chapter 1's canonical-versus-derived distinction limits memory poisoning and makes
  projection tampering detectable.
- Chapter 3 parses provider output and separates discovery from authorization.
- Chapter 4 checks path, network, credential, tool, and process isolation independently.
- Chapter 5 expires authority with leases, fencing tokens, and session incarnations.
- Chapters 6 and 7 preserve evidence across crashes and unattended execution.

A threat list helps a team ask what could go wrong. It does not demonstrate that a
specific control refuses the attack. The exercises in these chapters supply that second
step by making the learner run the adversarial path and inspect the resulting state.

## NIST frames residual risk and deployment evidence

The [NIST AI Risk Management Framework Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
is a cross-sector companion to the AI RMF. It organizes generative-AI risk work around
governance, mapping, measurement, and management rather than prescribing one agent
architecture.

Chapter 12's release ladder fits inside that larger risk process. Deterministic tests,
installed-artifact checks, credentialed provider evaluation, human-reviewed pilots,
canaries, and wider release are different evidence environments. A team can use the NIST
profile to identify affected people, harms, controls, and residual risks while using this
book's receipts and proof packs to make individual operational claims inspectable.

Neither system certifies the other. A complete proof pack may still encode an inadequate
acceptance rule. A completed risk worksheet may still describe a control that was never
exercised. Governance documents and executable evidence have to meet at the same exact
release candidate.

## What changes when these protocols are present

The practical architecture has three layers:

1. **Interoperability:** MCP exposes tools and context; A2A exchanges tasks, messages, and
   artifacts.
2. **Observability:** OpenTelemetry records operations and correlations in a shared
   vocabulary.
3. **Governance and proof:** the host binds authority, state, effects, verification, and
   acceptance under the invariants built in this book.

The layers reinforce one another, but no layer may silently inherit another's guarantee.
An advertised tool is not authorized work. A completed remote task is not an accepted
outcome. A trace is not a causal proof. A policy document is not an exercised refusal.

That separation is why the book's mechanisms remain relevant as protocols and providers
change. The interfaces can evolve. The questions stay stable: who was allowed to act,
inside which boundary, on which subject, against which current state, with what surviving
evidence, and who checked the result?

Return to the [book contents](README.md) or continue with
[Advanced mechanisms](ADVANCED_MECHANISMS.md).
