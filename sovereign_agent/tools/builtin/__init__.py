"""Built-in tools. Registered on import.

These are small, deterministic, and work against the session directory the
agent is running in. They cover the things every agent needs: reading and
writing files in the workspace, listing files, and the protocol tools
`handoff_to_structured` and `complete_task`.

Tools that need session context (almost all of them) are implemented as
factory functions: you call them with a Session to get a bound tool. The
orchestrator registers them per-session, not globally.

The @register_tool decorator auto-generates the discovery schema. We declare
examples explicitly for tools that need more than the auto-example.
"""

from __future__ import annotations

from sovereign_agent._internal.atomic import atomic_write_text
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.errors import ToolError
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool


def make_builtin_registry(session: Session) -> ToolRegistry:
    """Build a ToolRegistry scoped to one session with the default builtins.

    This factory pattern is how the executor gets tools that know which
    session they belong to without us having to thread the Session through
    every tool call at execution time.
    """
    reg = ToolRegistry()

    # read_file ---------------------------------------------------------
    def read_file(path: str) -> ToolResult:
        """Read a file from the session's workspace/ directory."""
        try:
            resolved = session.path(f"workspace/{path}")
            if not resolved.exists():
                raise SovereignIOError(
                    code="SA_IO_NOT_FOUND",
                    message=f"file not found in workspace: {path}",
                    context={"path": path},
                )
            content = resolved.read_text(encoding="utf-8")
            return ToolResult(
                success=True,
                output={"path": path, "content": content, "size_bytes": len(content.encode())},
                summary=f"read {path} ({len(content)} chars)",
            )
        except SovereignIOError as exc:
            return ToolResult(success=False, output={}, summary=str(exc), error=exc)

    reg.register(
        _RegisteredTool(
            name="read_file",
            description="Read a file from the session's workspace/ directory.",
            fn=read_file,
            parameters_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=["SA_IO_NOT_FOUND", "SA_IO_SESSION_ESCAPE"],
            examples=[
                {"input": {"path": "notes.md"}, "output": {"path": "notes.md", "content": "..."}}
            ],
        )
    )

    # write_file --------------------------------------------------------
    def write_file(path: str, content: str) -> ToolResult:
        """Write a file to the session's workspace/ directory."""
        try:
            resolved = session.path(f"workspace/{path}")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(resolved, content)
            return ToolResult(
                success=True,
                output={"path": path, "bytes_written": len(content.encode())},
                summary=f"wrote {path} ({len(content)} chars)",
            )
        except SovereignIOError as exc:
            return ToolResult(success=False, output={}, summary=str(exc), error=exc)

    reg.register(
        _RegisteredTool(
            name="write_file",
            description="Write a file to the session's workspace/ directory.",
            fn=write_file,
            parameters_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=["SA_IO_SESSION_ESCAPE", "SA_IO_ATOMIC_WRITE_FAILED"],
            examples=[
                {
                    "input": {"path": "report.md", "content": "# Report\n..."},
                    "output": {"path": "report.md", "bytes_written": 10},
                }
            ],
            # v0.2: writes to the workspace — if two writers hit the same
            # path in the same turn with different contents, last-write
            # wins. We serialise these to keep behaviour predictable.
            parallel_safe=False,
        )
    )

    # list_files --------------------------------------------------------
    def list_files(path: str = ".") -> ToolResult:
        """List files in a directory under the session's workspace/."""
        try:
            resolved = session.path(f"workspace/{path}")
            if not resolved.exists():
                return ToolResult(
                    success=True,
                    output={"path": path, "entries": []},
                    summary=f"{path} has no entries (does not exist)",
                )
            entries = []
            for e in sorted(resolved.iterdir()):
                entries.append(
                    {
                        "name": e.name,
                        "type": "dir" if e.is_dir() else "file",
                        "size_bytes": e.stat().st_size if e.is_file() else None,
                    }
                )
            return ToolResult(
                success=True,
                output={"path": path, "entries": entries},
                summary=f"{path}: {len(entries)} entries",
            )
        except SovereignIOError as exc:
            return ToolResult(success=False, output={}, summary=str(exc), error=exc)

    reg.register(
        _RegisteredTool(
            name="list_files",
            description="List files in a directory under the session's workspace/.",
            fn=list_files,
            parameters_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=["SA_IO_SESSION_ESCAPE"],
            examples=[{"input": {"path": "."}, "output": {"path": ".", "entries": []}}],
        )
    )

    # handoff_to_structured ---------------------------------------------
    def handoff_to_structured(reason: str, context: str, data: dict) -> ToolResult:
        """Hand off control to the structured half.

        Writes an ipc/handoff_to_structured.json file. The executor will see
        this on its next poll and exit the ReAct loop with handoff_requested=True.
        """
        try:
            from datetime import UTC, datetime

            payload = {
                "version": 1,
                "from_half": "loop",
                "to_half": "structured",
                "written_at": datetime.now(tz=UTC).isoformat(),
                "session_id": session.session_id,
                "reason": reason,
                "context": context,
                "data": data,
                "return_instructions": data.get("return_instructions", ""),
            }
            handoff_path = session.ipc_dir / "handoff_to_structured.json"
            from sovereign_agent._internal.atomic import atomic_write_json

            atomic_write_json(handoff_path, payload)
            return ToolResult(
                success=True,
                output={"handoff_written": True, "exit_reason": "handoff"},
                summary=f"handoff to structured half: {reason}",
            )
        except Exception as exc:  # noqa: BLE001
            err = ToolError(
                code="SA_TOOL_EXECUTION_FAILED",
                message=f"handoff_to_structured failed: {exc}",
                cause=exc,
            )
            return ToolResult(success=False, output={}, summary=str(err), error=err)

    reg.register(
        _RegisteredTool(
            name="handoff_to_structured",
            description="Hand off control to the structured half for rule-following work.",
            fn=handoff_to_structured,
            parameters_schema={
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "context": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["reason", "context", "data"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=["SA_TOOL_EXECUTION_FAILED"],
            examples=[
                {
                    "input": {
                        "reason": "need_confirmation",
                        "context": "destructive action",
                        "data": {"action": "delete_file", "path": "x"},
                    },
                    "output": {"handoff_written": True, "exit_reason": "handoff"},
                }
            ],
            # v0.2: handoff terminates the loop. Never run alongside other
            # tool calls in the same turn — if a handoff co-exists with
            # parallel calls, the other results would be written but never
            # consumed by the loop half.
            parallel_safe=False,
        )
    )

    # complete_task -----------------------------------------------------
    def complete_task(result: dict) -> ToolResult:
        """Mark the session as complete. Writes ipc/session_complete.json."""
        try:
            payload = {"session_id": session.session_id, "result": result}
            from sovereign_agent._internal.atomic import atomic_write_json

            atomic_write_json(session.ipc_dir / "session_complete.json", payload)
            return ToolResult(
                success=True,
                output={"session_complete": True},
                summary="session marked complete",
            )
        except Exception as exc:  # noqa: BLE001
            err = ToolError(
                code="SA_TOOL_EXECUTION_FAILED",
                message=f"complete_task failed: {exc}",
                cause=exc,
            )
            return ToolResult(success=False, output={}, summary=str(err), error=err)

    reg.register(
        _RegisteredTool(
            name="complete_task",
            description="Mark the session as complete with the given result payload.",
            fn=complete_task,
            parameters_schema={
                "type": "object",
                "properties": {"result": {"type": "object"}},
                "required": ["result"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            error_codes=["SA_TOOL_EXECUTION_FAILED"],
            examples=[
                {
                    "input": {"result": {"answer": "rainy, 18C"}},
                    "output": {"session_complete": True},
                }
            ],
            # v0.2: complete_task is terminal — session ends after this.
            # Serialised for the same reason as handoff_to_structured.
            parallel_safe=False,
        )
    )

    return reg


__all__ = ["make_builtin_registry"]
