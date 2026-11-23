"""The harness card's manifest: one entry per agent it may invoke, without the agent's schemas
(docs/specs/orchestration.md).

An entry is the agent's `describe(spec)` with `schemas` replaced by `schemas_digest`, the digest of
the document the harness serves at `SCHEMAS_PATH` for that agent (`dd_sdk.wire`). The card so
stays the same size however large the agents' schemas grow, and a delegation agent fetches an
agent's schemas only when the digest it holds no longer matches (#1590).
"""

from __future__ import annotations

from typing import Any

from dd_sdk.agent import AgentSpec, describe
from dd_sdk.contract.classes import schemas_digest as schemas_digest
from dd_sdk.wire import SCHEMAS_DIGEST_KEY

SCHEMAS_KEY = "schemas"


def schemas_document(spec: AgentSpec) -> dict[str, Any]:
    """The agent's class schemas, keyed by class name: what `describe` puts under `schemas`."""
    return {c.name: c.describe() for c in spec.schemas()}


def manifest_entry(spec: AgentSpec) -> dict[str, Any]:
    """The agent's entry in the harness card's manifest: its description without its schemas,
    and the digest of the schemas the harness serves for it."""
    entry = describe(spec)
    entry[SCHEMAS_DIGEST_KEY] = schemas_digest(entry.pop(SCHEMAS_KEY))
    return entry
