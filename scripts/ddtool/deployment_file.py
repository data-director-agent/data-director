"""`deployment.yaml` read and checked: what an instance runs (ddtool.deployment applies it).

    name: datadir-dev        # names the generated profile
    orchestrator: model      # the agent the home page converses with: model or stub
    disabled: []             # agents in app/config/agents.yaml not to run
    privacy_notice: https://example.ac.uk/data-director/privacy   # optional
    model_accounts: {own: allowed, ...}   # optional: copied into the profile as it stands
    institution_repositories: [{repository_id: bl.durham, ...}]   # optional: copied likewise
    administrators: [https://orcid.org/0000-0002-1825-0097]       # optional: copied likewise
    stewardship: {teams: [...]}                                     # optional: copied likewise
    pid_resolver: true       # optional, development only: run the PID resolver (mcp-pid)
    campus_ranges: [172.18.0.0/16]   # optional: the ranges `doctor` keeps Docker's networks out of

Each problem is reported against the file as the operator knows it, naming the key and what it
takes.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ddtool.common import MODEL_BACKED, Agent, DevError, shown

ORCHESTRATORS = ("model", "stub")
KEYS = {
    "name",
    "orchestrator",
    "disabled",
    "privacy_notice",
    "model_accounts",
    "institution_repositories",
    "institution_storage",
    "administrators",
    "stewardship",
    "access",
    "pid_resolver",
    "campus_ranges",
}
# An absolute https URL with a host and no spaces. The app checks the same rule when it reads
# the setting (dd_app.privacy), as app.env can be edited by hand.
PRIVACY_NOTICE = re.compile(r"https://[^\s/@?#]+(?:[/?#]\S*)?")
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Deployment:
    name: str
    orchestrator: str
    disabled: frozenset[str] = frozenset()
    privacy_notice: str | None = None
    model_accounts: dict[str, Any] | None = None
    institution_repositories: list[dict[str, Any]] | None = None
    institution_storage: list[dict[str, Any]] | None = None
    # Deployment roles (docs/specs/stewardship.md, invariant 1), copied into the profile.
    administrators: list[str] | None = None
    stewardship: dict[str, Any] | None = None
    # Whom a deployment that signs people in admits, copied into the profile; None admits only
    # those listed, its stewards and its administrators (ddtool.deployment.profile).
    access: dict[str, Any] | None = None
    pid_resolver: bool = False
    # The address ranges the institution's networks use, which `doctor` checks Docker's networks
    # against; None means the private blocks Docker's default pools fall in.
    campus_ranges: list[str] | None = None

    @property
    def orchestrator_agent(self) -> str:
        """The orchestrator's name in agents.yaml (its id with `-` for `.`)."""
        return f"orchestrator-{self.orchestrator}"

    def runs(self, agents: list[Agent]) -> list[Agent]:
        """The agents this instance runs: every listed agent but those disabled, and a
        model-backed one only as the orchestrator."""
        return [
            agent
            for agent in agents
            if agent.name not in self.disabled
            and (agent.name not in MODEL_BACKED or agent.name == self.orchestrator_agent)
        ]


def load(path: Path, agents: list[Agent]) -> Deployment:
    """`path`'s deployment, checked against the agents the release lists."""
    return parse(path.read_text(encoding="utf-8"), shown(path), agents)


def parse(text: str, label: str, agents: list[Agent]) -> Deployment:
    """The deployment `text` says, checked against the agents the release lists. Each problem is
    reported against `label`, the file as the operator knows it."""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise DevError(f"{label} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise DevError(
            f"{label}: expected name, orchestrator, disabled, privacy_notice, model_accounts, "
            "institution_repositories, institution_storage, administrators, stewardship, access "
            "and pid_resolver"
        )
    if unknown := sorted(set(data) - KEYS):
        raise DevError(
            f"{label}: unknown key {', '.join(unknown)} (known: {', '.join(sorted(KEYS))})"
        )
    name = str(data.get("name") or "")
    if not NAME.match(name):
        raise DevError(f"{label}: name is lower-case words joined by hyphens, such as datadir-dev")
    orchestrator = str(data.get("orchestrator") or "stub")
    if orchestrator not in ORCHESTRATORS:
        raise DevError(
            f"{label}: orchestrator is {' or '.join(ORCHESTRATORS)}, not {orchestrator!r}"
        )
    disabled = data.get("disabled") or []
    if not isinstance(disabled, list):
        raise DevError(f"{label}: disabled is a list of agent names")
    known = {agent.name for agent in agents}
    if unknown_agents := sorted(set(map(str, disabled)) - known):
        raise DevError(f"{label}: disabled names {', '.join(unknown_agents)}, not in agents.yaml")
    found = Deployment(name, orchestrator, frozenset(map(str, disabled)), **_options(data, label))
    if found.orchestrator_agent not in known:
        raise DevError(f"{label}: agents.yaml lists no {found.orchestrator_agent}")
    if found.orchestrator_agent in found.disabled:
        raise DevError(f"{label}: the orchestrator, {found.orchestrator_agent}, is disabled")
    return found


def _options(data: dict[str, Any], label: str) -> dict[str, Any]:
    """The optional keys, checked: privacy_notice, model_accounts, institution_repositories,
    institution_storage, administrators, stewardship, access and pid_resolver. What the profile's
    keys hold is checked when the harness loads the profile."""
    privacy_notice = data.get("privacy_notice")
    if privacy_notice is not None and not (
        isinstance(privacy_notice, str) and PRIVACY_NOTICE.fullmatch(privacy_notice.strip())
    ):
        raise DevError(
            f"{label}: privacy_notice is the address of the institution's privacy notice, "
            "an https URL such as https://example.ac.uk/data-director/privacy"
        )
    model_accounts = data.get("model_accounts")
    if model_accounts is not None and not isinstance(model_accounts, dict):
        raise DevError(f"{label}: model_accounts is a mapping, as in the profile")
    repositories = _entries(data, "institution_repositories", "repository_id", label)
    storage = _entries(data, "institution_storage", "storage_id", label)
    administrators = data.get("administrators")
    if administrators is not None and not (
        isinstance(administrators, list) and all(isinstance(a, str) for a in administrators)
    ):
        raise DevError(
            f"{label}: administrators lists people by principal identifier, such as "
            "https://orcid.org/0000-0002-1825-0097, as in the profile"
        )
    stewardship = data.get("stewardship")
    if stewardship is not None and not isinstance(stewardship, dict):
        raise DevError(f"{label}: stewardship is a mapping with teams, as in the profile")
    access = data.get("access")
    if access is not None and not isinstance(access, dict):
        raise DevError(
            f"{label}: access is a mapping with admit, allow and block, as in the profile"
        )
    pid_resolver = data.get("pid_resolver", False)
    if not isinstance(pid_resolver, bool):
        raise DevError(f"{label}: pid_resolver is true or false")
    return {
        "campus_ranges": campus_ranges(data, label),
        "privacy_notice": privacy_notice.strip() if privacy_notice else None,
        "model_accounts": model_accounts,
        "institution_repositories": repositories,
        "institution_storage": storage,
        "administrators": administrators,
        "stewardship": stewardship,
        "access": access,
        "pid_resolver": pid_resolver,
    }


def campus_ranges(data: dict[str, Any], label: str) -> list[str] | None:
    """`campus_ranges`, a list of IPv4 networks in CIDR form, or None if the key is absent."""
    value = data.get("campus_ranges")
    if value is None:
        return None
    try:
        if not isinstance(value, list):
            raise ValueError(value)
        return [str(ipaddress.IPv4Network(str(item), strict=False)) for item in value]
    except ValueError as exc:
        raise DevError(
            f"{label}: campus_ranges is a list of IPv4 networks in CIDR form, such as 172.18.0.0/16"
        ) from exc


def _entries(
    data: dict[str, Any], key: str, id_key: str, label: str
) -> list[dict[str, Any]] | None:
    """A key that lists entries, each a mapping, as the profile's key of that name does."""
    value = data.get(key)
    if value is not None and not (
        isinstance(value, list) and all(isinstance(e, dict) for e in value)
    ):
        raise DevError(
            f"{label}: {key} lists entries, each a mapping with a {id_key}, as in the profile"
        )
    return value
