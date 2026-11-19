"""Each agent the app is configured with, as its card describes it (docs/specs/agents.md).

The admin service reads the same `agents.yaml` the app does and asks each agent for its card, as
`dd_harness.registry.Registry` does, but keeps every entry by the name it is configured under, so
an agent that is down is still listed with its port and why."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dd_harness.registry import RegistryError, load_config
from dd_harness.remote import ClientFactory, RemoteAgent, RemoteAgentError, default_client
from dd_sdk.agent import ContractVersionError, SpecError, describe

# An agent that does not answer within this is shown as down; the page should not wait for it.
CARD_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class AgentState:
    name: str
    url: str
    state: str  # "up", "down" or "incompatible"
    reason: str | None = None
    card: dict[str, Any] | None = None
    described: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Agents:
    configured: bool = True
    error: str | None = None
    agents: list[AgentState] = field(default_factory=list)

    def get(self, name: str) -> AgentState | None:
        return next((a for a in self.agents if a.name == name), None)

    def names(self) -> list[str]:
        return [a.name for a in self.agents]


def configured_names(config: Path | None) -> list[str]:
    """The agents' names in `config`, without asking them anything; empty if it cannot be read."""
    if config is None:
        return []
    try:
        return [str(e.get("name") or e["url"]) for e in load_config(config)]
    except RegistryError:
        return []


def probe(config: Path | None, client_factory: ClientFactory = default_client) -> Agents:
    """Read `config` and each agent's card."""
    if config is None:
        return Agents(configured=False)
    try:
        entries = load_config(config)
    except RegistryError as exc:
        return Agents(error=str(exc))
    found: list[AgentState] = []
    for entry in entries:
        url = str(entry["url"])
        name = str(entry.get("name") or url)
        timeout_s = min(float(entry.get("timeout_s", CARD_TIMEOUT_S)), CARD_TIMEOUT_S)
        try:
            agent = RemoteAgent.from_url(url, timeout_s=timeout_s, client_factory=client_factory)
        except ContractVersionError as exc:
            found.append(AgentState(name, url, "incompatible", str(exc)))
            continue
        except (RemoteAgentError, SpecError) as exc:
            found.append(AgentState(name, url, "down", str(exc)))
            continue
        found.append(AgentState(name, url, "up", card=agent.card, described=describe(agent.spec)))
    return Agents(agents=found)
