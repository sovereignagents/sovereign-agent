# Credits

sovereign-agent is not a clean-room invention. This file lists every system, paper, and author whose work shaped it. Listed roughly in order of influence.

## Direct predecessors

- **NanoClaw** — Gavriel Cohen, 2026. A WhatsApp-based interface to Claude Code. Contributed Decisions 1–8 (per-session filesystem isolation, SessionQueue with three guarantees, filesystem IPC with atomic rename, idle preemption via sentinel, credential gateway, drift-corrected scheduler, mount allowlist outside project root, graceful shutdown detaches not kills). `github.com/qwibitai/nanoclaw`.

- **QuackVerse** — Rod Rivera, 2024–2025. A media-operations agent system. Contributed Decision 9 (tickets with explicit state) and Patterns A/B/C/D (discovery, summary artifact, structured error taxonomy, manifest discipline).

## Architectural influences

- **Claude Code** (Anthropic, 2024–). Closed source; architecture visible via public docs. The per-repository working directory pattern and the "session directory is the agent's memory" idea.

- **OpenHands / OpenDevin** — Wang et al., 2024. `github.com/All-Hands-AI/OpenHands`. "OpenHands: An Open Platform for AI Software Developers as Generalist Agents" (arxiv:2407.16741). The closest open-source production agent to sovereign-agent.

- **Aider** — Paul Gauthier, 2023–. `github.com/paul-gauthier/aider`. Per-repository state via `.aider/`.

- **SWE-agent** — Yang et al., 2024. "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering" (arxiv:2405.15793). The agent-computer interface framing.

## Memory and planning influences

- **Voyager** — Wang et al., 2023 (arxiv:2305.16291). File-based skill libraries.
- **Reflexion** — Shinn et al., 2023 (arxiv:2303.11366). Verbal reinforcement learning.
- **MemGPT** — Packer et al., 2023 (arxiv:2310.08560). Hierarchical memory; the four-part working/semantic/episodic/procedural taxonomy.
- **RAG** — Lewis et al., 2020 (arxiv:2005.11401). Retrieval-augmented generation.
- **Mem0** — Chhikara et al., 2025 (arxiv:2504.19413).
- **A-MEM** — Rasmussen et al., 2025 (arxiv:2501.13956).
- **GraphRAG** — Edge et al., 2024 (arxiv:2404.16130).
- **RAPTOR** — Sarthi et al., 2024 (arxiv:2401.18059).

## Pedagogical models

- **nanoGPT** — Andrej Karpathy, 2023. `github.com/karpathy/nanoGPT`. "Build a real system from scratch in a small number of files."
- **minitorch** — Sasha Rush (Cornell), 2020–2023. `minitorch.github.io`. "The tutorial's answer is the production code." sovereign-agent's chapter-drift CI check is a direct port.
- **Build a Large Language Model from Scratch** — Sebastian Raschka, 2024. Manning Publications.

## Third-party libraries

Runtime dependencies:

- `openai` (Apache 2.0) — OpenAI-compatible HTTP client
- `typer` (MIT) — CLI framework
- `croniter` (MIT) — cron expression parsing
- `python-dateutil` (Apache 2.0 / BSD) — date arithmetic

Optional extras:

- `evidently` (Apache 2.0)
- `opentelemetry-*` (Apache 2.0)
- `speechmatics-python`, `elevenlabs` — respective vendor licenses
- `rasa-pro` — Rasa license; check terms before redistribution
- `docker` (Apache 2.0)

Development dependencies:

- `pytest`, `pytest-asyncio`, `pytest-timeout` (MIT)
- `ruff` (MIT)
- `mypy` (MIT)
- `mkdocs`, `mkdocs-material` (MIT)
