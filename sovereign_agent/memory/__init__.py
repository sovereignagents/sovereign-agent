"""Memory subsystem (skeleton).

See docs/architecture.md §2.12 for the full specification. The API here is
stable; the behaviors marked TODO are placeholders that the first lessons
will replace with real implementations (retrieval, consolidation,
embedding-cache management).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from sovereign_agent._internal.atomic import atomic_write_json, atomic_write_text
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.errors import ValidationError
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc


class MemoryType(StrEnum):
    WORKING = "working"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


@dataclass
class MemoryEntry:
    id: str
    type: MemoryType
    path: Path
    content: str
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    embedding: list[float] | None = None


class MemoryStore:
    """File-backed memory store for one session.

    Structure:
        session/memory/
            working.md                       (single file, overwritten per turn)
            semantic/fact_<id>.md
            episodic/<timestamp>_<id>.md
            procedural/<id>.md
            index.json                       (manifest of all files)
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Working memory
    # ------------------------------------------------------------------
    def working(self) -> str:
        path = self.session.memory_dir / "working.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def set_working(self, content: str) -> None:
        atomic_write_text(self.session.memory_dir / "working.md", content)
        self._log_event("memory.set_working", {"size": len(content)})

    def clear_working(self) -> None:
        self.set_working("")

    # ------------------------------------------------------------------
    # Semantic / episodic / procedural
    # ------------------------------------------------------------------
    def write_fact(
        self,
        memory_type: MemoryType,
        fact_id: str,
        content: str,
        metadata: dict | None = None,
    ) -> MemoryEntry:
        if memory_type == MemoryType.WORKING:
            raise ValidationError(
                code="SA_VAL_BAD_TYPE",
                message="write_fact() does not accept WORKING; use set_working()",
            )
        subdir = self.session.memory_dir / memory_type.value
        subdir.mkdir(parents=True, exist_ok=True)
        path = subdir / f"{fact_id}.md"
        now = now_utc()
        meta = dict(metadata or {})
        meta.setdefault("id", fact_id)
        meta.setdefault("created_at", now.isoformat())
        meta.setdefault("updated_at", now.isoformat())
        body = _render_fact(meta, content)
        atomic_write_text(path, body)
        self._update_index(memory_type, fact_id, path, meta)
        self._log_event("memory.fact_written", {"type": memory_type.value, "id": fact_id})
        return MemoryEntry(
            id=fact_id,
            type=memory_type,
            path=path,
            content=content,
            metadata=meta,
            created_at=now,
            updated_at=now,
        )

    def read_fact(self, fact_id: str) -> MemoryEntry:
        # Search across all non-working subdirs.
        for mtype in (MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL):
            path = self.session.memory_dir / mtype.value / f"{fact_id}.md"
            if path.exists():
                meta, body = _parse_fact(path.read_text(encoding="utf-8"))
                return MemoryEntry(
                    id=fact_id,
                    type=mtype,
                    path=path,
                    content=body,
                    metadata=meta,
                )
        raise SovereignIOError(
            code="SA_IO_NOT_FOUND",
            message=f"fact {fact_id!r} not found",
            context={"fact_id": fact_id},
        )

    def list_facts(
        self,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Enumerate facts, optionally filtered by type and/or tags."""
        types = (
            [memory_type]
            if memory_type is not None
            else [MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL]
        )
        out: list[MemoryEntry] = []
        for mt in types:
            subdir = self.session.memory_dir / mt.value
            if not subdir.exists():
                continue
            for p in sorted(subdir.iterdir()):
                if p.suffix != ".md":
                    continue
                try:
                    meta, body = _parse_fact(p.read_text(encoding="utf-8"))
                except OSError:
                    continue
                if tags:
                    have = set(meta.get("tags", []) or [])
                    if not set(tags).intersection(have):
                        continue
                out.append(
                    MemoryEntry(
                        id=meta.get("id", p.stem),
                        type=mt,
                        path=p,
                        content=body,
                        metadata=meta,
                    )
                )
        return out

    def delete_fact(self, fact_id: str) -> None:
        try:
            entry = self.read_fact(fact_id)
        except SovereignIOError:
            return
        try:
            entry.path.unlink()
        except FileNotFoundError:
            pass
        self._drop_from_index(fact_id)
        self._log_event("memory.fact_deleted", {"id": fact_id})

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------
    @property
    def index_path(self) -> Path:
        return self.session.memory_dir / "index.json"

    def read_index(self) -> dict:
        if not self.index_path.exists():
            return {"entries": []}
        with open(self.index_path, encoding="utf-8") as f:
            return json.load(f)

    def _update_index(self, memory_type: MemoryType, fact_id: str, path: Path, meta: dict) -> None:
        idx = self.read_index()
        entries = idx.setdefault("entries", [])
        # Replace any existing entry for this id.
        entries = [e for e in entries if e.get("id") != fact_id]
        entries.append(
            {
                "id": fact_id,
                "type": memory_type.value,
                "path": str(path.relative_to(self.session.directory)),
                "metadata": meta,
            }
        )
        idx["entries"] = entries
        atomic_write_json(self.index_path, idx)

    def _drop_from_index(self, fact_id: str) -> None:
        idx = self.read_index()
        idx["entries"] = [e for e in idx.get("entries", []) if e.get("id") != fact_id]
        atomic_write_json(self.index_path, idx)

    def _log_event(self, event_type: str, payload: dict) -> None:
        try:
            self.session.append_trace_event(
                {
                    "event_type": event_type,
                    "actor": "memory",
                    "timestamp": now_utc().isoformat(),
                    "payload": payload,
                }
            )
        except Exception:  # noqa: BLE001
            # Trace failures are never fatal.
            pass


# ---------------------------------------------------------------------------
# YAML-frontmatter-style fact parser (minimal, not a full YAML parser)
# ---------------------------------------------------------------------------


def _render_fact(metadata: dict, content: str) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {json.dumps(value)}")
    lines.append("---")
    lines.append("")
    lines.append(content.rstrip())
    return "\n".join(lines) + "\n"


def _parse_fact(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    try:
        _, fm, body = text.split("---", 2)
    except ValueError:
        return {}, text
    meta: dict = {}
    for raw in fm.strip().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        try:
            meta[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            meta[key] = value
    return meta, body.lstrip("\n")


# Retrieval and consolidation: TODO lessons implement these ------------------


class MemoryRetrieval:
    """Hybrid retrieval over a MemoryStore. TODO: implement.

    The API is stable. The first lesson in the lessons feed is expected to
    provide a real implementation: embedding-based similarity with
    recency decay and optional cross-encoder rerank.
    """

    def __init__(self, store: MemoryStore, **_: object) -> None:
        self.store = store

    async def retrieve(
        self,
        query: str,  # noqa: ARG002 — placeholder
        k: int = 5,
        types: list[MemoryType] | None = None,
    ) -> list[MemoryEntry]:
        """Placeholder: returns the most recent `k` facts.

        TODO: replace with real similarity retrieval.
        """
        entries = self.store.list_facts()
        if types is not None:
            entries = [e for e in entries if e.type in types]
        # Most-recent-first heuristic: rely on index ordering, which is
        # append-order. Good enough as a placeholder.
        return entries[-k:]


class MemoryConsolidation:
    """Summarize working memory into semantic facts. TODO: implement."""

    def __init__(self, store: MemoryStore, **_: object) -> None:
        self.store = store

    async def consolidate(self) -> list[MemoryEntry]:
        """Placeholder: turns non-empty working memory into a single semantic fact."""
        working = self.store.working()
        if not working.strip():
            return []
        from secrets import token_hex

        entry = self.store.write_fact(
            MemoryType.SEMANTIC,
            f"fact_{token_hex(3)}",
            working,
            metadata={"source": "consolidation-placeholder"},
        )
        self.store.clear_working()
        return [entry]


__all__ = [
    "MemoryType",
    "MemoryEntry",
    "MemoryStore",
    "MemoryRetrieval",
    "MemoryConsolidation",
]
