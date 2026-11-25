"""The tools that delegate to another agent (`agent.py`): one per input class each agent the
harness's manifest lists accepts, except delegation agents, itself included, since delegation is
one level deep (docs/specs/orchestration.md)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dd_sdk.contract.models import GroundingMode
from dd_sdk.model import ToolSpec

AGENT_ID = "orchestrator.model"
# The API's rule for a tool name.
TOOL_NAME_UNSAFE = re.compile(r"[^a-zA-Z0-9_-]")
TOOL_NAME_MAX = 64
# Keys of a generated class schema that describe the file, not the input.
SCHEMA_ANNOTATIONS = ("$comment", "$id", "$schema", "title")


@dataclass(frozen=True)
class Tool:
    """One tool offered to the model: delegate an input of `schema_class` to `agent_id`."""

    name: str
    agent_id: str
    schema_class: str
    definition: ToolSpec


def delegable(entry: dict[str, Any], own_id: str = AGENT_ID) -> bool:
    """Whether a tool may delegate to the agent of a manifest entry: not to a delegation agent."""
    return (
        str(entry.get("agent_id")) != own_id
        and entry.get("grounding_mode") != GroundingMode.DELEGATION.value
    )


def with_schemas(
    manifest: list[dict[str, Any]],
    schemas_of: Callable[[list[str]], dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """The manifest with each delegable agent's class schemas under `schemas`. The harness's card
    names them only by digest; `schemas_of` is the delegate's, which fetches those it does not
    already hold (docs/specs/orchestration.md)."""
    ids = [str(e.get("agent_id")) for e in manifest if delegable(e)]
    schemas = schemas_of(ids) if ids else {}
    return [
        {**e, "schemas": schemas[str(e.get("agent_id"))]} if delegable(e) else e for e in manifest
    ]


def tools_from_manifest(manifest: list[dict[str, Any]], own_id: str = AGENT_ID) -> list[Tool]:
    """One tool per input class of each agent the harness lists, except delegation agents."""
    tools: list[Tool] = []
    for entry in sorted(manifest, key=lambda e: str(e.get("agent_id"))):
        agent_id = str(entry.get("agent_id"))
        if not delegable(entry, own_id):
            continue
        accepts = [str(name) for name in entry.get("accepts") or []]
        schemas = entry.get("schemas") or {}
        for schema_class in accepts:
            schema = (schemas.get(schema_class) or {}).get("json_schema")
            if not isinstance(schema, dict):
                continue
            base = TOOL_NAME_UNSAFE.sub("_", agent_id)
            name = base if len(accepts) == 1 else f"{base}__{schema_class}"
            description = str(entry.get("description") or agent_id)
            title = str(entry.get("title") or "")
            if title:
                # The persona's name, so the reply can name who was asked (docs/specs/agents.md).
                description = f"The {title}. {description}"
            steps = [str(s) for s in entry.get("serves") or []]
            if steps:
                description += f" Serves step(s) {', '.join(steps)}."
            tools.append(
                Tool(
                    name=name[:TOOL_NAME_MAX],
                    agent_id=agent_id,
                    schema_class=schema_class,
                    definition=ToolSpec(
                        name=name[:TOOL_NAME_MAX],
                        description=(
                            f"Ask the agent {agent_id} (input class {schema_class}). {description}"
                        ),
                        input_schema=tool_schema(schema),
                    ),
                )
            )
    return tools


def tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A class schema as a tool's input schema: without `schema_class`, which the orchestrator
    fills in, and with the integers the A2A card carried as floats made integers again."""
    out = {k: _integral(v) for k, v in schema.items() if k not in SCHEMA_ANNOTATIONS}
    properties = dict(out.get("properties") or {})
    properties.pop("schema_class", None)
    out["properties"] = properties
    out["required"] = [r for r in out.get("required") or [] if r != "schema_class"]
    return out


def _integral(value: Any) -> Any:
    # protobuf's Struct has only floating-point numbers (docs/specs/app.md).
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _integral(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_integral(v) for v in value]
    return value
