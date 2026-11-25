"""`pid_resolver: true` in deployment.yaml: the PID resolver (mcp-pid/README.md) in development.

`apply` grants the Linking Adviser every server `app/config/tools.yaml` lists and names that file
in app.env as `DD_TOOLS_CONFIG`; both go again when the switch is off. `dd.py start` runs the
server before the app, since the app lists the gateway's servers once, when it starts. A VM
refuses the switch until the server has a unit there and the harness its gateway extra
(TODO(#953)).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from ddtool import paths

TOOLS_CONFIG_VARIABLE = "DD_TOOLS_CONFIG"
AGENT = "advisor-linking"  # the agent the servers are granted to
AGENT_ID = "advisor.linking"
PORT = 8310  # where app/config/tools.yaml lists the servers
VM_REFUSAL = (
    "pid_resolver is for development only for now: a VM has no unit for the PID resolver yet "
    "(TODO(#953)); remove it from deployment.yaml"
)


def tools_config(source: Path) -> Path:
    return source / "app" / "config" / "tools.yaml"


def tool_servers(config: Path) -> list[str]:
    """The names of the MCP servers a tool configuration lists, in its order."""
    data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    return [str(server["name"]) for server in data.get("servers") or []]


@dataclass(frozen=True)
class Settings:
    """What the switch makes of one instance: the profile's grant and app.env's setting."""

    tool_servers: dict[str, list[str]] | None
    tools_config: str | None
    refusal: str | None = None


def settings(*, on: bool, disabled: frozenset[str], source: Path, on_vm: bool) -> Settings:
    if not on:
        return Settings(None, None)
    if on_vm:
        return Settings(None, None, VM_REFUSAL)
    config = tools_config(source)
    if not config.is_file() or AGENT in disabled:
        return Settings(None, None)
    return Settings({AGENT_ID: tool_servers(config)}, str(config))


def server_env() -> dict[str, str]:
    """The server's settings: the ROR registry the policy advisor builds (`dd-sources prepare`),
    which dump it was built from, the journal registry's index (built the same way), and where
    the server keeps its cache of the registries' answers (under config/local/, never committed)."""
    ror = paths.ROOT / "agents" / "advisor-policy" / "data" / "ror"
    try:
        version = json.loads((ror / "manifest.json").read_text(encoding="utf-8"))["version"]
    except OSError, ValueError, KeyError:
        version = None
    return {
        "DD_PID_ROR_REGISTRY": str(ror / "registry.jsonl"),
        "DD_PID_ROR_SNAPSHOT": f"ROR dump {version}" if version else "ROR dump",
        "DD_PID_JOURNALS_REGISTRY": str(
            paths.ROOT / "journals" / "src" / "dd_journals" / "data" / "journals.sqlite"
        ),
        "DD_PID_CACHE_DIR": str(paths.LOCAL_DIR / "cache" / "mcp-pid"),
    }
