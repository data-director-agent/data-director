"""Escalation to a data steward, as every way in reaches it (docs/specs/stewardship.md,
invariants 4, 5 and 11; docs/ui/steward-escalation-flows.md).

The project rules (`dd_harness.projects.escalations`) keep the record and the state of each
escalation. What they cannot know is here, because it needs the profile or the runs:

- **routing** (`route`): an escalation goes to the project's support team, the steward team its
  owners chose. With none chosen, it goes to the profile's only team, or, where the profile names
  several, to the team the sender picks; an owner's pick also becomes the project's support team.
  A deployment with no steward team refuses it, saying so and giving no team (invariant 11);
- **origin** (`check_origin`): an escalation is opened only when a person confirms it
  (invariant 5). One that names a run, a policy-gate referral, an agent's abstention or referral,
  or an orchestrator's offer, must name a run of this project that ended that way;
- **sides** (`side_of`): a member of the project acts on the researcher's side; a steward of the
  team the escalation is routed to who is not a member acts on the steward's. A member who is
  also a steward of that team acts as a member (invariant 2), so may not take the escalation;
- **what each person may do** (`permitted_moves`): the moves of their side that the
  escalation's state allows, or, for a member reaching it as a steward, each steward move refused
  with why, so that the shell renders the moves and decides none. A move that names a target,
  `reassign` or `transfer`, carries the colleagues or teams it may name, and is left out where
  there are none (`dd_harness.escalation_targets`, re-exported here);
- **the queue** (`queue`): the escalations routed to a steward's teams, found through the team
  index (`dd_harness.role_events.team_key`) in one read per team;
- **telling the team** (`tell_team`): each escalation opened, or moved by the researcher, is
  emailed to the team's address, where the profile names one (invariant 13);
- **the sweep** (`sweep`): an escalation nobody has taken within the profile's `reroute_after` is
  sent to its team again, for the deployment, and the team and the researchers are told.

A steward reaches only an escalation's record and moves here; opening the project as a steward
is `dd_harness.steward_api`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dd_harness import escalation_targets, project_access
from dd_harness.escalation_targets import NamesOf
from dd_harness.escalation_targets import permitted_moves as permitted_moves
from dd_harness.notifications import Notifier, dispatch
from dd_harness.policy import Profile
from dd_harness.project_access import Action, Role
from dd_harness.projects import (
    EscalationRefusal,
    EscalationRefusedError,
    UnknownProjectError,
    deletion,
    member_roles,
)
from dd_harness.projects.escalations import (
    LIVE_STATES,
    ORIGINS,
    RESEARCHER,
    STEWARD,
    MoveAsked,
    NewEscalation,
    Side,
    escalations,
    support_team,
)
from dd_harness.role_events import team_key
from dd_harness.stewardship import StewardTeam
from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import Principal, PrincipalKind

type EnvelopeOf = Callable[[str], Mapping[str, Any] | None]

# What each origin that names a run asks of the run's outcome.
_POLICY_REASON = "policy_requires_approval"

# Whom the sweep acts for when it sends an escalation to its team again: the deployment, an
# accountable role that no person signs in as (invariant 13).
SWEEP = Principal(
    principal_id="urn:dd:deployment:escalation-sweep",
    name="Data Director",
    principal_kind=PrincipalKind.ACCOUNTABLE_ROLE,
)
SWEEP_CAUSED_BY = "dd-harness escalations sweep"


def tell_team(
    notifier: Notifier,
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    escalation: Mapping[str, Any],
) -> None:
    """Tell the escalation's team about its latest move, as `open_escalation`, `move` or `sweep`
    returned it, if that move is one the team hears of (`dd_harness.notifications.dispatch`).
    Every way in calls it after a move it made, outside the move, so that a mail server that is
    slow or down never holds a project's log."""
    event_id = escalation["history"][-1]["event_id"]
    events = store.events(project_id)
    dispatch(notifier, profile, events, [e for e in events if e["event_id"] == event_id])


def route(
    profile: Profile, events: Sequence[Mapping[str, Any]], requested: str | None
) -> StewardTeam:
    """The steward team a new escalation in the project whose log is `events` goes to.
    `requested` is the team the sender picked, if any. Raises `EscalationRefusedError`."""
    stewardship = profile.stewardship
    if not stewardship.teams:
        raise EscalationRefusedError(
            EscalationRefusal.NO_STEWARD_TEAM, "this deployment names no data steward team"
        )
    if requested is not None:
        team = stewardship.team(requested)
        if team is None:
            raise EscalationRefusedError(
                EscalationRefusal.UNKNOWN_TEAM, f"this deployment has no steward team {requested!r}"
            )
        return team
    chosen = support_team(events)
    if chosen is not None and (team := stewardship.team(chosen)) is not None:
        return team
    if len(stewardship.teams) == 1:
        return stewardship.teams[0]
    raise EscalationRefusedError(
        EscalationRefusal.TEAM_REQUIRED,
        "this deployment has several steward teams and the project has no support team: "
        "choose the team to send it to",
    )


def check_origin(
    origin: Mapping[str, Any], project_id: str, envelope_of: EnvelopeOf
) -> dict[str, Any]:
    """`origin`, checked against the run it names: the origin to record. Raises
    `EscalationRefusedError` for an unknown kind, or a run that is not this project's or did not
    end as its kind says."""
    kind = origin.get("kind")
    invocation_id = origin.get("invocation_id")
    if kind not in ORIGINS:
        raise EscalationRefusedError(
            EscalationRefusal.ORIGIN_MISMATCH,
            f"an escalation comes from one of {', '.join(ORIGINS)}, not {kind!r}",
        )
    if kind == "researcher":
        if invocation_id is not None:
            raise EscalationRefusedError(
                EscalationRefusal.ORIGIN_MISMATCH,
                "an escalation the researcher raises names no run; one from a run names its kind",
            )
        return {"kind": kind}
    envelope = envelope_of(str(invocation_id)) if invocation_id else None
    if envelope is None or envelope.get("project_id") != project_id:
        raise EscalationRefusedError(
            EscalationRefusal.ORIGIN_MISMATCH, f"no run {invocation_id!r} in this project"
        )
    outcome = envelope.get("outcome") or {}
    status = outcome.get("status")
    if (
        kind == "policy_gate"
        and (status, outcome.get("reason_code")) != ("referred", _POLICY_REASON)
    ) or (kind == "agent" and status not in ("abstained", "referred")):
        raise EscalationRefusedError(
            EscalationRefusal.ORIGIN_MISMATCH,
            f"the run {invocation_id} ended {status!r}, which is not a {kind.replace('_', ' ')} "
            "referral",
        )
    found = {"kind": kind, "invocation_id": invocation_id}
    if envelope.get("agent_id"):
        found["agent_id"] = envelope["agent_id"]
    return found


def side_of(
    profile: Profile,
    events: Sequence[Mapping[str, Any]],
    principal: Principal,
    escalation: Mapping[str, Any],
) -> Side | None:
    """The side `principal` acts on for `escalation`: the researcher's for a member of the
    project, the steward's for a steward of the team it is routed to, or None."""
    if principal.principal_id in member_roles(events):
        return RESEARCHER
    teams = profile.stewardship.teams_of(principal.principal_id)
    if any(team.team_id == escalation["team_id"] for team in teams):
        return STEWARD
    return None


def _teams(profile: Profile) -> list[dict[str, Any]]:
    return [
        {
            "team_id": team.team_id,
            "name": team.name,
            "supports": list(team.supports),
            **({"contact": team.contact} if team.contact else {}),
            **({"response_time": team.response_time} if team.response_time else {}),
        }
        for team in profile.stewardship.teams
    ]


def _team_name(profile: Profile, team_id: str) -> str:
    team = profile.stewardship.team(team_id)
    return team.name if team else team_id


def _named(profile: Profile, escalation: dict[str, Any]) -> dict[str, Any]:
    """`escalation` with its team's name, and the name of the team each transfer sent it to."""
    return {
        **escalation,
        "team_name": _team_name(profile, escalation["team_id"]),
        "history": [
            {**h, "team_name": _team_name(profile, h["team_id"])} if "team_id" in h else h
            for h in escalation["history"]
        ],
    }


def for_project(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    reader: Principal,
    names: NamesOf | None = None,
) -> dict[str, Any]:
    """The project's escalations, each with the moves `reader` may make on it, the steward teams
    it may send to and its support team, and where a new escalation would go: a team, or none
    with why (invariant 11). `names` names the colleagues a steward may reassign to."""
    events = store.events(project_id)
    try:
        routes_to: str | None = route(profile, events, None).team_id
        unrouted: str | None = None
    except EscalationRefusedError as exc:
        routes_to, unrouted = None, exc.refusal.value
    return {
        "escalations": [
            {
                **_named(profile, e),
                "permitted_moves": permitted_moves(
                    side_of(profile, events, reader, e),
                    e,
                    targets=escalation_targets.targets_of(profile, events, e, names),
                ),
            }
            for e in escalations(events)
        ],
        "teams": _teams(profile),
        "support_team": support_team(events),
        "routes_to": routes_to,
        "unrouted": unrouted,
    }


@dataclass(frozen=True)
class Confirmed:
    """What a person confirmed when sending a matter to a data steward: where it comes from, their
    note, the scope shared as they saw it, and the team they picked, if any (invariant 5)."""

    origin: Mapping[str, Any]
    note: str
    scope_shared: Sequence[str] = ()
    team_id: str | None = None


@dataclass(frozen=True)
class Requested:
    """A move a person asked to make on an escalation, with their note, and the colleague's
    `principal_id` or the team's id a move that names a target names. `as_steward` for a move
    asked on a steward's route, which is made on the steward's side; otherwise the
    researcher's."""

    escalation_id: str
    move: str
    note: str | None = None
    to: str | None = None
    as_steward: bool = False


def open_escalation(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    confirmed: Confirmed,
    envelope_of: EnvelopeOf,
    *,
    acted_for: Principal,
    caused_by: str,
) -> dict[str, Any]:
    """Open an escalation a member of the project confirmed, routed by `route`. An owner's
    pick of a team, where the project has no support team, becomes its support team. Raises
    `EscalationRefusedError`, and `UnknownProjectError` for someone who may not contribute."""
    if not project_access.may(store, project_id, acted_for, Action.CONTRIBUTE):
        raise UnknownProjectError(f"no project {project_id!r}")
    events = store.events(project_id)
    team = route(profile, events, confirmed.team_id)
    origin = check_origin(confirmed.origin, project_id, envelope_of)
    owner = member_roles(events).get(acted_for.principal_id) == Role.OWNER.value
    opened = store.open_escalation(
        project_id,
        NewEscalation(
            team_id=team.team_id,
            origin=origin,
            note=confirmed.note,
            scope_shared=confirmed.scope_shared,
            support=owner and confirmed.team_id is not None and support_team(events) is None,
        ),
        acted_for=acted_for,
        caused_by=caused_by,
    )
    return {**_named(profile, opened), "permitted_moves": permitted_moves(RESEARCHER, opened)}


def choose_support_team(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    team_id: str,
    *,
    acted_for: Principal,
    caused_by: str,
) -> None:
    """Record the project's support team, which an owner chooses from the profile's teams.
    Raises `EscalationRefusedError` for a team the profile does not name."""
    if profile.stewardship.team(team_id) is None:
        raise EscalationRefusedError(
            EscalationRefusal.UNKNOWN_TEAM, f"this deployment has no steward team {team_id!r}"
        )
    store.choose_support_team(project_id, team_id, acted_for=acted_for, caused_by=caused_by)


def move(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    requested: Requested,
    *,
    acted_for: Principal,
    caused_by: str,
    names: NamesOf | None = None,
) -> dict[str, Any]:
    """Make the move `requested` asks for, on the steward's side when `requested.as_steward` (a
    steward's route) and the researcher's otherwise. Raises `UnknownProjectError` for someone on
    neither side, so that a refusal does not reveal the project, and `EscalationRefusedError` for
    a move the rules refuse, a steward who is a member of the project, or a target the profile
    does not allow (`dd_harness.escalation_targets.checked`). `names` names a colleague
    reassigned to."""
    if not store.exists(project_id):
        raise UnknownProjectError(f"no project {project_id!r}")
    as_steward = requested.as_steward
    events = store.events(project_id)
    found = next(
        (e for e in escalations(events) if e["escalation_id"] == requested.escalation_id), None
    )
    side = side_of(profile, events, acted_for, found) if found is not None else None
    if as_steward:
        if found is None or side is None:
            raise UnknownProjectError(f"no project {project_id!r}")
        if side == RESEARCHER:
            raise EscalationRefusedError(
                EscalationRefusal.MEMBER_OF_PROJECT,
                "you are a member of this project, so you act in it as a member, not as its "
                "steward",
            )
    elif acted_for.principal_id not in member_roles(events):
        raise UnknownProjectError(f"no project {project_id!r}")
    to: str | Principal | None = requested.to
    if as_steward and found is not None:
        to = escalation_targets.checked(profile, events, found, requested.move, requested.to, names)
    moved = store.move_escalation(
        project_id,
        requested.escalation_id,
        MoveAsked(requested.move, requested.note, to),
        side=STEWARD if as_steward else RESEARCHER,
        acted_for=acted_for,
        caused_by=caused_by,
    )
    after = store.events(project_id)
    # A steward whose team an escalation was transferred from is on neither side of it now.
    now_side = side_of(profile, after, acted_for, moved) if as_steward else RESEARCHER
    return {
        **_named(profile, moved),
        "permitted_moves": permitted_moves(
            now_side, moved, targets=escalation_targets.targets_of(profile, after, moved, names)
        ),
    }


def sweep(
    store: ProjectStorage, profile: Profile, notifier: Notifier, *, now: datetime
) -> list[dict[str, Any]]:
    """Send each `open` escalation that its team was last asked to take more than the profile's
    `reroute_after` before `now` to that team again, and tell the team; the researchers read it
    in the app. Returns each escalation sent again, with its project. Nothing, where the profile
    sets no `reroute_after` (invariant 13)."""
    after = profile.stewardship.reroute_after
    if after is None:
        return []
    due = now - after
    sent = []
    for team in profile.stewardship.teams:
        for project_id, events in store.logs_naming(team_key(team.team_id)).items():
            if deletion(events) is not None:
                continue
            for escalation in escalations(events):
                if (
                    escalation["team_id"] != team.team_id
                    or escalation["state"] != "open"
                    or datetime.fromisoformat(escalation["routed_at"]) >= due
                ):
                    continue
                rerouted = store.reroute_escalation(
                    project_id,
                    escalation["escalation_id"],
                    routed_before=due,
                    acted_for=SWEEP,
                    caused_by=SWEEP_CAUSED_BY,
                )
                if rerouted is not None:
                    found = {**_named(profile, rerouted), "project_id": project_id}
                    tell_team(notifier, store, profile, project_id, rerouted)
                    sent.append(found)
    return sent


def queue(
    store: ProjectStorage,
    profile: Profile,
    steward: Principal,
    states: Sequence[str] | None = None,
    names: NamesOf | None = None,
) -> list[dict[str, Any]]:
    """The escalations routed to the steward's teams, in live projects, the oldest first: each
    with its project's title, whether the steward is a member of the project (and so may not act
    in it as its steward), and the moves they may make. `states` narrows them; by default the
    live ones, `open`, `taken` and `waiting`. `names` names the colleagues a steward may
    reassign to."""
    wanted = frozenset(states) if states else LIVE_STATES
    rows = []
    for team in profile.stewardship.teams_of(steward.principal_id):
        for project_id, events in store.logs_naming(team_key(team.team_id)).items():
            if deletion(events) is not None:
                continue
            member = steward.principal_id in member_roles(events)
            title = store.summary_of(project_id, events)["title"]
            for escalation in escalations(events):
                if escalation["team_id"] == team.team_id and escalation["state"] in wanted:
                    rows.append(
                        {
                            **_named(profile, escalation),
                            "project_id": project_id,
                            "project_title": title,
                            "member_of_project": member,
                            "permitted_moves": permitted_moves(
                                STEWARD,
                                escalation,
                                member=member,
                                targets=escalation_targets.targets_of(
                                    profile, events, escalation, names
                                ),
                            ),
                        }
                    )
    return sorted(rows, key=lambda row: row["opened_at"])
