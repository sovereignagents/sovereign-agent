"""Configuration loading.

See docs/architecture.md §2.20. Config can be loaded from env vars
(SOVEREIGN_AGENT_*) or from a TOML file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Literal


@dataclass
class Config:
    """sovereign-agent configuration.

    Defaults are tuned for "new user on a laptop with a Nebius key." Override
    via env vars (SOVEREIGN_AGENT_<FIELD> in uppercase) or TOML.
    """

    # Filesystem
    sessions_dir: Path = field(default_factory=lambda: Path("sessions"))
    mount_allowlist_path: Path = field(
        default_factory=lambda: Path.home() / ".config" / "sovereign-agent" / "mount-allowlist.json"
    )

    # Concurrency
    max_concurrent: int = 5
    poll_interval_s: float = 1.0

    # LLM provider
    llm_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    llm_api_key_env: str = "NEBIUS_KEY"
    llm_planner_model: str = "Qwen/Qwen3-Next-80B-A3B-Thinking"
    llm_executor_model: str = "Qwen/Qwen3-32B"
    llm_memory_model: str = "meta-llama/Llama-3.3-70B-Instruct"
    llm_embedding_model: str = "Qwen/Qwen3-Embedding-8B"

    # Execution mode
    bare_mode: bool = False

    # Observability
    observability_backend: Literal["jsonl", "evidently", "otel"] = "jsonl"

    # Feature toggles
    enable_voice: bool = False
    enable_structured_half: bool = True

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        """Load a Config from environment variables.

        Any field named `foo_bar` is populated from `SOVEREIGN_AGENT_FOO_BAR`
        (uppercase). Unset fields use the dataclass default.

        Also honors a `.env` file in the cwd if present, loaded in a
        simple KEY=VALUE manner.
        """
        _load_dotenv()
        env = env or dict(os.environ)
        overrides: dict[str, Any] = {}
        for f in fields(cls):
            envkey = f"SOVEREIGN_AGENT_{f.name.upper()}"
            if envkey in env:
                overrides[f.name] = _coerce(f.type, env[envkey])
        return cls(**overrides)

    @classmethod
    def from_toml(cls, path: Path) -> Config:
        import tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)
        section = data.get("sovereign_agent", data)
        overrides: dict[str, Any] = {}
        for f in fields(cls):
            if f.name in section:
                overrides[f.name] = _coerce(f.type, section[f.name])
        return cls(**overrides)

    def validate(self) -> list[str]:
        """Return a list of problems with this config, empty if OK."""
        issues: list[str] = []
        # Sessions directory can be created later, so only warn if its parent doesn't exist.
        if not self.sessions_dir.parent.exists():
            issues.append(f"sessions_dir parent does not exist: {self.sessions_dir.parent}")
        if not os.environ.get(self.llm_api_key_env):
            issues.append(f"LLM API key env var {self.llm_api_key_env!r} is not set")
        if self.max_concurrent <= 0:
            issues.append(f"max_concurrent must be > 0, got {self.max_concurrent}")
        if self.poll_interval_s <= 0:
            issues.append(f"poll_interval_s must be > 0, got {self.poll_interval_s}")
        return issues

    def to_dict(self) -> dict:
        return {
            f.name: getattr(self, f.name)
            if not isinstance(getattr(self, f.name), Path)
            else str(getattr(self, f.name))
            for f in fields(self)
        }


def _coerce(declared_type: Any, raw: str) -> Any:
    """Coerce an env-var string into the declared field type."""
    # `declared_type` is a type hint object (may be a string under future annotations).
    t = declared_type if not isinstance(declared_type, str) else declared_type
    if t in (int, "int"):
        return int(raw)
    if t in (float, "float"):
        return float(raw)
    if t in (bool, "bool"):
        return raw.lower() in {"1", "true", "yes", "on"}
    if t in (Path, "Path"):
        return Path(raw).expanduser()
    # Everything else: treat as str.
    return raw


def _load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader. Does NOT override existing env vars."""
    dotenv = path or Path(".env")
    if not dotenv.exists():
        return
    try:
        text = dotenv.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


__all__ = ["Config"]
