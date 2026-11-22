"""The deployment's list of MCP servers (`DD_TOOLS_CONFIG`, docs/specs/agents.md, Tools).

The list names each server the tool gateway may call, as `agents.yaml` names each agent, and the
source it serves (docs/specs/grounding.md):

```yaml
servers:
  - name: spdx                      # what cards and the profile call it
    url: http://127.0.0.1:8312/spdx/mcp     # its streamable HTTP endpoint
    id_field: licenseId             # the field that identifies a record
    canonicalisation: dd-spdx-licence-v1    # registered in dd_sdk.evidence
    snapshot_ref: spdx:3.29.0       # optional: the pinned copy it serves (mcp-spdx)
    tools_sha256: "6f1e…"           # the pin of its tools/list (dd-mcp-tools-v1), quoted
```

Whether a server is `local` or `remote` is worked out from its address by the rule that
classifies a model's endpoint (`dd_sdk.model_provider.hosting_of`), never stated: a mistake can
only call a local server remote, which withholds more (docs/specs/policy-and-identity.md).

A server's tool definitions are pinned by digest, so a changed description cannot reach a prompt
unreviewed. `tools_digest` is that digest: the SHA-256 of the sorted JSON of each tool's name,
description, input schema and output schema, which `dd-harness tools pins` prints for review.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from dd_sdk.evidence import CANONICALISATIONS
from dd_sdk.model_provider import hosting_of

# The name of the digest a server's tools/list is pinned under.
TOOLS_DIGEST = "dd-mcp-tools-v1"
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

type Locality = Literal["local", "remote"]


class ToolConfigError(Exception):
    """The list of MCP servers is missing, malformed or names something unregistered."""


@dataclass(frozen=True)
class ToolServer:
    """One MCP server the deployment lists, and the source it serves."""

    name: str
    url: str
    id_field: str
    canonicalisation: str
    tools_sha256: str
    snapshot_ref: str | None = None

    @property
    def locality(self) -> Locality:
        return "local" if hosting_of(self.url) == "local" else "remote"


def tools_digest(tools: Iterable[Mapping[str, Any]]) -> str:
    """The `dd-mcp-tools-v1` digest of a server's tools, each given as its tools/list entry."""
    kept = sorted(
        (
            {
                "name": t.get("name"),
                "description": t.get("description") or "",
                "inputSchema": t.get("inputSchema") or {},
                "outputSchema": t.get("outputSchema"),
            }
            for t in tools
        ),
        key=lambda t: str(t["name"]),
    )
    data = json.dumps(kept, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def load_servers(path: Path) -> tuple[ToolServer, ...]:
    """The servers `path` lists. A file that cannot be read, an entry without its keys, a name
    used twice or an unregistered canonicalisation is a `ToolConfigError`."""
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ToolConfigError(f"cannot read {path}: {exc}") from None
    entries = doc.get("servers") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise ToolConfigError(f"{path}: expected a top-level 'servers' list")
    servers = tuple(_server(path, entry) for entry in entries)
    names = [s.name for s in servers]
    if len(set(names)) != len(names):
        raise ToolConfigError(f"{path}: a server name is listed twice: {sorted(names)}")
    return servers


def _server(path: Path, entry: Any) -> ToolServer:
    try:
        server = ToolServer(
            name=str(entry["name"]),
            url=str(entry["url"]),
            id_field=str(entry["id_field"]),
            canonicalisation=str(entry["canonicalisation"]),
            tools_sha256=str(entry["tools_sha256"]),
            snapshot_ref=str(entry["snapshot_ref"]) if entry.get("snapshot_ref") else None,
        )
    except KeyError, TypeError, AttributeError:
        raise ToolConfigError(
            f"{path}: each server needs name, url, id_field, canonicalisation and tools_sha256"
        ) from None
    if not _NAME.match(server.name):
        raise ToolConfigError(f"{path}: server name {server.name!r} is not lower-case words")
    if server.canonicalisation not in CANONICALISATIONS:
        raise ToolConfigError(
            f"{path}: server {server.name!r} names canonicalisation "
            f"{server.canonicalisation!r}, which dd_sdk.evidence does not register"
        )
    if not _SHA256.match(server.tools_sha256):
        raise ToolConfigError(
            f"{path}: server {server.name!r}: tools_sha256 is not 64 hex digits; quote it"
        )
    return server
