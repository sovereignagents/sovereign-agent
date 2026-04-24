"""Mount allowlist (Decision 7).

The allowlist lives at ~/.config/sovereign-agent/mount-allowlist.json,
OUTSIDE the project root. Workers that mount the project root cannot reach
this file, so they cannot tamper with it.

Current status: validate() and load_allowlist() are wired up; the
orchestrator has not yet been taught to actually mount additional host
directories into worker containers (that's part of the Docker-spawning
work that's still a skeleton). When that lands, it will call validate()
before every mount.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from sovereign_agent._internal.atomic import atomic_write_json
from sovereign_agent.errors import ValidationError

ALLOWLIST_PATH: Path = Path.home() / ".config" / "sovereign-agent" / "mount-allowlist.json"

# Hard-coded default blocked patterns. User additions are MERGED with these
# (not replaced): users can add to the blocklist but cannot subtract.
DEFAULT_BLOCKED_PATTERNS: frozenset[str] = frozenset(
    {
        ".ssh",
        ".gnupg",
        ".gpg",
        ".aws",
        ".azure",
        ".gcloud",
        ".kube",
        ".docker",
        "credentials",
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "id_rsa",
        "id_ed25519",
        "private_key",
        ".secret",
        ".pki",
    }
)


@dataclass
class AllowedRoot:
    path: Path
    allow_read_write: bool = False
    description: str = ""


@dataclass
class MountAllowlist:
    allowed_roots: list[AllowedRoot] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)
    non_main_read_only: bool = False

    def effective_blocked(self) -> frozenset[str]:
        """User patterns MERGED with defaults — users cannot remove defaults."""
        return DEFAULT_BLOCKED_PATTERNS | frozenset(self.blocked_patterns)


@dataclass
class AdditionalMount:
    host_path: Path
    container_path: Path


@dataclass
class MountValidationResult:
    allowed: bool
    reason: str
    resolved_host: Path | None = None
    readonly: bool = True


def load_allowlist(path: Path | None = None) -> MountAllowlist:
    """Load the allowlist from disk. Generates an empty template on first run."""
    path = path or ALLOWLIST_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        empty = {
            "allowed_roots": [],
            "blocked_patterns": [],
            "non_main_read_only": False,
            "_comment": (
                "Empty allowlist = no additional mounts allowed. Safest default. "
                "Add roots to allowed_roots to enable specific mounts."
            ),
        }
        atomic_write_json(path, empty)
        return MountAllowlist()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    roots = [
        AllowedRoot(
            path=Path(r["path"]).expanduser(),
            allow_read_write=bool(r.get("allow_read_write", False)),
            description=r.get("description", ""),
        )
        for r in data.get("allowed_roots", [])
    ]
    return MountAllowlist(
        allowed_roots=roots,
        blocked_patterns=list(data.get("blocked_patterns", [])),
        non_main_read_only=bool(data.get("non_main_read_only", False)),
    )


def validate_mount(requested: AdditionalMount, allowlist: MountAllowlist) -> MountValidationResult:
    """Check that a requested mount is safe to allow."""
    host = Path(str(requested.host_path)).expanduser()
    if not host.exists():
        return MountValidationResult(
            allowed=False,
            reason=f"host path does not exist: {host}",
        )
    try:
        resolved = host.resolve(strict=True)
    except OSError as exc:
        return MountValidationResult(
            allowed=False,
            reason=f"host path does not resolve: {exc}",
        )

    # Check blocked patterns against every component of the resolved path.
    parts = set(resolved.parts)
    blocked = allowlist.effective_blocked()
    for part in parts:
        if part in blocked:
            return MountValidationResult(
                allowed=False,
                reason=f"path component {part!r} is in the blocked pattern list",
                resolved_host=resolved,
            )

    # Check the path is under one of the allowed roots.
    matching_root: AllowedRoot | None = None
    for root in allowlist.allowed_roots:
        try:
            resolved.relative_to(root.path.resolve())
            matching_root = root
            break
        except ValueError:
            continue
    if matching_root is None:
        return MountValidationResult(
            allowed=False,
            reason="path is not under any allowed root",
            resolved_host=resolved,
        )
    readonly = not matching_root.allow_read_write
    return MountValidationResult(
        allowed=True,
        reason="ok",
        resolved_host=resolved,
        readonly=readonly,
    )


def require_mount(
    requested: AdditionalMount, allowlist: MountAllowlist | None = None
) -> MountValidationResult:
    """Convenience: validate a mount and raise ValidationError if denied."""
    al = allowlist if allowlist is not None else load_allowlist()
    result = validate_mount(requested, al)
    if not result.allowed:
        raise ValidationError(
            code="SA_VAL_INVALID_CONFIG",
            message=f"mount not allowed: {result.reason}",
            context={
                "host_path": str(requested.host_path),
                "container_path": str(requested.container_path),
                "reason": result.reason,
            },
        )
    return result


__all__ = [
    "ALLOWLIST_PATH",
    "DEFAULT_BLOCKED_PATTERNS",
    "AllowedRoot",
    "MountAllowlist",
    "AdditionalMount",
    "MountValidationResult",
    "load_allowlist",
    "validate_mount",
    "require_mount",
]
