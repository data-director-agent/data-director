"""Which classes of project content may go where: the profile keys that list them, and the MCP
servers the profile grants (docs/specs/projects.md, invariant 8; docs/specs/policy-and-identity.md).
Read by `dd_harness.policy`, which applies them (`withheld`)."""

from __future__ import annotations

from typing import Any

# The classes of project content (docs/specs/projects.md, invariant 8): the inventory of the data
# files, documentation (a document's text, or what a person wrote about one), the facts
# researchers kept from their public ORCID records, and the facts people decided about the project
# (its funders, required repositories, which files go in, sensitivity and licence), which hold
# structured values only, never a person's words.
CONTENT_CLASSES = ("inventory", "documentation", "researcher", "decisions")
# What may be given to an agent whose card declares a hosted model, where the profile does not say.
DEFAULT_HOSTED_MODELS = frozenset({"inventory", "decisions"})
# What may be given to an agent granted a `remote` MCP server, where the profile does not say:
# everything but the facts researchers kept from their ORCID records
# (docs/specs/policy-and-identity.md).
DEFAULT_REMOTE_TOOL_CONTENT = frozenset({"inventory", "documentation", "decisions"})


def classes(data: dict[str, Any], key: str, default: frozenset[str]) -> frozenset[str]:
    """A profile key that lists classes of project content (`hosted_models`,
    `remote_tool_content`), or `default` where the profile does not set it."""
    listed = data.get(key, sorted(default))
    if not isinstance(listed, list):
        raise TypeError(f"{key} must list classes of project content")
    if wrong := sorted({str(c) for c in listed} - set(CONTENT_CLASSES)):
        raise ValueError(
            f"{key} names {', '.join(map(repr, wrong))}; "
            f"the classes of project content are {', '.join(CONTENT_CLASSES)}"
        )
    return frozenset(str(c) for c in listed)


def tool_servers(value: Any, agents: dict[Any, Any]) -> dict[str, tuple[str, ...]]:
    """The profile's `tool_servers`: each enabled agent's MCP servers (docs/specs/agents.md,
    Tools). Whether the deployment lists them is checked when the conductor is built
    (`dd_harness.settings`)."""
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(v, list) for v in value.values()):
        raise TypeError("tool_servers must map each agent_id to a list of MCP server names")
    if stray := sorted(str(a) for a in value if a not in agents):
        raise ValueError(
            f"tool_servers names {', '.join(stray)}, which the profile does not enable"
        )
    return {str(a): tuple(str(s) for s in servers) for a, servers in value.items()}
