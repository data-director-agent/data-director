"""The institutional profile as its operators need to read it (docs/guide/operations/admin.md,
"Policy"): which agents it allows and at what action class, which actions wait for a person, what
may reach a hosted model, whose account pays, who administers and who stewards, and whom it admits.

The Configuration page shows `profile.yaml` as text. This page reads it with the harness's own
parser (`dd_harness.policy.Profile`), so it shows what the harness enforces and a profile the
harness would refuse is reported, not guessed at. It compares the profile's agents with the roster
in `agents.yaml` and what `deployment.yaml` turns off, and the profile on disk with the one the
running app reports. Nothing here writes: `deployment.yaml` is the operator's, and
`data-director apply` makes the profile from it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

import yaml

from dd_admin.agents import Agents
from dd_admin.broker import broker_id
from dd_admin.settings import AdminSettings
from dd_admin.system import System
from dd_harness.policy import PolicyError, Profile

PROFILE_FILE = "profile.yaml"
DEPLOYMENT_FILE = "deployment.yaml"


@dataclass(frozen=True)
class AgentRow:
    """One agent: what the profile says of it, and whether the roster and the deployment agree."""

    agent_id: str
    action_class: str | None  # None: the roster has it, the profile does not allow it
    in_roster: bool
    state: str | None  # `up`, `down` or `incompatible`, once the agents were asked
    needs_approval: bool = False
    tool_servers: tuple[str, ...] = ()
    settings: dict[str, str] = field(default_factory=dict)
    orchestrator: bool = False

    @property
    def problem(self) -> str | None:
        if self.action_class is None:
            return "in agents.yaml but not allowed by the profile, so the harness refuses its calls"
        if not self.in_roster:
            return "allowed by the profile but not in agents.yaml, so nothing answers for it"
        return None


@dataclass
class PolicyView:
    """`error` is set when there is no profile to show; `profile` otherwise."""

    configured: bool = False
    error: str | None = None
    profile: Profile | None = None
    agents: list[AgentRow] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    running: dict[str, Any] | None = None

    @property
    def stale(self) -> bool:
        """The running app holds another profile than the file on disk: `apply` has run, or the
        file was edited, without a restart."""
        if self.profile is None or not self.running:
            return False
        return (self.running.get("id"), self.running.get("version")) != (
            self.profile.profile_id,
            self.profile.version,
        )


def _mapping(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def parse(text: str, source: str) -> Profile:
    """The profile in `text`, as the harness parses a file; raises `PolicyError` if it refuses it.
    The digest is that of `text`, which equals the file's for the UTF-8 files `apply` writes."""
    data = _mapping(text)
    if data is None:
        raise PolicyError(f"profile {source!r} is not a mapping")
    return Profile.from_mapping(
        data, source=source, digest=hashlib.sha256(text.encode("utf-8")).hexdigest()
    )


def roster(profile: Profile, agents: Agents) -> list[AgentRow]:
    """Each agent the profile allows or the roster holds, by id, in id order."""
    in_roster: dict[str, str | None] = {}
    for found in agents.agents:
        agent_id = str(found.described.get("agent_id") or broker_id(found.name))
        in_roster[agent_id] = found.state
    rows = []
    for agent_id in sorted(set(profile.agents) | set(in_roster)):
        action_class = profile.agents.get(agent_id)
        rows.append(
            AgentRow(
                agent_id=agent_id,
                action_class=action_class,
                in_roster=agent_id in in_roster,
                state=in_roster.get(agent_id),
                needs_approval=action_class in profile.actions_requiring_approval,
                tool_servers=profile.tool_servers.get(agent_id, ()),
                settings=profile.agent_settings.get(agent_id, {}),
                orchestrator=profile.orchestrator == agent_id,
            )
        )
    return rows


def read(settings: AdminSettings, system: System, agents: Agents, about: object) -> PolicyView:
    """The profile in `etc`, the roster against it, and what the app says it is running."""
    if settings.etc is None:
        return PolicyView()
    view = PolicyView(configured=True)
    path = settings.etc / PROFILE_FILE
    text = system.read_text(path)
    if text is None:
        view.error = f"{path} cannot be read"
        return view
    try:
        view.profile = parse(text, str(path))
    except PolicyError as exc:
        view.error = f"the harness would refuse this profile: {exc}"
        return view
    view.agents = roster(view.profile, agents)
    deployment = _mapping(system.read_text(settings.etc / DEPLOYMENT_FILE)) or {}
    disabled = deployment.get("disabled")
    view.disabled = sorted(str(n) for n in disabled) if isinstance(disabled, list) else []
    running = about.get("profile") if isinstance(about, dict) else None
    view.running = running if isinstance(running, dict) else None
    return view
