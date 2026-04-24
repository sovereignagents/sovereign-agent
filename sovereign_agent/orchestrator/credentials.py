"""Credential gateway (Decision 5).

Skeleton for now: loads credentials from the process environment. The
per-tool scoping and injection-at-spawn-time is TODO when we wire Docker
worker spawning into orchestrator/main.py.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


class CredentialGateway:
    """Minimal credential gateway. Loads from env at construction.

    TODO:
      - per-tool scoping (so a worker running tool X only sees keys X needs)
      - injection into worker environment at spawn time
      - audit-log every injection (without values) via session.append_trace_event
    """

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = dict(env) if env is not None else dict(os.environ)

    def get(self, key: str) -> str | None:
        return self._env.get(key)

    def require(self, key: str) -> str:
        value = self._env.get(key)
        if not value:
            raise RuntimeError(f"credential {key!r} is not set")
        return value

    def for_tool(self, tool_name: str) -> dict[str, str]:
        """Return only the credentials this tool is allowed to see.

        Placeholder implementation returns empty — overriding this is how
        users scope credentials. A full implementation will consult a
        per-tool allowlist in ~/.config/sovereign-agent/tool-credentials.json.
        """
        log.debug("CredentialGateway.for_tool(%r): returning empty scope (TODO)", tool_name)
        return {}


__all__ = ["CredentialGateway"]
