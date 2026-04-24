"""Structured error taxonomy for sovereign-agent.

Pattern C from the architecture doc: errors carry a machine-readable category
code prefix (SA_SYS_*, SA_VAL_*, SA_IO_*, SA_EXT_*, SA_TOOL_*) so agents and
the framework can branch on category without parsing exception class names
or stack traces.

See docs/architecture.md §1.5 Pattern C and §2.8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ErrorCategory(StrEnum):
    """The five error categories. Agents branch on this, not on exception class."""

    SYS = "SYS"
    VAL = "VAL"
    IO = "IO"
    EXT = "EXT"
    TOOL = "TOOL"


@dataclass
class SovereignError(Exception):
    """Base class for all structured errors in sovereign-agent.

    The `code` field is the machine-readable identifier (e.g. "SA_EXT_AUTH_EXPIRED").
    The `category` field is the prefix (e.g. ErrorCategory.EXT).
    The `message` field is human-readable.
    The `context` field is a free-form dict for structured detail.
    The `retriable` field is a hint to the SessionQueue; ExternalError defaults True.
    The `cause` field preserves the original exception when wrapping one.
    """

    code: str
    category: ErrorCategory
    message: str
    context: dict = field(default_factory=dict)
    retriable: bool = False
    cause: BaseException | None = None

    def __post_init__(self) -> None:
        # Validate that the code prefix matches the declared category.
        # Codes look like "SA_<CATEGORY>_<NAME>" per the canonical list.
        expected_prefix = f"SA_{self.category.value}_"
        if not self.code.startswith(expected_prefix):
            raise ValueError(
                f"error code {self.code!r} does not match category "
                f"{self.category.value!r} (expected prefix {expected_prefix!r})"
            )
        # Initialize the Exception base class so str(err) gives something useful.
        super().__init__(f"[{self.code}] {self.message}")

    def to_dict(self) -> dict:
        """Serializable form, used by the trace writer."""
        return {
            "code": self.code,
            "category": self.category.value,
            "message": self.message,
            "context": self.context,
            "retriable": self.retriable,
            "cause": repr(self.cause) if self.cause is not None else None,
        }


class SystemError(SovereignError):  # noqa: A001 — intentional shadow of builtin in SA namespace
    """SA_SYS_* — system/infra errors (crash, OOM, disk full, PID lost)."""

    def __init__(self, code: str, message: str, **kwargs: object) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.SYS,
            message=message,
            **kwargs,  # type: ignore[arg-type]
        )


class ValidationError(SovereignError):
    """SA_VAL_* — input validation errors (bad config, malformed input)."""

    def __init__(self, code: str, message: str, **kwargs: object) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.VAL,
            message=message,
            **kwargs,  # type: ignore[arg-type]
        )


class IOError(SovereignError):  # noqa: A001 — intentional shadow in SA namespace
    """SA_IO_* — local I/O errors (not found, permission, corrupt manifest)."""

    def __init__(self, code: str, message: str, **kwargs: object) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.IO,
            message=message,
            **kwargs,  # type: ignore[arg-type]
        )


class ExternalError(SovereignError):
    """SA_EXT_* — external service errors (LLM timeout, auth expired, rate limit).

    Defaults to retriable=True because most external errors are transient.
    """

    def __init__(self, code: str, message: str, retriable: bool = True, **kwargs: object) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.EXT,
            message=message,
            retriable=retriable,
            **kwargs,  # type: ignore[arg-type]
        )


class ToolError(SovereignError):
    """SA_TOOL_* — tool-specific logic errors.

    Distinct from SA_VAL (which is about input validation) and SA_EXT (which
    is about the service a tool calls). SA_TOOL errors mean the tool ran,
    did its job, and the job failed in a domain-specific way.
    """

    def __init__(self, code: str, message: str, **kwargs: object) -> None:
        super().__init__(
            code=code,
            category=ErrorCategory.TOOL,
            message=message,
            **kwargs,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# The canonical error code list.
#
# Extensions may add their own codes following the SA_<CATEGORY>_<NAME> convention.
# Keeping them enumerated in one place lets grep find every possible error.
# ---------------------------------------------------------------------------

CANONICAL_CODES: dict[ErrorCategory, frozenset[str]] = {
    ErrorCategory.SYS: frozenset(
        {
            "SA_SYS_DISK_FULL",
            "SA_SYS_OOM",
            "SA_SYS_PROCESS_CRASHED",
            "SA_SYS_PID_LOST",
            "SA_SYS_UNEXPECTED",
        }
    ),
    ErrorCategory.VAL: frozenset(
        {
            "SA_VAL_INVALID_CONFIG",
            "SA_VAL_MISSING_REQUIRED_FIELD",
            "SA_VAL_BAD_TYPE",
            "SA_VAL_INVALID_DISCOVERY_SCHEMA",
            "SA_VAL_INVALID_STATE_TRANSITION",
            "SA_VAL_INVALID_PLANNER_OUTPUT",
            "SA_VAL_INVALID_HANDOFF_SCHEMA",
        }
    ),
    ErrorCategory.IO: frozenset(
        {
            "SA_IO_NOT_FOUND",
            "SA_IO_PERMISSION_DENIED",
            "SA_IO_MANIFEST_INVALID",
            "SA_IO_MANIFEST_CORRUPT",
            "SA_IO_SESSION_ESCAPE",
            "SA_IO_ATOMIC_WRITE_FAILED",
            "SA_IO_MALFORMED_HANDOFF_STATE",
        }
    ),
    ErrorCategory.EXT: frozenset(
        {
            "SA_EXT_AUTH_EXPIRED",
            "SA_EXT_RATE_LIMITED",
            "SA_EXT_TIMEOUT",
            "SA_EXT_SERVICE_UNAVAILABLE",
            "SA_EXT_UNEXPECTED_RESPONSE",
        }
    ),
    ErrorCategory.TOOL: frozenset(
        {
            "SA_TOOL_INVALID_INPUT",
            "SA_TOOL_EXECUTION_FAILED",
            "SA_TOOL_DEPENDENCY_MISSING",
            "SA_TOOL_NOT_FOUND",
        }
    ),
}


def is_canonical(code: str) -> bool:
    """Check whether a code is one of the framework's canonical codes.

    Extensions are welcome to define their own codes; this is a hint, not a
    requirement. Used by `doctor` to warn about extensions that invent codes
    without documentation.
    """
    for codes in CANONICAL_CODES.values():
        if code in codes:
            return True
    return False


def wrap_unexpected(exc: BaseException) -> SystemError:
    """Wrap a non-SovereignError exception as a SystemError with SA_SYS_UNEXPECTED.

    Used by the orchestrator and ticket harness to ensure every failure that
    escapes an operation has a structured code, even if it came from a
    third-party library that raises plain Python exceptions.
    """
    if isinstance(exc, SovereignError):
        # Already structured; don't double-wrap.
        return exc  # type: ignore[return-value]
    return SystemError(
        code="SA_SYS_UNEXPECTED",
        message=f"unexpected {type(exc).__name__}: {exc}",
        context={"exc_type": type(exc).__name__},
        cause=exc,
    )


__all__ = [
    "ErrorCategory",
    "SovereignError",
    "SystemError",
    "ValidationError",
    "IOError",
    "ExternalError",
    "ToolError",
    "CANONICAL_CODES",
    "is_canonical",
    "wrap_unexpected",
]
