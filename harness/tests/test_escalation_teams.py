"""Stewards work as teams: an escalation is reassigned to a colleague or transferred to another
team, a steward who is a member of the project never acts in it as its steward, and any member of
the team that holds a pause may lift it (docs/specs/stewardship.md, invariants 2, 4 and 8;
docs/ui/steward-escalation-flows.md, Flow G; #1308).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_escalations import (
    COLLEAGUE,
    FACULTY,
    LIBRARY,
    OTHER_STEWARD,
    STEWARD,
    open_one,
    profile,
)
from test_steward_interventions import act

from dd_harness import escalation_api
from dd_harness.escalation_api import Requested
from dd_harness.notifications import dispatch
from dd_harness.policy import Profile
from dd_harness.projects import (
    ESCALATION_REASSIGNED,
    ESCALATION_TRANSFERRED,
    EscalationRefusal,
    EscalationRefusedError,
    ProjectStore,
    UnknownProjectError,
)
from dd_harness.projects.escalations import escalations
from dd_harness.projects.stewarding import pause_of
from dd_harness.role_events import team_key
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

pytestmark = pytest.mark.requirement("C13.6")

COVER = Principal(principal_id="https://orcid.org/0000-0003-1415-9269", name="A Cover")
TEAM = {**LIBRARY, "members": [STEWARD.principal_id, COVER.principal_id]}
TEAMS = profile(TEAM, FACULTY)


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project_id(projects: ProjectStore) -> str:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    return project_id


@pytest.fixture
def escalated(projects: ProjectStore, project_id: str) -> dict[str, Any]:
    return open_one(projects, project_id, TEAMS, team_id="library-rdm")


def steward_move(
    projects: ProjectStore,
    project_id: str,
    escalation: dict[str, Any],
    move: str,
    *,
    to: str | None = None,
    note: str | None = "A note",
    by: Principal = STEWARD,
    found: Profile = TEAMS,
) -> dict[str, Any]:
    return escalation_api.move(
        projects,
        found,
        project_id,
        Requested(escalation["escalation_id"], move, note, to, as_steward=True),
        acted_for=by,
        caused_by="test",
        names=lambda ids: {pid: "Named " + pid[-4:] for pid in ids},
    )


def refusal_of(call: Any) -> EscalationRefusal:
    with pytest.raises(EscalationRefusedError) as raised:
        call()
    return raised.value.refusal


def targets_of(escalation: dict[str, Any], move: str) -> list[str] | None:
    listed = next((m for m in escalation["permitted_moves"] if m["move"] == move), None)
    return None if listed is None else [t["id"] for t in listed["targets"]]


# --- reassigning -----------------------------------------------------------------------------


def test_a_colleague_in_the_team_takes_over_a_taken_escalation(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    taken = steward_move(projects, project_id, escalated, "take", note=None)
    assert targets_of(taken, "reassign") == [COVER.principal_id]
    # Any member of the team may reassign it, not only the steward who took it.
    moved = steward_move(projects, project_id, taken, "reassign", to=COVER.principal_id, by=COVER)
    assert moved["state"] == "taken"
    assert moved["taken_by"]["principal_id"] == COVER.principal_id
    assert moved["taken_by"]["name"]
    last = moved["history"][-1]
    assert last["move"] == "reassign"
    assert last["from_steward"]["principal_id"] == STEWARD.principal_id
    assert last["to_steward"]["principal_id"] == COVER.principal_id
    (event,) = [e for e in projects.events(project_id) if e["event"] == ESCALATION_REASSIGNED]
    assert event["acting_as"] == "steward"
    # The researcher reads the same history.
    (shown,) = escalation_api.for_project(projects, TEAMS, project_id, TEST_PRINCIPAL)[
        "escalations"
    ]
    assert shown["history"][-1]["move"] == "reassign"
    assert targets_of(moved, "reassign") == [STEWARD.principal_id]


def test_reassigning_is_refused_outside_the_team_and_to_a_member_of_the_project(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    with_member = profile({**TEAM, "members": [*TEAM["members"], COLLEAGUE.principal_id]})
    taken = steward_move(projects, project_id, escalated, "take", note=None, found=with_member)
    # A member of the project is never offered as a colleague to pass it to.
    assert targets_of(taken, "reassign") == [COVER.principal_id]

    def to(target: str | None, found: Profile = with_member) -> Any:
        return lambda: steward_move(projects, project_id, taken, "reassign", to=target, found=found)

    assert refusal_of(to(OTHER_STEWARD.principal_id)) is EscalationRefusal.NOT_IN_TEAM
    assert refusal_of(to(COLLEAGUE.principal_id)) is EscalationRefusal.TARGET_MEMBER_OF_PROJECT
    assert refusal_of(to(STEWARD.principal_id)) is EscalationRefusal.SAME_TARGET
    assert refusal_of(to(None)) is EscalationRefusal.TARGET_REQUIRED
    assert not [e for e in projects.events(project_id) if e["event"] == ESCALATION_REASSIGNED]


def test_only_a_taken_escalation_is_reassigned(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    assert targets_of(escalated, "reassign") is None
    refused = refusal_of(
        lambda: steward_move(projects, project_id, escalated, "reassign", to=COVER.principal_id)
    )
    assert refused is EscalationRefusal.MOVE_NOT_ALLOWED


# --- transferring ----------------------------------------------------------------------------


@pytest.mark.parametrize("before", [[], ["take"], ["take", "wait"]])
def test_a_live_escalation_is_transferred_to_another_team(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any], before: list[str]
) -> None:
    current = escalated
    for move in before:
        current = steward_move(projects, project_id, current, move)
    (row,) = escalation_api.queue(projects, TEAMS, STEWARD)
    assert targets_of(row, "transfer") == ["faculty"]
    moved = steward_move(projects, project_id, current, "transfer", to="faculty")
    assert moved["state"] == "open"
    assert moved["team_id"] == "faculty"
    assert moved["taken_by"] is None
    assert moved["routed_at"] == moved["updated_at"]
    last = moved["history"][-1]
    assert (last["move"], last["from_team"], last["team_id"]) == (
        "transfer",
        "library-rdm",
        "faculty",
    )
    # The team it left no longer queues it; the team it went to finds it through its index.
    assert escalation_api.queue(projects, TEAMS, STEWARD) == []
    assert project_id in projects.logs_naming(team_key("faculty"))
    (queued,) = escalation_api.queue(projects, TEAMS, OTHER_STEWARD)
    assert queued["escalation_id"] == escalated["escalation_id"]
    assert [m["move"] for m in queued["permitted_moves"]] == ["take", "transfer"]
    # The researcher sees the new team's name.
    (shown,) = escalation_api.for_project(projects, TEAMS, project_id, TEST_PRINCIPAL)[
        "escalations"
    ]
    assert shown["team_name"] == FACULTY["name"]


def test_transferring_needs_a_note_and_a_team_the_profile_names(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    def to(target: str | None, note: str | None = "Not ours") -> Any:
        return lambda: steward_move(
            projects, project_id, escalated, "transfer", to=target, note=note
        )

    assert refusal_of(to("faculty", None)) is EscalationRefusal.NOTE_REQUIRED
    assert refusal_of(to("nowhere")) is EscalationRefusal.UNKNOWN_TEAM
    assert refusal_of(to("library-rdm")) is EscalationRefusal.SAME_TARGET
    assert refusal_of(to(None)) is EscalationRefusal.TARGET_REQUIRED
    with pytest.raises(UnknownProjectError):
        steward_move(
            projects, project_id, escalated, "transfer", to="library-rdm", by=OTHER_STEWARD
        )
    assert not [e for e in projects.events(project_id) if e["event"] == ESCALATION_TRANSFERRED]


def test_a_deployment_with_one_team_offers_no_transfer(
    projects: ProjectStore, project_id: str
) -> None:
    single = profile(LIBRARY)
    open_one(projects, project_id, single)
    (row,) = escalation_api.queue(projects, single, STEWARD)
    assert targets_of(row, "transfer") is None


def test_the_team_an_escalation_is_transferred_to_is_told(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    told = profile(TEAM, {**FACULTY, "notify": "faculty-data@example.org"})
    steward_move(projects, project_id, escalated, "transfer", to="faculty", found=told)
    events = projects.events(project_id)
    sent = dispatch(_Recording(), told, events, events[-1:])
    assert [(n.kind, n.team_id) for n in sent] == [("opened", "faculty")]


class _Recording:
    def __init__(self) -> None:
        self.sent: list[tuple[str, Any]] = []

    def send(self, address: str, notice: Any) -> None:
        self.sent.append((address, notice))


# --- conflicts of interest -------------------------------------------------------------------


@pytest.mark.parametrize("move", ["reassign", "transfer"])
def test_a_steward_who_is_a_member_of_the_project_may_not_move_its_escalation(
    projects: ProjectStore, project_id: str, move: str
) -> None:
    found = profile({**TEAM, "members": [*TEAM["members"], COLLEAGUE.principal_id]}, FACULTY)
    escalation = open_one(projects, project_id, found, team_id="library-rdm")
    escalation = steward_move(projects, project_id, escalation, "take", note=None, found=found)
    to = COVER.principal_id if move == "reassign" else "faculty"
    refused = refusal_of(
        lambda: steward_move(
            projects, project_id, escalation, move, to=to, by=COLLEAGUE, found=found
        )
    )
    assert refused is EscalationRefusal.MEMBER_OF_PROJECT
    (row,) = escalation_api.queue(projects, found, COLLEAGUE)
    listed = {m["move"]: m for m in row["permitted_moves"]}
    assert listed[move]["permitted"] is False
    assert listed[move]["refusal"] == "member-of-project"


# --- cover for a pause -----------------------------------------------------------------------


def test_any_member_of_the_team_lifts_a_pause_a_colleague_applied(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    act(projects, project_id, "pause", STEWARD, TEAMS)
    with pytest.raises(UnknownProjectError):
        act(projects, project_id, "resume", OTHER_STEWARD, TEAMS)
    act(projects, project_id, "resume", COVER, TEAMS)
    assert pause_of(projects.events(project_id)) is None


def test_a_pause_stays_with_its_team_when_the_escalation_is_transferred(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    act(projects, project_id, "pause", STEWARD, TEAMS)
    steward_move(projects, project_id, escalated, "transfer", to="faculty")
    held = pause_of(projects.events(project_id))
    assert held is not None and held["team_id"] == "library-rdm"
    (moved,) = escalations(projects.events(project_id))
    assert moved["team_id"] == "faculty"
    act(projects, project_id, "resume", COVER, TEAMS)
    assert pause_of(projects.events(project_id)) is None
