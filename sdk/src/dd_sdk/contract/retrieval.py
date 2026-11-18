"""What a run's grounding rests on beyond its input (docs/specs/grounding.md): the evidence items an
agent returns, and the records the conductor kept from the harness's tool gateway
(docs/specs/agents.md, Tools). Re-exported by `dd_sdk.contract.models`, the mirror of the core
schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from dd_sdk.contract.base import Frozen

_SHA256 = r"^[0-9a-f]{64}$"
# A source read through the harness's tool gateway: tool:<server>/<record id>.
TOOL_SOURCE_PREFIX = "tool:"


def tool_source_id(server: str, record_id: str) -> str:
    """The source id of a record a tool returned through the gateway (docs/specs/grounding.md)."""
    return f"{TOOL_SOURCE_PREFIX}{server}/{record_id}"


class EvidenceItem(Frozen):
    source_id: str
    source_uri: str | None = None
    retrieved_at: datetime | None = None
    snapshot_ref: str | None = None
    hash_algorithm: str = "sha256"
    canonicalisation: str
    content_hash: str = Field(pattern=_SHA256)
    # What the hash covers, already projected; the linter re-hashes it (E1,
    # docs/specs/grounding.md).
    content: dict[str, Any] | None = None


class ToolRetrieval(Frozen):
    """One record a tool returned through the gateway, as the conductor recorded it, never the
    agent (docs/specs/grounding.md, invariant 15)."""

    tool_server: str
    tool_name: str
    source_id: str = Field(pattern=r"^tool:[^/]+/.+$")
    canonicalisation: str
    content_hash: str = Field(pattern=_SHA256)
    retrieved_at: datetime
