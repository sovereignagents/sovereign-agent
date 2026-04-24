"""Discovery protocol (Pattern A).

Every extension in sovereign-agent — tool, planner, executor, memory backend,
half, observability adapter — implements `discover()` and returns a JSON
schema describing its interface. Agents can learn about extensions at
runtime without being retrained or prompted in advance.

See docs/architecture.md §1.5 Pattern A and §2.5.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from sovereign_agent.errors import ValidationError


class DiscoverySchema(TypedDict, total=False):
    """The schema every extension returns from its discover() method.

    Required fields: name, kind, description, parameters, returns,
    error_codes, examples, version.

    Optional fields: metadata (arbitrary extension-specific).

    `parameters` and `returns` are JSON Schema objects (dicts). We do not
    validate them as full JSON Schema here — that would pull in jsonschema
    as a dependency. We only check shape. A full validator is a future lesson.
    """

    name: str
    kind: Literal["tool", "planner", "executor", "memory", "half", "observability"]
    description: str
    parameters: dict
    returns: dict
    error_codes: list[str]
    examples: list[dict]
    version: str
    metadata: dict


@runtime_checkable
class Discoverable(Protocol):
    """Protocol for anything that can describe its own interface to an agent."""

    name: str

    def discover(self) -> DiscoverySchema: ...


_VALID_KINDS: frozenset[str] = frozenset(
    {"tool", "planner", "executor", "memory", "half", "observability"}
)
_REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "kind",
    "description",
    "parameters",
    "returns",
    "error_codes",
    "examples",
    "version",
)


def validate_schema(schema: Any) -> DiscoverySchema:
    """Validate a discovery schema. Raises ValidationError on any problem.

    Catches common mistakes: missing required fields, wrong types, empty
    examples list (the spec mandates at least one example).

    Returns the schema (narrowed to DiscoverySchema) on success. The return
    is convenient for callers that want `validated = validate_schema(raw)`.
    """
    if not isinstance(schema, dict):
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message=f"discovery schema must be a dict, got {type(schema).__name__}",
        )

    # Check required fields are present.
    for field in _REQUIRED_FIELDS:
        if field not in schema:
            raise ValidationError(
                code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
                message=f"discovery schema missing required field {field!r}",
                context={"schema": schema},
            )

    # name: non-empty str
    if not isinstance(schema["name"], str) or not schema["name"]:
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message="discovery schema: 'name' must be a non-empty string",
        )

    # kind: one of the allowed values
    if schema["kind"] not in _VALID_KINDS:
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message=(
                f"discovery schema: 'kind' must be one of "
                f"{sorted(_VALID_KINDS)}, got {schema['kind']!r}"
            ),
        )

    # description: non-empty str
    if not isinstance(schema["description"], str) or not schema["description"]:
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message="discovery schema: 'description' must be a non-empty string",
        )

    # parameters & returns: dicts (shallow check, not full JSON Schema)
    if not isinstance(schema["parameters"], dict):
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message="discovery schema: 'parameters' must be a dict (JSON Schema object)",
        )
    if not isinstance(schema["returns"], dict):
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message="discovery schema: 'returns' must be a dict (JSON Schema object)",
        )

    # error_codes: list of str
    if not isinstance(schema["error_codes"], list) or not all(
        isinstance(c, str) for c in schema["error_codes"]
    ):
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message="discovery schema: 'error_codes' must be a list of strings",
        )

    # examples: mandatory, at least one entry, each a dict
    if (
        not isinstance(schema["examples"], list)
        or len(schema["examples"]) == 0
        or not all(isinstance(ex, dict) for ex in schema["examples"])
    ):
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message=(
                "discovery schema: 'examples' must be a non-empty list of dicts. "
                "Every extension must document at least one example invocation."
            ),
        )

    # version: non-empty str
    if not isinstance(schema["version"], str) or not schema["version"]:
        raise ValidationError(
            code="SA_VAL_INVALID_DISCOVERY_SCHEMA",
            message="discovery schema: 'version' must be a non-empty string",
        )

    return schema  # type: ignore[return-value]


def discover_all(extensions: list[Discoverable]) -> list[DiscoverySchema]:
    """Call discover() on every extension and return the validated schemas.

    Used by the orchestrator at startup and by agents that want the full
    capability list.
    """
    out: list[DiscoverySchema] = []
    for ext in extensions:
        schema = ext.discover()
        out.append(validate_schema(schema))
    return out


def discoverable(cls: type) -> type:
    """Class decorator that validates a class implements the Discoverable protocol.

    Raises at class-definition time if `discover` is missing or unreachable.
    It does not instantiate the class (that would require knowing the
    constructor signature) — the schema itself is validated lazily when
    the instance calls `discover()`.

    Intended for use as:

        @discoverable
        class MyTool:
            name = "my_tool"
            def discover(self) -> DiscoverySchema: ...
    """
    if not hasattr(cls, "discover"):
        raise TypeError(
            f"{cls.__name__} is marked @discoverable but does not define discover(). "
            "Every extension must implement discover() returning a DiscoverySchema."
        )
    if not callable(getattr(cls, "discover", None)):
        raise TypeError(f"{cls.__name__}.discover must be a callable method")
    return cls


__all__ = [
    "DiscoverySchema",
    "Discoverable",
    "validate_schema",
    "discover_all",
    "discoverable",
]
