"""Agent discovery (ADR-0010).

Agents are found through Python entry points in the group `workbench.agents`. Each entry point
names a factory `build(settings) -> Agent`. Adding an agent to the workbench is one package plus
one line in `pyproject.toml`; a package outside this repository registers the same way. The
conductor, CLI, transports and shell read the registry and never name an agent.

A factory that raises `NotImplementedError` marks an agent that is registered but not yet
usable (R3 while it awaits porting); the registry records the reason and carries on. Any other
exception from a factory is a configuration error and propagates.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any

from workbench.agents.base import Agent, describe

if TYPE_CHECKING:
    from workbench.settings import Settings

ENTRY_POINT_GROUP = "workbench.agents"


class RegistryError(Exception):
    pass


@dataclass
class Registry:
    agents: dict[str, Agent] = field(default_factory=dict)
    unavailable: dict[str, str] = field(default_factory=dict)  # entry point name -> reason

    @classmethod
    def from_agents(cls, agents: Iterable[Agent]) -> Registry:
        registry = cls()
        for agent in agents:
            registry.add(agent)
        return registry

    @classmethod
    def from_entry_points(cls, settings: Settings) -> Registry:
        registry = cls()
        for ep in sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda e: e.name):
            factory = ep.load()
            try:
                agent = factory(settings)
            except NotImplementedError as exc:
                registry.unavailable[ep.name] = str(exc) or "not implemented"
                continue
            registry.add(agent)
        return registry

    def add(self, agent: Agent) -> None:
        if not isinstance(agent, Agent):
            raise RegistryError(f"{agent!r} does not implement the Agent protocol")
        agent_id = agent.spec.agent_id
        if agent_id in self.agents:
            raise RegistryError(f"two agents registered as {agent_id!r}")
        self.agents[agent_id] = agent

    def get(self, agent_id: str) -> Agent | None:
        return self.agents.get(agent_id)

    def __iter__(self) -> Iterator[Agent]:
        return iter(self.agents.values())

    def __len__(self) -> int:
        return len(self.agents)

    def ids(self) -> list[str]:
        return sorted(self.agents)

    def manifest(self) -> list[dict[str, Any]]:
        return [describe(self.agents[agent_id].spec) for agent_id in self.ids()]
