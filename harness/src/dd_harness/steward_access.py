"""How a data steward reaches a project: the steward path beside `dd_harness.project_access`
(docs/specs/stewardship.md, invariants 2, 3 and 6).

A deployment role never makes anyone a member of a project. A steward reaches a project by this
separate path, which answers "steward of this project, through these teams" or nothing, from the
project's log and the profile alone:

- a member of the project acts there as a member, never as its steward, so has no steward access
  (invariant 2), and nor has anyone in a deleted project;
- with `stewardship.visibility: escalated` (the default), a steward reaches a project while it
  has an escalation routed to one of their teams that is `open`, `taken` or `waiting for
  researcher`, or a pause one of their teams holds (invariant 3);
- with `visibility: scope`, also any project whose owners chose one of their teams as its support
  team, though only to read it until a matter is escalated.

What a steward may do there is the closed list of invariant 6, `ACTIONS`; `refusal` says why one
is not open to them. Recording each read, and each action, is `dd_harness.steward_api`'s.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from dd_harness.policy import Profile
from dd_harness.projects import deletion, member_roles
from dd_harness.projects.escalations import LIVE_STATES, escalations, support_team
from dd_harness.projects.stewarding import pause_of
from dd_harness.storage import ProjectLifecycle
from dd_sdk.contract.models import Principal

type StewardAction = Literal[
    "read", "message", "propose_edit", "run", "pause", "resume", "clear_gate", "refuse_gate"
]
# Invariant 6, in the order the spec's table gives them. Moving an escalation is
# `dd_harness.escalation_api`'s, which checks the team it is routed to.
ACTIONS: Final[tuple[StewardAction, ...]] = (
    "read",
    "message",
    "propose_edit",
    "run",
    "pause",
    "resume",
    "clear_gate",
    "refuse_gate",
)
# Why an action is not open to a steward who reaches the project.
NO_LIVE_ESCALATION: Final = "no-live-escalation"
NO_PAUSE_HELD: Final = "no-pause-held"


@dataclass(frozen=True)
class StewardAccess:
    """A steward's access to one project: the teams of theirs it comes through, those of them
    with a live escalation on it, and whether one of them holds its pause."""

    teams: frozenset[str]
    escalated_teams: frozenset[str]
    holds_pause: bool

    @property
    def escalated(self) -> bool:
        return bool(self.escalated_teams)

    def refusal(self, action: StewardAction) -> str | None:
        """Why `action` is not open to the steward, or None if it is. Reading is open to every
        steward who reaches the project; lifting a pause to its team; a note to the researcher
        while a matter is escalated or a pause held; everything else while a matter is
        escalated."""
        if action == "read":
            return None
        if action == "resume":
            return None if self.holds_pause else NO_PAUSE_HELD
        if action == "message" and self.holds_pause:
            return None
        return None if self.escalated else NO_LIVE_ESCALATION


def access_in(
    profile: Profile, events: Sequence[Mapping[str, Any]], principal: Principal
) -> StewardAccess | None:
    """`principal`'s steward access to the project whose log is `events`, or None."""
    if principal.principal_id in member_roles(events) or deletion(events) is not None:
        return None
    stewardship = profile.stewardship
    mine = {team.team_id for team in stewardship.teams_of(principal.principal_id)}
    if not mine:
        return None
    live = {e["team_id"] for e in escalations(events) if e["state"] in LIVE_STATES} & mine
    pause = pause_of(events)
    held = {pause["team_id"]} & mine if pause is not None else set()
    chosen = support_team(events) if stewardship.visibility == "scope" else None
    supported = {chosen} & mine if chosen is not None else set()
    teams = live | held | supported
    if not teams:
        return None
    return StewardAccess(frozenset(teams), frozenset(live), holds_pause=bool(held))


def steward_of(
    store: ProjectLifecycle, profile: Profile, project_id: str, principal: Principal
) -> StewardAccess | None:
    """`principal`'s steward access to the project `project_id`, or None: no such project, a
    member of it, or none of their teams reaches it."""
    if not store.exists(project_id):
        return None
    return access_in(profile, store.events(project_id), principal)
