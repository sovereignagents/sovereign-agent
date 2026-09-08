**Created:** 2026-09-07 · **Last-updated:** 2026-09-07 · **Status:** DRAFT

Supersedes `zeocore-interop-v1.md`: source URLs now use the verified canonical Git remote; the tested protocol and source pin are unchanged.

# Optional Zeocore integration through stdio MCP

The sixteen teaching chapters run without Zeocore. This appendix connects the same reader-owned loop and dispatcher to a separate Zeocore tool process. Sovereign Agent retains its own tool allowlist, argument validation, budgets and work records. Zeocore supplies its maintained tool implementation and MCP adapter in another Python environment.

`zeocore_server_v1.py` defines a bounded report word-count tool using Zeocore's public `BaseZeoTool`, registers it through `register_tool`, and serves it over stdio. It accepts no credentials and contacts no external service. The example proves the connection contract; it does not certify every Zeocore integration or authorize consequential operations.

Use a separate Python environment containing the optional `zeocore[mcp]` installation. The tested integration uses Zeocore commit `0a65423154c0d25384c19f534e88ee3598fef89e` and MCP SDK 2.1.1. Sovereign Agent's environment still requires only Pydantic at runtime. Point `SOVEREIGN_AGENT_ZEOCORE_PYTHON` at the absolute interpreter path for that separate environment, then run from the Sovereign Agent repository:

```bash
uv run pytest -m live tests/test_zeocore_interop.py
```

The test follows the actual data path: authored model request → local dispatcher → Sovereign Agent MCP client → separate Zeocore process → typed tool result → identified model observation. For `Lucy has six vanilla tubs`, the returned data must contain five words and twenty-five characters. The process must be stopped after the invocation. An absent interpreter setting skips the optional test; a configured but broken integration fails it.

The client passes an explicit empty environment to this credential-free server and permits only `word_count`. Discovering another advertised operation would not authorize it. When substituting a maintained integration, choose its exact operation, validate its arguments, define its result contract, and supply only the environment entries that server requires. Starting a host process grants it host execution rights; MCP does not provide a sandbox.

A real write operation also needs the approval and external-effect recovery boundary from Chapters 8–10. Do not wrap an arbitrary remote write as an ordinary read tool simply because it is reachable through MCP. The example intentionally chooses a read-only calculation so that protocol interoperability can be proved without mixing it with a purchasing contract.

The pinned Zeocore [MCP server](https://github.com/profrodai/zeocore/blob/0a65423154c0d25384c19f534e88ee3598fef89e/src/zeo_core/adapters/mcp/server.py) documents its registry snapshot and stdio runner. Its [public example](https://github.com/profrodai/zeocore/blob/0a65423154c0d25384c19f534e88ee3598fef89e/examples/mcp_server_usage.py) shows the typed tool interface used here. This appendix does not require readers to adopt Zeocore to understand or run the teaching implementation.
