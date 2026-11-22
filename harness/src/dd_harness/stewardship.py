"""Deployment roles: who is a data steward or an administrator (docs/specs/stewardship.md,
invariant 1).

A person's deployment role comes from the institutional profile and nowhere else. The profile's
`stewardship` key names the deployment's steward teams, and its `administrators` key the
administrators. Everyone who signs in is a researcher, who may hold projects of their own; a
person a team lists is also a steward of that team, and a person `administrators` lists is also an
administrator. Neither role makes anyone a member of a project (invariant 2), and being an
administrator gives no access to anyone's project.

People are named by principal identifier, as the authentication boundary records them: for ORCID
sign-in, the iD as a URL (`https://orcid.org/0000-0002-1825-0097`). A bare iD would never match a
principal, so it is refused at load with the form to write instead, rather than passing silently.

This module reads the two keys; `dd_harness.policy.Profile` holds what it reads.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Which projects a steward may open (docs/specs/stewardship.md, invariant 3). `escalated` is the
# default: only while the project has an escalation routed to the steward's team, or a pause the
# team holds. `scope` adds the projects whose owners chose the team as their support team.
VISIBILITIES = ("escalated", "scope")
TEAM_KEYS = frozenset({"id", "name", "members", "supports", "contact", "response_time"})
STEWARDSHIP_KEYS = frozenset({"visibility", "deposit_co_approval", "teams"})
# A team's identifier: lower-case words joined by hyphens, as it appears in a project's log.
TEAM_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# A bare ORCID iD, which names no principal on its own.
_BARE_ORCID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


class DeploymentRole(StrEnum):
    """A person's role in the deployment, separate from any role in a project."""

    RESEARCHER = "researcher"
    STEWARD = "steward"
    ADMINISTRATOR = "administrator"


@dataclass(frozen=True)
class StewardTeam:
    """A team of data stewards, as the profile names it."""

    team_id: str
    # What researchers are shown.
    name: str
    # The principal identifiers of the people in the team.
    members: frozenset[str]
    # The labels of the projects the team supports, shown to the owners who choose a team.
    supports: tuple[str, ...] = ()
    # An address or a page, shown as given when no steward can help.
    contact: str | None = None
    # What the researcher is told to expect, as written, such as "3 working days".
    response_time: str | None = None


@dataclass(frozen=True)
class Stewardship:
    """The profile's `stewardship` key. Empty (no teams) when the profile has none: a deployment
    without stewards still works (invariant 11)."""

    teams: tuple[StewardTeam, ...] = ()
    visibility: str = "escalated"
    # Whether a deposit also needs a steward's co-approval (invariant 7). TODO(#1306): enforced
    # by the deposit once it is built; until then a profile that turns it on is refused at load.
    deposit_co_approval: bool = False

    def team(self, team_id: str) -> StewardTeam | None:
        """The team `team_id` names, or None."""
        return next((t for t in self.teams if t.team_id == team_id), None)

    def teams_of(self, principal_id: str) -> tuple[StewardTeam, ...]:
        """The teams `principal_id` is a steward in, in the profile's order."""
        return tuple(t for t in self.teams if principal_id in t.members)


@dataclass(frozen=True)
class DeploymentRoles:
    """What the profile makes a person: their deployment roles, and their steward teams."""

    roles: frozenset[DeploymentRole]
    teams: tuple[StewardTeam, ...] = field(default=())

    @property
    def steward(self) -> bool:
        return DeploymentRole.STEWARD in self.roles

    @property
    def administrator(self) -> bool:
        return DeploymentRole.ADMINISTRATOR in self.roles


def deployment_roles(
    stewardship: Stewardship, administrators: frozenset[str], principal_id: str
) -> DeploymentRoles:
    """The deployment roles the profile gives `principal_id`. Everyone is a researcher."""
    teams = stewardship.teams_of(principal_id)
    roles = {DeploymentRole.RESEARCHER}
    if teams:
        roles.add(DeploymentRole.STEWARD)
    if principal_id in administrators:
        roles.add(DeploymentRole.ADMINISTRATOR)
    return DeploymentRoles(frozenset(roles), teams)


def principals(value: Any, key: str) -> frozenset[str]:
    """A list of principal identifiers, checked. Raises `TypeError` or `ValueError` with what is
    wrong, which the profile reports as malformed."""
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise TypeError(f"{key} lists principal identifiers")
    found = set()
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise TypeError(f"{key} lists principal identifiers, as strings; {entry!r} is not one")
        entry = entry.strip()
        if _BARE_ORCID.fullmatch(entry):
            raise ValueError(
                f"{key} lists {entry!r}, a bare ORCID iD, which names no principal; write it as "
                f"the iD's URL, such as https://orcid.org/{entry}"
            )
        found.add(entry)
    return frozenset(found)


def _optional_text(team: dict[str, Any], key: str, label: str) -> str | None:
    value = team.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{label}: {key} is text")
    return value.strip()


def _team(value: Any, index: int) -> StewardTeam:
    if not isinstance(value, dict):
        raise TypeError(f"stewardship.teams[{index}] is a mapping with an id, a name and members")
    label = f"stewardship.teams[{index}]"
    if unknown := sorted(set(value) - TEAM_KEYS):
        raise ValueError(
            f"{label} has keys nothing enforces: {', '.join(unknown)}; "
            f"a team has {', '.join(sorted(TEAM_KEYS))}"
        )
    team_id = value.get("id")
    if not isinstance(team_id, str) or not TEAM_ID.fullmatch(team_id):
        raise ValueError(
            f"{label}: id is lower-case words joined by hyphens, such as library-rdm, "
            f"not {team_id!r}"
        )
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} ({team_id}): name is what researchers are shown, as text")
    members = principals(value.get("members"), f"{label}.members")
    if not members:
        raise ValueError(f"{label} ({team_id}): members lists at least one steward")
    supports = value.get("supports") or []
    if not isinstance(supports, list) or not all(isinstance(s, str) and s for s in supports):
        raise TypeError(f"{label} ({team_id}): supports lists labels, as text")
    return StewardTeam(
        team_id=team_id,
        name=name.strip(),
        members=members,
        supports=tuple(supports),
        contact=_optional_text(value, "contact", label),
        response_time=_optional_text(value, "response_time", label),
    )


def parse(value: Any) -> Stewardship:
    """The profile's `stewardship` key, checked. None: no stewards."""
    if value is None:
        return Stewardship()
    if not isinstance(value, dict):
        raise TypeError("stewardship is a mapping with teams, visibility and deposit_co_approval")
    if unknown := sorted(set(value) - STEWARDSHIP_KEYS):
        raise ValueError(
            f"stewardship has keys nothing enforces: {', '.join(unknown)}; "
            f"it has {', '.join(sorted(STEWARDSHIP_KEYS))}"
        )
    visibility = value.get("visibility", "escalated")
    if visibility not in VISIBILITIES:
        raise ValueError(
            f"stewardship.visibility is {visibility!r}; it is one of {', '.join(VISIBILITIES)}"
        )
    co_approval = value.get("deposit_co_approval", False)
    if not isinstance(co_approval, bool):
        raise TypeError("stewardship.deposit_co_approval is true or false")
    if co_approval:
        raise ValueError(
            "stewardship.deposit_co_approval is not enforced yet (#1306), so it may not be "
            "turned on: a deposit would not wait for the co-approval it promises"
        )
    teams = value.get("teams") or []
    if not isinstance(teams, list):
        raise TypeError("stewardship.teams lists the deployment's steward teams")
    parsed = tuple(_team(team, index) for index, team in enumerate(teams))
    _distinct(t.team_id for t in parsed)
    return Stewardship(teams=parsed, visibility=visibility, deposit_co_approval=co_approval)


def _distinct(team_ids: Iterable[str]) -> None:
    seen: set[str] = set()
    for team_id in team_ids:
        if team_id in seen:
            raise ValueError(f"stewardship.teams names the team {team_id!r} more than once")
        seen.add(team_id)
