"""Telling people that an escalation has moved (docs/specs/stewardship.md, invariant 13; #378).

Nobody should have to watch a queue. Each event in a project's log that someone else must act on
is a **notice**:

- for the **steward team** the escalation is routed to: it was opened or transferred to the team,
  sent again because nobody took it, or the researcher replied, withdrew or re-opened it. A team
  is emailed at the address the profile names for it (`StewardTeam.notify`), for the notices it
  chose (`notify_on`). The deployment holds no person's email address
  (docs/specs/policy-and-identity.md, invariant 15), so a team address, a shared mailbox or a
  helpdesk's intake, is the one recipient;
- for the project's **researchers**: a steward asked them something, resolved or handed back the
  escalation, wrote to them, or the escalation was sent to its team again. These are read in the
  app (`for_person`), from the log, and need no address and no store.

A notice holds a subject and a link, never research content: not the note, not the project's
title and no person's name (#156, C2). The team's name is the institution's, as the profile gives
it. The project log stays authoritative wherever a notice goes; a notice that cannot be sent is
logged and changes nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from dd_harness.policy import Profile
from dd_harness.projects import deletion, member_roles
from dd_harness.projects.escalations import escalations
from dd_harness.projects.rules import (
    ESCALATION_HANDED_BACK,
    ESCALATION_OPENED,
    ESCALATION_REOPENED,
    ESCALATION_REPLIED,
    ESCALATION_REROUTED,
    ESCALATION_RESOLVED,
    ESCALATION_TRANSFERRED,
    ESCALATION_WAITING,
    ESCALATION_WITHDRAWN,
    STEWARD_MESSAGE,
)
from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import Principal

log = logging.getLogger(__name__)

type Audience = Literal["team", "researchers"]

# The page a steward team's notice links to: the queue of requests.
STEWARD_QUEUE_PATH = "/steward"

# What each event tells a team, by the name `notify_on` uses (dd_harness.stewardship.TEAM_NOTICES),
# and the subject it is sent with; `{team}` is the team's name.
_TEAM: Mapping[str, tuple[str, str]] = {
    ESCALATION_OPENED: ("opened", "A new request for {team}"),
    # A transferred escalation is new to the team it is sent to, which hears of it as opened.
    ESCALATION_TRANSFERRED: ("opened", "A request was passed to {team}"),
    ESCALATION_REROUTED: ("rerouted", "A request for {team} is still waiting for a steward"),
    ESCALATION_REPLIED: ("replied", "A researcher replied to a request for {team}"),
    ESCALATION_WITHDRAWN: ("withdrawn", "A researcher withdrew a request to {team}"),
    ESCALATION_REOPENED: ("reopened", "A researcher re-opened a request to {team}"),
}
# What each event tells the project's researchers.
_RESEARCHERS: Mapping[str, tuple[str, str]] = {
    ESCALATION_WAITING: ("waiting", "{team} asked you something about your request"),
    ESCALATION_RESOLVED: ("resolved", "{team} resolved your request"),
    ESCALATION_HANDED_BACK: ("handed_back", "{team} handed your request back to you"),
    ESCALATION_REROUTED: ("rerouted", "Your request was sent to {team} again"),
    STEWARD_MESSAGE: ("message", "A data steward wrote to you"),
}
# The kinds a researcher's notice may have, for the shell's choice of what to show.
RESEARCHER_NOTICES = tuple(kind for kind, _ in _RESEARCHERS.values())


@dataclass(frozen=True)
class Notice:
    """One thing someone is told: whom, about what, and where to look. `path` is a page of the
    app, which a sender makes absolute."""

    audience: Audience
    kind: str
    project_id: str
    event_id: str
    at: str
    subject: str
    path: str
    team_id: str | None = None
    escalation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        found = {
            "kind": self.kind,
            "project_id": self.project_id,
            "event_id": self.event_id,
            "at": self.at,
            "subject": self.subject,
            "path": self.path,
        }
        if self.escalation_id is not None:
            found["escalation_id"] = self.escalation_id
        return found


class Notifier(Protocol):
    """Sends a team's notice to an address. Never raises for a notice it could not send: the
    log stays authoritative, so a failure is logged and nothing else changes."""

    def send(self, address: str, notice: Notice) -> None: ...


class NullNotifier:
    """The notifier of a deployment that sends no email: every notice is read in the app."""

    def send(self, address: str, notice: Notice) -> None:
        return None


NULL_NOTIFIER: Notifier = NullNotifier()


def _team_name(profile: Profile, team_id: str | None) -> str:
    team = profile.stewardship.team(team_id) if team_id else None
    return team.name if team else "the data stewards"


def _escalation_team(events: Iterable[Mapping[str, Any]], escalation_id: str) -> str | None:
    found = next((e for e in escalations(events) if e["escalation_id"] == escalation_id), None)
    return found["team_id"] if found else None


def _team_of(events: Sequence[Mapping[str, Any]], event: Mapping[str, Any]) -> str | None:
    """The team an event concerns: the one it names, or that of the escalation it moves, or for
    a steward's message the team of the project's latest escalation."""
    if event.get("team_id"):
        return str(event["team_id"])
    if event.get("escalation_id"):
        return _escalation_team(events, event["escalation_id"])
    found = escalations(events)
    return found[-1]["team_id"] if found else None


def notice_of(
    profile: Profile,
    events: Sequence[Mapping[str, Any]],
    event: Mapping[str, Any],
    audience: Audience,
) -> Notice | None:
    """The notice `event` gives `audience`, or None. `events` is the project's log, holding
    `event`."""
    kind, subject = (_TEAM if audience == "team" else _RESEARCHERS).get(event["event"], ("", ""))
    if not kind:
        return None
    team_id = _team_of(events, event)
    escalation_id = event.get("escalation_id") or (
        event["event_id"] if event["event"] == ESCALATION_OPENED else None
    )
    project_id = str(event["project_id"])
    return Notice(
        audience=audience,
        kind=kind,
        project_id=project_id,
        event_id=str(event["event_id"]),
        at=str(event["at"]),
        subject=subject.format(team=_team_name(profile, team_id)),
        path=STEWARD_QUEUE_PATH if audience == "team" else f"/projects/{project_id}",
        team_id=team_id,
        escalation_id=escalation_id,
    )


def dispatch(
    notifier: Notifier,
    profile: Profile,
    events: Sequence[Mapping[str, Any]],
    appended: Iterable[Mapping[str, Any]],
) -> list[Notice]:
    """Email the team each of `appended` concerns, where the profile names an address for it and
    the team chose to be told about that kind of notice. Returns the notices sent. `events` is the
    project's log, holding `appended`."""
    sent = []
    for event in appended:
        notice = notice_of(profile, events, event, "team")
        team = profile.stewardship.team(notice.team_id) if notice and notice.team_id else None
        if notice is None or team is None or team.notify is None:
            continue
        if notice.kind in team.notify_on:
            notifier.send(team.notify, notice)
            sent.append(notice)
    return sent


def for_person(
    store: ProjectStorage, profile: Profile, person: Principal, *, since: datetime
) -> list[dict[str, Any]]:
    """What the stewards have done in `person`'s projects since `since`, the newest first: each a
    notice for the project's researchers. One read, through the listing index that finds a
    person's projects ([Storage](docs/specs/storage.md)); a deleted project, or one the person is
    no longer a member of, gives none."""
    found = []
    for events in store.logs_naming(person.principal_id).values():
        if deletion(events) is not None or person.principal_id not in member_roles(events):
            continue
        for event in events:
            if datetime.fromisoformat(event["at"]) < since:
                continue
            if (notice := notice_of(profile, events, event, "researchers")) is not None:
                found.append(notice.to_dict())
    return sorted(found, key=lambda notice: notice["at"], reverse=True)
