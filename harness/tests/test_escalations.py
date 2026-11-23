"""Escalation to a data steward as a record in the project's log (docs/specs/stewardship.md,
invariants 4, 5 and 11; docs/ui/steward-escalation-flows.md, "Escalation states"; #373).

The rules keep each escalation's state and refuse any move the state table does not list, or one
made from the other side. `dd_harness.escalation_api` routes an escalation, checks the run it
names, decides who is on which side, and finds a steward's queue through the team index.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_harness import escalation_api
from dd_harness.escalation_api import Confirmed, Requested
from dd_harness.policy import Profile
from dd_harness.projects import (
    ESCALATION_OPENED,
    SUPPORT_TEAM_CHOSEN,
    EscalationRefusal,
    EscalationRefusedError,
    ProjectStore,
    UnknownProjectError,
)
from dd_harness.projects.escalations import (
    MOVES,
    RESEARCHER,
    NewEscalation,
    Side,
    escalations,
    support_team,
)
from dd_harness.projects.escalations import STEWARD as STEWARD_SIDE
from dd_harness.role_events import names, team_key
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

COLLEAGUE = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="A Colleague")
STEWARD = Principal(principal_id="https://orcid.org/0000-0001-5000-0007", name="A Steward")
OTHER_STEWARD = Principal(principal_id="https://orcid.org/0000-0001-5109-3700", name="Another")
LIBRARY = {
    "id": "library-rdm",
    "name": "Library Research Data Team",
    "members": [STEWARD.principal_id],
}
FACULTY = {"id": "faculty", "name": "Faculty Data Team", "members": [OTHER_STEWARD.principal_id]}
RUN = "019a0000-0000-7000-8000-000000000001"


def profile(*teams: dict[str, Any]) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    if teams:
        data["stewardship"] = {"teams": list(teams)}
    return Profile.from_mapping(data, source="test", digest="0" * 64)


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


def no_runs(invocation_id: str) -> None:
    return None


def runs(project_id: str, status: str, reason_code: str | None = None) -> Any:
    envelope = {
        "invocation_id": RUN,
        "project_id": project_id,
        "agent_id": "advisor.metadata",
        "outcome": {"status": status, **({"reason_code": reason_code} if reason_code else {})},
    }
    return lambda invocation_id: envelope if invocation_id == RUN else None


def open_one(
    projects: ProjectStore,
    project_id: str,
    found: Profile,
    *,
    by: Principal = TEST_PRINCIPAL,
    team_id: str | None = None,
    origin: dict[str, Any] | None = None,
    envelope_of: Any = no_runs,
) -> dict[str, Any]:
    return escalation_api.open_escalation(
        projects,
        found,
        project_id,
        Confirmed(
            origin=origin or {"kind": "researcher"},
            note="Can I share the interview transcripts?",
            scope_shared=["The project's title", "Its recent conversation"],
            team_id=team_id,
        ),
        envelope_of,
        acted_for=by,
        caused_by="test",
    )


def make(
    projects: ProjectStore,
    project_id: str,
    found: Profile,
    escalation: dict[str, Any],
    move: str,
    note: str | None = "A note",
    *,
    by: Principal = STEWARD,
) -> dict[str, Any]:
    return escalation_api.move(
        projects,
        found,
        project_id,
        Requested(escalation["escalation_id"], move, note),
        as_steward=by not in (TEST_PRINCIPAL, COLLEAGUE),
        acted_for=by,
        caused_by="test",
    )


# --- the record ------------------------------------------------------------------------------


def test_an_escalation_is_an_event_in_the_projects_log(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY)
    opened = open_one(projects, project_id, found)
    assert opened["state"] == "open"
    assert opened["team_id"] == "library-rdm"
    assert opened["team_name"] == "Library Research Data Team"
    assert opened["origin"] == {"kind": "researcher"}
    assert opened["scope_shared"] == ["The project's title", "Its recent conversation"]
    assert opened["opened_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    (event,) = [e for e in projects.events(project_id) if e["event"] == ESCALATION_OPENED]
    assert event["event_id"] == opened["escalation_id"]
    # The team index finds it: a steward team's queue is one read.
    assert names(event) == team_key("library-rdm")
    assert project_id in projects.logs_naming(team_key("library-rdm"))


@pytest.mark.parametrize(
    ("path", "state"),
    [
        (["take"], "taken"),
        (["take", "release"], "open"),
        (["take", "wait"], "waiting_for_researcher"),
        (["take", "wait", "reply"], "taken"),
        (["take", "resolve"], "resolved"),
        (["take", "wait", "resolve"], "resolved"),
        (["take", "hand_back"], "handed_back"),
        (["take", "wait", "hand_back"], "handed_back"),
        (["withdraw"], "withdrawn"),
        (["take", "withdraw"], "withdrawn"),
        (["take", "wait", "withdraw"], "withdrawn"),
        (["take", "resolve", "reopen"], "open"),
        (["take", "hand_back", "reopen"], "open"),
    ],
)
def test_each_move_the_state_table_lists_is_made(
    projects: ProjectStore, project_id: str, path: list[str], state: str
) -> None:
    found = profile(LIBRARY)
    escalation = open_one(projects, project_id, found)
    for move in path:
        by = STEWARD if MOVES[move].side == "steward" else TEST_PRINCIPAL
        escalation = make(projects, project_id, found, escalation, move, by=by)
    assert escalation["state"] == state
    assert [h["move"] for h in escalation["history"]] == ["open", *path]
    assert escalations(projects.events(project_id)) == [
        {k: v for k, v in escalation.items() if k not in ("team_name", "permitted_moves")}
    ]


@pytest.mark.parametrize(
    ("path", "refused"),
    [
        ([], "release"),
        ([], "wait"),
        ([], "resolve"),
        ([], "reply"),
        ([], "reopen"),
        (["take"], "take"),
        (["take"], "reply"),
        (["take", "resolve"], "resolve"),
        (["take", "resolve"], "withdraw"),
        (["withdraw"], "reopen"),
        (["withdraw"], "take"),
    ],
)
def test_a_move_the_state_table_does_not_list_is_refused_and_nothing_is_recorded(
    projects: ProjectStore, project_id: str, path: list[str], refused: str
) -> None:
    found = profile(LIBRARY)
    escalation = open_one(projects, project_id, found)
    for move in path:
        by = STEWARD if MOVES[move].side == "steward" else TEST_PRINCIPAL
        escalation = make(projects, project_id, found, escalation, move, by=by)
    before = projects.events(project_id)
    by = STEWARD if MOVES[refused].side == "steward" else TEST_PRINCIPAL
    with pytest.raises(EscalationRefusedError) as raised:
        make(projects, project_id, found, escalation, refused, by=by)
    assert raised.value.refusal is EscalationRefusal.MOVE_NOT_ALLOWED
    assert projects.events(project_id) == before


def test_a_researcher_cannot_make_a_stewards_move_nor_a_steward_a_researchers(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY)
    escalation = open_one(projects, project_id, found)
    with pytest.raises(EscalationRefusedError) as raised:
        make(projects, project_id, found, escalation, "take", by=TEST_PRINCIPAL)
    assert raised.value.refusal is EscalationRefusal.NOT_YOUR_MOVE
    with pytest.raises(EscalationRefusedError) as raised:
        make(projects, project_id, found, escalation, "withdraw", by=STEWARD)
    assert raised.value.refusal is EscalationRefusal.NOT_YOUR_MOVE


def test_a_steward_moves_with_acting_as_steward(projects: ProjectStore, project_id: str) -> None:
    found = profile(LIBRARY)
    escalation = open_one(projects, project_id, found)
    taken = make(projects, project_id, found, escalation, "take")
    assert taken["taken_by"]["principal_id"] == STEWARD.principal_id
    assert taken["history"][-1]["acting_as"] == "steward"
    assert projects.events(project_id)[-1]["acting_as"] == "steward"


def test_a_note_is_required_where_the_table_says(projects: ProjectStore, project_id: str) -> None:
    found = profile(LIBRARY)
    escalation = make(projects, project_id, found, open_one(projects, project_id, found), "take")
    for move in ("wait", "resolve", "hand_back"):
        with pytest.raises(EscalationRefusedError) as raised:
            make(projects, project_id, found, escalation, move, note="  ")
        assert raised.value.refusal is EscalationRefusal.NOTE_REQUIRED
    released = make(projects, project_id, found, escalation, "release", note=None)
    assert released["state"] == "open"
    with pytest.raises(EscalationRefusedError) as raised:
        escalation_api.open_escalation(
            projects,
            found,
            project_id,
            Confirmed(origin={"kind": "researcher"}, note=""),
            no_runs,
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )
    assert raised.value.refusal is EscalationRefusal.NOTE_REQUIRED


def test_reopening_keeps_the_history(projects: ProjectStore, project_id: str) -> None:
    found = profile(LIBRARY)
    escalation = open_one(projects, project_id, found)
    for move in ("take", "resolve"):
        escalation = make(projects, project_id, found, escalation, move)
    reopened = make(
        projects, project_id, found, escalation, "reopen", "Still stuck", by=TEST_PRINCIPAL
    )
    assert reopened["state"] == "open" and reopened["taken_by"] is None
    assert [h["move"] for h in reopened["history"]] == ["open", "take", "resolve", "reopen"]
    assert reopened["history"][2]["note"] == "A note"


# --- sides ---------------------------------------------------------------------------------


def test_a_steward_of_another_team_or_nobody_does_not_reach_the_escalation(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY, FACULTY)
    escalation = open_one(projects, project_id, found, team_id="library-rdm")
    stranger = Principal(principal_id="https://orcid.org/0000-0002-9079-593X", name="Stranger")
    for who in (OTHER_STEWARD, stranger):
        with pytest.raises(UnknownProjectError):
            make(projects, project_id, found, escalation, "take", by=who)


def test_a_steward_who_is_a_member_of_the_project_acts_as_a_member(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile({**LIBRARY, "members": [STEWARD.principal_id, COLLEAGUE.principal_id]})
    escalation = open_one(projects, project_id, found)
    with pytest.raises(EscalationRefusedError) as raised:
        escalation_api.move(
            projects,
            found,
            project_id,
            Requested(escalation["escalation_id"], "take"),
            as_steward=True,
            acted_for=COLLEAGUE,
            caused_by="test",
        )
    assert raised.value.refusal is EscalationRefusal.MEMBER_OF_PROJECT
    (row,) = escalation_api.queue(projects, found, COLLEAGUE)
    assert row["member_of_project"] is True
    assert [(m["move"], m["permitted"], m["refusal"]) for m in row["permitted_moves"]] == [
        ("take", False, "member-of-project")
    ]


# --- what each person may do -----------------------------------------------------------------


def moves_of(escalation: dict[str, Any]) -> dict[str, str]:
    """The moves listed as permitted, each with its note rule."""
    return {m["move"]: m["note"] for m in escalation["permitted_moves"] if m["permitted"]}


def test_each_side_is_told_the_moves_the_state_allows(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY)
    opened = open_one(projects, project_id, found)
    assert moves_of(opened) == {"withdraw": "none"}
    (row,) = escalation_api.queue(projects, found, STEWARD)
    assert moves_of(row) == {"take": "none"}
    taken = make(projects, project_id, found, opened, "take")
    assert moves_of(taken) == {
        "release": "optional",
        "wait": "required",
        "resolve": "required",
        "hand_back": "required",
    }
    make(projects, project_id, found, taken, "wait")

    def shown(reader: Principal) -> dict[str, str]:
        (escalation,) = escalation_api.for_project(projects, found, project_id, reader)[
            "escalations"
        ]
        return moves_of(escalation)

    assert shown(COLLEAGUE) == {"reply": "required", "withdraw": "none"}
    assert shown(STEWARD) == {"resolve": "required", "hand_back": "required"}
    assert shown(OTHER_STEWARD) == {}


@pytest.mark.parametrize(
    "state", ["open", "taken", "waiting_for_researcher", "resolved", "handed_back", "withdrawn"]
)
@pytest.mark.parametrize("side", [RESEARCHER, STEWARD_SIDE])
def test_every_listed_move_is_one_the_rules_allow(state: str, side: Side) -> None:
    for listed in escalation_api.permitted_moves(side, {"state": state}):
        step = MOVES[listed["move"]]
        assert step.side == side and state in step.starts and listed["note"] == step.note


def test_someone_who_is_not_a_member_cannot_open_one(
    projects: ProjectStore, project_id: str
) -> None:
    with pytest.raises(UnknownProjectError):
        open_one(projects, project_id, profile(LIBRARY), by=STEWARD)


# --- routing ---------------------------------------------------------------------------------


def test_with_one_team_an_escalation_goes_to_it(projects: ProjectStore, project_id: str) -> None:
    assert open_one(projects, project_id, profile(LIBRARY))["team_id"] == "library-rdm"


def test_with_no_team_it_is_refused_and_the_project_says_so(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile()
    with pytest.raises(EscalationRefusedError) as raised:
        open_one(projects, project_id, found)
    assert raised.value.refusal is EscalationRefusal.NO_STEWARD_TEAM
    shown = escalation_api.for_project(projects, found, project_id, TEST_PRINCIPAL)
    assert shown["routes_to"] is None and shown["unrouted"] == "no-steward-team"
    assert shown["teams"] == [] and shown["escalations"] == []


def test_with_several_teams_the_sender_picks_one_and_an_owners_pick_is_the_support_team(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY, FACULTY)
    with pytest.raises(EscalationRefusedError) as raised:
        open_one(projects, project_id, found)
    assert raised.value.refusal is EscalationRefusal.TEAM_REQUIRED
    with pytest.raises(EscalationRefusedError) as raised:
        open_one(projects, project_id, found, team_id="nowhere")
    assert raised.value.refusal is EscalationRefusal.UNKNOWN_TEAM
    # A member's pick routes their escalation and does not choose for the project.
    assert (
        open_one(projects, project_id, found, by=COLLEAGUE, team_id="faculty")["team_id"]
        == "faculty"
    )
    assert support_team(projects.events(project_id)) is None
    # An owner's pick is also the project's support team, which the next escalation goes to.
    open_one(projects, project_id, found, team_id="library-rdm")
    assert support_team(projects.events(project_id)) == "library-rdm"
    assert open_one(projects, project_id, found, by=COLLEAGUE)["team_id"] == "library-rdm"
    assert (
        escalation_api.for_project(projects, found, project_id, TEST_PRINCIPAL)["routes_to"]
        == "library-rdm"
    )


def test_an_owner_chooses_the_support_team_from_the_profiles_teams(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY, FACULTY)
    escalation_api.choose_support_team(
        projects, found, project_id, "faculty", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    escalation_api.choose_support_team(
        projects, found, project_id, "faculty", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    chosen = [e for e in projects.events(project_id) if e["event"] == SUPPORT_TEAM_CHOSEN]
    assert len(chosen) == 1 and names(chosen[0]) == team_key("faculty")
    with pytest.raises(EscalationRefusedError) as raised:
        escalation_api.choose_support_team(
            projects, found, project_id, "nowhere", acted_for=TEST_PRINCIPAL, caused_by="test"
        )
    assert raised.value.refusal is EscalationRefusal.UNKNOWN_TEAM


# --- origin ----------------------------------------------------------------------------------


def test_a_confirmed_referral_opens_exactly_one_escalation_linked_to_its_run(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY)
    referred = runs(project_id, "referred", "policy_requires_approval")
    origin = {"kind": "policy_gate", "invocation_id": RUN}
    opened = open_one(projects, project_id, found, origin=origin, envelope_of=referred)
    assert opened["origin"] == {**origin, "agent_id": "advisor.metadata"}
    with pytest.raises(EscalationRefusedError) as raised:
        open_one(projects, project_id, found, origin=origin, envelope_of=referred)
    assert raised.value.refusal is EscalationRefusal.ALREADY_ESCALATED
    # Once withdrawn, the run may be sent again.
    make(projects, project_id, found, opened, "withdraw", by=TEST_PRINCIPAL)
    assert (
        open_one(projects, project_id, found, origin=origin, envelope_of=referred)["state"]
        == "open"
    )


@pytest.mark.parametrize(
    ("origin", "status", "reason_code"),
    [
        ({"kind": "policy_gate", "invocation_id": RUN}, "succeeded", None),
        ({"kind": "policy_gate", "invocation_id": RUN}, "referred", "insufficient_evidence"),
        ({"kind": "agent", "invocation_id": RUN}, "succeeded", None),
        (
            {"kind": "agent", "invocation_id": "019a0000-0000-7000-8000-00000000ffff"},
            "abstained",
            None,
        ),
        ({"kind": "researcher", "invocation_id": RUN}, "referred", None),
        ({"kind": "the dean"}, "referred", None),
    ],
)
def test_an_origin_that_does_not_match_its_run_is_refused(
    projects: ProjectStore,
    project_id: str,
    origin: dict[str, Any],
    status: str,
    reason_code: str | None,
) -> None:
    with pytest.raises(EscalationRefusedError) as raised:
        open_one(
            projects,
            project_id,
            profile(LIBRARY),
            origin=origin,
            envelope_of=runs(project_id, status, reason_code),
        )
    assert raised.value.refusal is EscalationRefusal.ORIGIN_MISMATCH


def test_a_run_of_another_project_is_not_an_origin(projects: ProjectStore, project_id: str) -> None:
    other = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    with pytest.raises(EscalationRefusedError) as raised:
        open_one(
            projects,
            project_id,
            profile(LIBRARY),
            origin={"kind": "agent", "invocation_id": RUN},
            envelope_of=runs(other, "abstained"),
        )
    assert raised.value.refusal is EscalationRefusal.ORIGIN_MISMATCH


# --- the queue -------------------------------------------------------------------------------


def test_a_steward_sees_only_their_teams_live_escalations(
    projects: ProjectStore, project_id: str
) -> None:
    found = profile(LIBRARY, FACULTY)
    projects.rename(
        project_id, "Soil survey", source="researcher", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    first = open_one(projects, project_id, found, team_id="library-rdm")
    open_one(projects, project_id, found, by=COLLEAGUE, team_id="faculty")
    elsewhere = projects.create(acted_for=COLLEAGUE, caused_by="test")
    open_one(projects, elsewhere, found, by=COLLEAGUE, team_id="faculty")
    queued = escalation_api.queue(projects, found, STEWARD)
    assert [row["escalation_id"] for row in queued] == [first["escalation_id"]]
    assert queued[0]["project_id"] == project_id
    assert queued[0]["project_title"] == "Soil survey"
    assert queued[0]["member_of_project"] is False
    assert {r["project_id"] for r in escalation_api.queue(projects, found, OTHER_STEWARD)} == {
        project_id,
        elsewhere,
    }
    # Finished escalations leave the default queue, and a filter by state finds them.
    make(projects, project_id, found, make(projects, project_id, found, first, "take"), "resolve")
    assert escalation_api.queue(projects, found, STEWARD) == []
    resolved = escalation_api.queue(projects, found, STEWARD, ["resolved"])
    assert [r["escalation_id"] for r in resolved] == [first["escalation_id"]]
    # A researcher in no team has no queue.
    assert escalation_api.queue(projects, found, TEST_PRINCIPAL) == []


def test_a_deleted_project_leaves_the_queue(projects: ProjectStore, project_id: str) -> None:
    found = profile(LIBRARY)
    open_one(projects, project_id, found)
    projects.delete(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert escalation_api.queue(projects, found, STEWARD) == []


def test_the_rules_alone_refuse_an_overlong_note(projects: ProjectStore, project_id: str) -> None:
    with pytest.raises(EscalationRefusedError) as raised:
        projects.open_escalation(
            project_id,
            NewEscalation(team_id="library-rdm", origin={"kind": "researcher"}, note="x" * 5000),
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )
    assert raised.value.refusal is EscalationRefusal.NOTE_TOO_LONG
