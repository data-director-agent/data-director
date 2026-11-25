"""Whom a steward may pass an escalation to (docs/specs/stewardship.md, invariant 4;
docs/ui/steward-escalation-flows.md, Flow G).

Two steward moves name a target. `reassign` gives a taken escalation to a colleague in the team
it is routed to, so that it is never stuck with one person; `transfer` sends it to another of the
profile's teams. The project rules (`dd_harness.projects.escalations`) record the move and check
that a target is given and is not where the escalation already is. What needs the profile is
here:

- **checking** (`checked`): a colleague must be in the escalation's team and not a member of the
  project, who would act in it as a member (invariant 2); a team must be one the profile names;
- **listing** (`targets`): each colleague or team the move could name, so that the shell offers
  only those, and decides none;
- **what each person may do** (`permitted_moves`): the moves of their side that an escalation's
  state allows, each with the targets it may name, or, for a member reaching it as a steward,
  each steward move refused with why (invariant 2).

The profile names people by identifier only. A colleague's name comes from `names`, which the
shell gives (public ORCID names); without one, the identifier stands for the name.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from dd_harness.policy import Profile
from dd_harness.projects import EscalationRefusal, EscalationRefusedError, member_roles
from dd_harness.projects.escalations import MOVES, Side
from dd_sdk.contract.models import Principal

# The names of people by `principal_id`, for those it knows.
type NamesOf = Callable[[Iterable[str]], Mapping[str, str]]


def _colleagues(
    profile: Profile, events: Sequence[Mapping[str, Any]], escalation: Mapping[str, Any]
) -> list[str]:
    team = profile.stewardship.team(escalation["team_id"])
    if team is None:
        return []
    members = member_roles(events)
    taken = (escalation["taken_by"] or {}).get("principal_id")
    return sorted(m for m in team.members if m != taken and m not in members)


def targets(
    profile: Profile,
    events: Sequence[Mapping[str, Any]],
    escalation: Mapping[str, Any],
    move: str,
    names: NamesOf | None = None,
) -> list[dict[str, str]]:
    """Each colleague or team `move` could pass `escalation` to, as `{id, name}`: none for a
    move that names no target."""
    step = MOVES.get(move)
    if step is None or step.target is None:
        return []
    if step.target == "team":
        return [
            {"id": team.team_id, "name": team.name}
            for team in profile.stewardship.teams
            if team.team_id != escalation["team_id"]
        ]
    found = _colleagues(profile, events, escalation)
    named = names(found) if names is not None and found else {}
    return [{"id": pid, "name": named.get(pid) or pid} for pid in found]


def checked(
    profile: Profile,
    events: Sequence[Mapping[str, Any]],
    escalation: Mapping[str, Any],
    move: str,
    to: str | None,
    names: NamesOf | None = None,
) -> str | Principal | None:
    """The target `to` names for `move`, as the rules take it: the colleague for `reassign`,
    the team's id for `transfer`, and `to` unchanged for any other move or none given. Raises
    `EscalationRefusedError` for a team the profile does not name, or a colleague who is not in
    the escalation's team or is a member of the project."""
    step = MOVES.get(move)
    if step is None or step.target is None or not to:
        return to
    stewardship = profile.stewardship
    if step.target == "team":
        if stewardship.team(to) is None:
            raise EscalationRefusedError(
                EscalationRefusal.UNKNOWN_TEAM, f"this deployment has no steward team {to!r}"
            )
        return to
    team = stewardship.team(escalation["team_id"])
    if team is None or to not in team.members:
        raise EscalationRefusedError(
            EscalationRefusal.NOT_IN_TEAM, "only a steward in the same team can take it over"
        )
    if to in member_roles(events):
        raise EscalationRefusedError(
            EscalationRefusal.TARGET_MEMBER_OF_PROJECT,
            "that steward is a member of this project, so cannot act in it as its steward",
        )
    name = (names([to]) if names is not None else {}).get(to) or to
    return Principal(principal_id=to, name=name)


type TargetsOf = Callable[[str], list[dict[str, str]]]


def permitted_moves(
    side: Side | None,
    escalation: Mapping[str, Any],
    *,
    member: bool = False,
    targets: TargetsOf | None = None,
) -> list[dict[str, Any]]:
    """The moves of `side` that `escalation`'s state allows, each with whether it needs a note:
    `{move, permitted, note}`. `member` marks someone reaching it as a steward who is a member of
    the project: each steward move is listed, refused with `member-of-project` (invariant 2).
    With `targets`, a move that names a target also carries the colleagues or teams it may name,
    and is left out where there are none; without, such a move is left out. None for someone on
    neither side."""
    if side is None:
        return []
    found = []
    for name, step in MOVES.items():
        if step.side != side or escalation["state"] not in step.starts:
            continue
        move: dict[str, Any] = {"move": name, "permitted": not member, "note": step.note}
        if step.target is not None:
            named = targets(name) if targets is not None else []
            if not named:
                continue
            move["targets"] = named
        if member:
            move["refusal"] = EscalationRefusal.MEMBER_OF_PROJECT.value
        found.append(move)
    return found


def targets_of(
    profile: Profile,
    events: Sequence[Mapping[str, Any]],
    escalation: Mapping[str, Any],
    names: NamesOf | None,
) -> TargetsOf:
    """`targets` for `escalation`, by move, as `permitted_moves` takes it."""
    return lambda move: targets(profile, events, escalation, move, names)
