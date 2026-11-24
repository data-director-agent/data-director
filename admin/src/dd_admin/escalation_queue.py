"""The steward teams' queues as an operator reads them (docs/guide/operations/admin.md,
"Escalations"): for each team the profile names, the escalations still live in its projects,
how long each has waited and whether it is overdue to be sent to its team again.

An escalation is a record in a project's log (`dd_harness.projects.escalations`), and the store
indexes a team's projects, so one read per team gives its queue. Only the teams the profile names
are read; an escalation routed to a team the profile no longer names is not shown.

This is for the operators who run the deployment and its sweep (`data-director-escalations.timer`),
to see that a queue is moving. A researcher's note and a steward's reply are never shown, nor is
any action offered: stewards act in the app, and the admin service writes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from dd_admin.policy_view import PolicyView
from dd_harness.projects.escalations import LIVE_STATES, OPEN, TAKEN, escalations
from dd_harness.role_events import team_key
from dd_harness.storage import ProjectStorage


@dataclass(frozen=True)
class Item:
    """One live escalation, without its note."""

    team_id: str
    project_id: str
    title: str
    escalation_id: str
    state: str
    origin: str
    opened_at: datetime | None
    routed_at: datetime | None
    taken_by: dict[str, Any] | None
    overdue: bool = False


@dataclass(frozen=True)
class TeamRow:
    team_id: str
    name: str
    members: int
    live: int = 0
    open: int = 0
    taken: int = 0
    overdue: int = 0
    oldest_open: datetime | None = None


@dataclass
class Queue:
    """`configured` is False when there is no project store or profile to read; `problems` names
    each team whose projects could not be read, so the others still show."""

    configured: bool = False
    reason: str | None = None
    teams: list[TeamRow] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    reroute_after: timedelta | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def open(self) -> int:
        return sum(t.open for t in self.teams)

    @property
    def overdue(self) -> int:
        return sum(t.overdue for t in self.teams)


def _when(value: object) -> datetime | None:
    try:
        found = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def _item(team_id: str, project_id: str, title: str, e: dict[str, Any], *, overdue: bool) -> Item:
    origin = e.get("origin")
    return Item(
        team_id=team_id,
        project_id=project_id,
        title=title,
        escalation_id=str(e["escalation_id"]),
        state=str(e["state"]),
        origin=str(origin.get("kind", "")) if isinstance(origin, dict) else "",
        opened_at=_when(e.get("opened_at")),
        routed_at=_when(e.get("routed_at")),
        taken_by=e.get("taken_by"),
        overdue=overdue,
    )


def _team_items(
    store: ProjectStorage, team_id: str, reroute_after: timedelta | None, now: datetime
) -> list[Item]:
    """The live escalations to `team_id`, over every project its index names."""
    found = []
    for project_id, events in store.logs_naming(team_key(team_id)).items():
        title = str(store.summary_of(project_id, events).get("title") or project_id)
        for e in escalations(events):
            if e["team_id"] != team_id or e["state"] not in LIVE_STATES:
                continue
            routed = _when(e.get("routed_at"))
            late = bool(
                reroute_after and e["state"] == OPEN and routed and now - routed > reroute_after
            )
            found.append(_item(team_id, project_id, title, e, overdue=late))
    return found


def read(projects: ProjectStorage | None, view: PolicyView, now: datetime | None = None) -> Queue:
    """Each profile team's live escalations, the longest-waiting first."""
    if projects is None:
        return Queue(reason="DD_PROJECTS_DIR")
    if view.profile is None:
        return Queue(reason="a profile (see Policy)")
    now = now or datetime.now(UTC)
    stewardship = view.profile.stewardship
    queue = Queue(configured=True, reroute_after=stewardship.reroute_after)
    for team in stewardship.teams:
        try:
            items = _team_items(projects, team.team_id, stewardship.reroute_after, now)
        except Exception as exc:  # noqa: BLE001 - any backend failure is shown, not raised
            queue.problems.append(f"{team.name}: {exc}")
            items = []
        opened = [i for i in items if i.state == OPEN and i.routed_at]
        queue.teams.append(
            TeamRow(
                team_id=team.team_id,
                name=team.name,
                members=len(team.members),
                live=len(items),
                open=sum(1 for i in items if i.state == OPEN),
                taken=sum(1 for i in items if i.state == TAKEN),
                overdue=sum(1 for i in items if i.overdue),
                oldest_open=min((i.routed_at for i in opened if i.routed_at), default=None),
            )
        )
        queue.items.extend(items)
    queue.items.sort(key=lambda i: i.routed_at or now)
    return queue
