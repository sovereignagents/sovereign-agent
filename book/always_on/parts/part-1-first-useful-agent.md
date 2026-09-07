# Build Lucy’s first useful agent

**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

Lucy needs a morning brief grounded in actual products and supplier data. First make one model call. Then expose deterministic shop functions as validated tools. Finally implement the bounded loop that alternates model requests, tool results and a final explanation.

At the end of this part, the agent can assemble a replenishment draft. It cannot purchase stock. That restriction lets you examine grounding, arithmetic, invalid arguments and stopping conditions before adding external consequences. Use several products now so later chapters can spend their attention on agent behavior rather than expanding a one-item data model.

The useful artifact is small enough to trace: shop fixture → model request → validated tool call → structured observation → draft. When a recommendation is wrong, inspect that path before adding another prompt or another agent.

- [1. Make the first model call for Lucy](../ch01_first_model_call/README.md)
- [2. Give the agent reliable shop tools](../ch02_shop_tools/README.md)
- [3. Build the model and tool loop](../ch03_agent_loop/README.md)
