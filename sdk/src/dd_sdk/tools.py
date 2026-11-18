"""Tools: a persona reads a source through the harness's tool gateway (docs/specs/agents.md).

A persona never connects to an MCP server itself. Its card declares the servers and tools it
uses (`ToolUse`), the deployment's profile grants servers per agent, and the conductor sends a
`ToolsGrant` with each invocation it may use them in. `dd_sdk.serve` binds the grant to the
agent's `ctx.tools` (`dd_sdk.tools_client.HarnessTools`), which calls the gateway's one MCP
endpoint with the grant's token.

The gateway records each record a tool returns, as the conductor's observation, and tells the
agent how it recorded it: the source id (`tool:<server>/<record id>`), the canonicalisation the
deployment names for the server and the content hash. A `ToolRecord` carries that, and the
grounding reference and evidence item that cite it, so a payload cannot mis-cite what the
gateway returned (docs/specs/grounding.md, invariant 15). Only a structured result grounds
anything: text a tool returns is passed on as `ToolOutcome.text` and cites nothing.

This module holds what the card, the wire and an agent share, and imports no MCP library; the
client is `dd_sdk.tools_client`, behind the SDK's `tools` extra.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, Self

from dd_sdk.contract.models import TOOL_SOURCE_PREFIX, EvidenceItem, GroundingRef
from dd_sdk.evidence import HASH_ALGORITHM, project, verify

# The A2A message metadata that carries a tools grant to the agent: the gateway's MCP endpoint and
# the token a call to it must present. Sent only to an agent the profile grants a server.
META_TOOLS_URL = "dd.tools_url"
META_TOOLS_TOKEN = "dd.tools_token"
# The key, in a tool result's `_meta`, of the records the gateway recorded from it, in the order
# of the structured result's records.
RECORDS_META = "dd.tool_retrievals"
# A tool's name at the gateway: `<server>.<tool>`.
SEPARATOR = "."

_SERVER = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_TOOL = re.compile(r"^[A-Za-z0-9_-]+$")


def gateway_name(server: str, tool: str) -> str:
    """The name the gateway lists a server's tool by."""
    return f"{server}{SEPARATOR}{tool}"


def split_name(name: str) -> tuple[str, str]:
    """The server and tool a gateway tool name names; a `ValueError` if it names neither."""
    server, sep, tool = name.partition(SEPARATOR)
    if not sep or not _SERVER.match(server) or not _TOOL.match(tool):
        raise ValueError(f"tool {name!r}: expected <server>{SEPARATOR}<tool>")
    return server, tool


@dataclass(frozen=True)
class ToolUse:
    """The tools of one MCP server an agent may call, as its card declares them."""

    server: str
    tools: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _SERVER.match(self.server):
            raise ValueError(
                f"tool server {self.server!r}: expected lower-case letters, digits and hyphens"
            )
        if not self.tools:
            raise ValueError(f"tool server {self.server!r}: names no tool")
        for tool in self.tools:
            if not _TOOL.match(tool):
                raise ValueError(
                    f"tool {tool!r} on {self.server!r}: expected letters, digits, _ or -"
                )
        if len(set(self.tools)) != len(self.tools):
            raise ValueError(f"tool server {self.server!r}: names a tool twice")

    def describe(self) -> dict[str, Any]:
        return {"server": self.server, "tools": list(self.tools)}


def tools_from_description(agent_id: str, entry: Mapping[str, Any]) -> tuple[ToolUse, ...]:
    """The tools a card declares. They may be absent: a card written before the tool gateway
    declares none. A malformed entry, or a server declared twice, is a `ValueError` naming the
    agent."""
    declared: Sequence[Any] = entry.get("tools") or ()
    try:
        uses = tuple(
            ToolUse(str(t["server"]), tuple(str(name) for name in t["tools"])) for t in declared
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"agent {agent_id!r}: malformed tools: {exc}") from exc
    servers = [u.server for u in uses]
    if len(set(servers)) != len(servers):
        raise ValueError(f"agent {agent_id!r} declares a tool server twice: {sorted(servers)}")
    return uses


@dataclass(frozen=True)
class ToolsGrant:
    """Where, and with what token, an agent may call the tool gateway in one invocation."""

    url: str
    token: str

    def metadata(self) -> dict[str, str]:
        """The A2A message metadata that carries this grant to the agent."""
        return {META_TOOLS_URL: self.url, META_TOOLS_TOKEN: self.token}

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> Self | None:
        """The grant a request's metadata carries, or None unless it has both a URL and a token."""
        url, token = metadata.get(META_TOOLS_URL), metadata.get(META_TOOLS_TOKEN)
        return cls(url=str(url), token=str(token)) if url and token else None


class ToolGatewayError(Exception):
    """The gateway would not run the call (a tool not declared, not granted or not available, or
    an expired grant), or could not be reached. A tool that ran and reported an error is a
    `ToolOutcome` with `is_error`."""


@dataclass(frozen=True)
class ToolRecord:
    """One record a tool returned, as the gateway recorded it.

    `content` is the record projected under `canonicalisation`, which is what `content_hash`
    covers and what an evidence item carries so that a reader can re-hash it (E1).
    """

    source_id: str
    canonicalisation: str
    content_hash: str
    content: dict[str, Any]
    retrieved_at: datetime | None = None

    def ref(self) -> GroundingRef:
        """The grounding reference a payload cites this record by."""
        return GroundingRef(source_id=self.source_id, content_hash=self.content_hash)

    def evidence(self) -> EvidenceItem:
        """The evidence item `ref()` points at."""
        return EvidenceItem(
            source_id=self.source_id,
            retrieved_at=self.retrieved_at,
            hash_algorithm=HASH_ALGORITHM,
            canonicalisation=self.canonicalisation,
            content_hash=self.content_hash,
            content=self.content,
        )


@dataclass(frozen=True)
class ToolOutcome:
    """What one tool call returned: the records the gateway recorded from its structured result,
    and any text, which grounds nothing."""

    records: tuple[ToolRecord, ...] = ()
    text: str = ""
    is_error: bool = False
    structured: Mapping[str, Any] | None = field(default=None, repr=False)


def records_from_result(
    structured: Mapping[str, Any] | None, meta: Mapping[str, Any] | None
) -> tuple[ToolRecord, ...]:
    """The records a tool result's structured content holds, each with what the gateway recorded
    of it (`RECORDS_META`). A record whose recorded hash does not match its content under the
    recorded canonicalisation is a `ToolGatewayError`: the gateway and the result disagree, and
    nothing is citable."""
    recorded = (meta or {}).get(RECORDS_META) or []
    if structured is None or not recorded:
        return ()
    items = structured.get("records") if "records" in structured else [structured]
    if not isinstance(items, list) or len(items) != len(recorded):
        raise ToolGatewayError("the gateway's records do not match the tool's structured result")
    records: list[ToolRecord] = []
    for item, entry in zip(items, recorded, strict=True):
        source_id, canon, digest = (
            str(entry.get("source_id")),
            str(entry.get("canonicalisation")),
            str(entry.get("content_hash")),
        )
        if not source_id.startswith(TOOL_SOURCE_PREFIX) or not isinstance(item, dict):
            raise ToolGatewayError(
                f"the gateway recorded {source_id!r}, which is not a tool record"
            )
        try:
            content = project(item, canon)
            matches = verify(content, canon, digest)
        except ValueError as exc:
            raise ToolGatewayError(f"record {source_id!r}: {exc}") from exc
        if not matches:
            raise ToolGatewayError(
                f"record {source_id!r} does not match the hash the gateway recorded"
            )
        when = entry.get("retrieved_at")
        records.append(
            ToolRecord(
                source_id=source_id,
                canonicalisation=canon,
                content_hash=digest,
                content=content,
                retrieved_at=datetime.fromisoformat(when) if isinstance(when, str) else None,
            )
        )
    return tuple(records)


class Tools(Protocol):
    """Call a tool through the harness's gateway (`dd_sdk.tools_client.HarnessTools`).

    `listed` is what the gateway says this invocation may call: each tool's gateway name
    (`<server>.<tool>`), description and input schema.
    """

    def call(self, server: str, tool: str, arguments: Mapping[str, Any]) -> ToolOutcome: ...

    def listed(self) -> list[dict[str, Any]]: ...
