"""Agent registry (ADR-0011, superseding the entry-point discovery of ADR-0010).

Agents run as their own services. The workbench learns about them from a configuration file,
`agents.yaml`, that lists each agent's base URL; it reads each agent card and rebuilds the
`AgentSpec` from the card's Data Director extension (`workbench.remote`). The conductor, CLI,
transports and viewer read the registry and never name an agent.

An agent whose card cannot be read, or whose card does not describe an agent this contract
admits, is recorded as unavailable with the reason, and the registry carries on: one agent being
down does not stop the workbench. An agent built against a contract version this workbench cannot
govern is recorded apart, as incompatible, with both versions (ADR-0019). The policy gate still
decides, per profile, which registered agents may run. Registration is not permission.

`from_agents` takes agent objects directly: `RemoteAgent`s, which tests bind to in-process ASGI
apps (`workbench.testing`), or in-process `Agent`s, which the conductor runs in its own trace.

Configuration shape:

    agents:
      - name: hello            # optional; labels the agent in `unavailable`
        url: http://127.0.0.1:8101
        timeout_s: 30          # optional; defaults to remote.DEFAULT_TIMEOUT_S
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dd_sdk.agent import Agent, ContractVersionError, SpecError, describe
from workbench.remote import (
    DEFAULT_TIMEOUT_S,
    ClientFactory,
    RemoteAgent,
    RemoteAgentError,
    default_client,
)


class RegistryError(Exception):
    pass


# A service the conductor reaches over A2A, or an agent object run in the conductor's process.
Registered = Agent | RemoteAgent


@dataclass
class Registry:
    agents: dict[str, Registered] = field(default_factory=dict)
    unavailable: dict[str, str] = field(default_factory=dict)  # name or URL -> reason
    incompatible: dict[str, str] = field(default_factory=dict)  # name or URL -> both versions

    @classmethod
    def from_agents(cls, agents: Iterable[Registered]) -> Registry:
        registry = cls()
        for agent in agents:
            registry.add(agent)
        return registry

    @classmethod
    def from_config(cls, path: Path, client_factory: ClientFactory = default_client) -> Registry:
        """Read `path` and each agent card it lists. A missing or malformed file is a
        `RegistryError`; an agent that cannot be reached is recorded as unavailable, and one
        built against another contract version as incompatible."""
        registry = cls()
        for entry in load_config(path):
            url = entry["url"]
            name = str(entry.get("name") or url)
            try:
                agent = RemoteAgent.from_url(
                    url,
                    timeout_s=float(entry.get("timeout_s", DEFAULT_TIMEOUT_S)),
                    client_factory=client_factory,
                )
            except ContractVersionError as exc:
                registry.incompatible[name] = str(exc)
                continue
            except (RemoteAgentError, SpecError) as exc:
                registry.unavailable[name] = str(exc)
                continue
            registry.add(agent)
        return registry

    def add(self, agent: Registered) -> None:
        if not isinstance(agent, (RemoteAgent, Agent)):
            raise RegistryError(f"{agent!r} does not implement the Agent protocol")
        agent_id = agent.spec.agent_id
        if agent_id in self.agents:
            raise RegistryError(f"two agents registered as {agent_id!r}")
        self.agents[agent_id] = agent

    def get(self, agent_id: str) -> Registered | None:
        return self.agents.get(agent_id)

    def __iter__(self) -> Iterator[Registered]:
        return iter(self.agents.values())

    def __len__(self) -> int:
        return len(self.agents)

    def ids(self) -> list[str]:
        return sorted(self.agents)

    def manifest(self) -> list[dict[str, Any]]:
        return [describe(self.agents[agent_id].spec) for agent_id in self.ids()]

    def listing(self) -> dict[str, Any]:
        """The manifest and the agents that could not be registered (`GET /agents`, `--json`)."""
        return {
            "agents": self.manifest(),
            "unavailable": self.unavailable,
            "incompatible": self.incompatible,
        }

    def not_registered(self) -> str:
        """One line per agent that could not be registered, and why."""
        return "".join(
            f"\n  {name} {state}: {reason}"
            for state, found in (
                ("unavailable", self.unavailable),
                ("incompatible", self.incompatible),
            )
            for name, reason in found.items()
        )


def load_config(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RegistryError(f"agent configuration {path} not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise RegistryError(f"{path}: expected a top-level `agents:` list")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
            raise RegistryError(f"{path}: agents[{i}] needs a `url`")
    return entries
