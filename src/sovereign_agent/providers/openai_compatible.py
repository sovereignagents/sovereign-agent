"""OpenAI-compatible intelligence provider (Ollama by default).

Unlike the CLI-agent providers, this one talks to an HTTP `/v1/chat/completions`
endpoint: a local Ollama server by default, or any OpenAI-compatible server
(vLLM, LM Studio, OpenAI itself). Registered as ``ollama`` because a local
Ollama is the zero-config default.

Reads only these environment variables:

- ``SOVEREIGN_AGENT_LLM_BASE_URL`` — default ``http://localhost:11434/v1``.
- ``SOVEREIGN_AGENT_LLM_MODEL`` — default ``qwen3`` (``..._EXECUTOR_MODEL`` alias).
- ``SOVEREIGN_AGENT_LLM_API_KEY`` — optional bearer; blank for local Ollama.

Like every provider, the model only *proposes* an ``ActorReport``; the
organization re-validates it against the ledger before anything commits.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from sovereign_agent.http_transport import request as bounded_request
from sovereign_agent.models import ActorReport
from sovereign_agent.providers.base import (
    InvocationRequest,
    InvocationSpec,
    ProviderCapabilities,
    ProviderEvent,
    allowed_environment,
    parse_json_line,
)

LLM_ENVIRONMENT: tuple[str, ...] = (
    "SOVEREIGN_AGENT_LLM_BASE_URL",
    "SOVEREIGN_AGENT_LLM_MODEL",
    "SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL",
    "SOVEREIGN_AGENT_LLM_API_KEY",
)
DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MODEL = "qwen3"
_VALID_STATUS = {"completed", "blocked", "failed"}
_SYSTEM_PROMPT = (
    "You are a Sovereign Agent operator actor. You PROPOSE work; you never commit it "
    "and cannot accept your own work. Reply with ONLY a single JSON object, no prose "
    'or code fences, with exactly: {"status": "completed"|"blocked"|"failed", '
    '"proposed_restock_units": <integer or null>, "proposed_checks": [<string>...], '
    '"notes": <short string>}. For a replenishment, propose an integer restock quantity '
    "that keeps stock at or above its reorder point; the organization re-validates it."
)


def resolve_config() -> tuple[str, str, str]:
    """Return (base_url, model, api_key) from the documented environment."""
    base = os.environ.get("SOVEREIGN_AGENT_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = (
        os.environ.get("SOVEREIGN_AGENT_LLM_MODEL")
        or os.environ.get("SOVEREIGN_AGENT_LLM_EXECUTOR_MODEL")
        or DEFAULT_MODEL
    )
    return base, model, os.environ.get("SOVEREIGN_AGENT_LLM_API_KEY", "")


class OpenAICompatibleProvider:
    name = "ollama"
    executable = "python"
    requires_terminal_event = False
    authentication_environment = LLM_ENVIRONMENT

    def probe(self) -> ProviderCapabilities:
        # No network: doctor stays fast and offline. Reachability is proven at
        # assignment time, where an unreachable endpoint yields a failed report.
        base, model, _ = resolve_config()
        return ProviderCapabilities(
            available=True,
            version=f"{model} @ {base}",
            print_mode=True,
            streaming=True,
            structured_result=True,
            workspace_write=True,
        )

    def build_invocation(self, request: InvocationRequest) -> InvocationSpec:
        return InvocationSpec(
            argv=[
                "python",
                "-m",
                "sovereign_agent.providers.openai_compatible",
                str(request.output),
                request.prompt,
            ],
            cwd=request.workspace,
            env=allowed_environment(*self.authentication_environment),
        )

    def parse_event(self, line: str) -> ProviderEvent | None:
        return parse_json_line(line)


def _chat(
    base: str, model: str, api_key: str, messages: list[dict[str, str]], timeout: float
) -> str:
    body = {"model": model, "messages": messages, "stream": False, "temperature": 0}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = bounded_request(
        f"{base}/chat/completions", data=json.dumps(body).encode(), headers=headers, timeout=timeout
    )
    if response.status != 200:
        raise OSError("model HTTP request failed")
    return str(json.loads(response.body)["choices"][0]["message"]["content"])


def _extract_json_object(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model reply contained no JSON object")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model reply was not a JSON object")
    return parsed


def _coerce_units(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def run_llm_report(output: Path, prompt: str, *, timeout: float = 120.0) -> ActorReport:
    """Ask the configured model to propose an ActorReport, and write it. An
    unreachable or malformed endpoint yields an honest ``failed`` report."""
    output.mkdir(parents=True, exist_ok=True)
    base, model, api_key = resolve_config()
    try:
        scope = str(json.loads(prompt)["statement_of_work"]["scope"])
    except json.JSONDecodeError, KeyError, TypeError:
        scope = prompt
    try:
        content = _chat(
            base,
            model,
            api_key,
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Assignment scope:\n{scope}\n\nJSON object only."},
            ],
            timeout,
        )
        parsed = _extract_json_object(content)
        raw_status = parsed.get("status")
        checks = parsed.get("proposed_checks")
        report = ActorReport(
            status=str(raw_status) if raw_status in _VALID_STATUS else "completed",
            proposed_restock_units=_coerce_units(parsed.get("proposed_restock_units")),
            changed_artifacts=["inventory.md"],
            proposed_checks=(
                [str(c) for c in checks]
                if isinstance(checks, list)
                else ["inventory_at_or_above_reorder_point", "cash_reconciles"]
            ),
            questions=[],
            notes=(str(parsed.get("notes") or f"proposed by {model}"))[:500],
        )
    except OSError, ValueError, KeyError:
        notes = "OpenAI-compatible endpoint failed: transport or response validation failed"
        report = ActorReport(status="failed", proposed_restock_units=None, notes=notes[:500])
    (output / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (output / "artifacts.json").write_text(
        '{"inventory.md": "replenishment proposed"}', encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    run_llm_report(Path(args[0]), args[1] if len(args) > 1 else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
