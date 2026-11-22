"""A data steward's interventions in a project, checked by policy and recorded
(docs/specs/stewardship.md, invariants 2, 3 and 6 to 8; #374).

A steward reaches a project by the steward path, never as a member, and only while the profile's
visibility allows it. Each action is checked against the closed list before it happens, and
recorded naming the steward; so is each read. A pause stops every run in the project that is not
`advise`, and every deposit, until a steward of the team that holds it lifts it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from test_escalations import (
    COLLEAGUE,
    FACULTY,
    LIBRARY,
    OTHER_STEWARD,
    RUN,
    STEWARD,
    make,
    open_one,
    profile,
    runs,
)

from dd_harness import project_access, steward_api
from dd_harness.deposit_api import DepositRefusedError, approve_and_deposit
from dd_harness.deposit_api import Refusal as DepositRefusal
from dd_harness.policy import Profile
from dd_harness.projects import (
    GATE_CLEARED,
    PROJECT_PAUSED,
    PROJECT_RESUMED,
    STEWARD_MESSAGE,
    STEWARD_VIEWED,
    ProjectStore,
    StewardRefusal,
    StewardRefusedError,
    UnknownProjectError,
)
from dd_harness.projects.stewarding import pause_of
from dd_harness.role_events import team_key
from dd_harness.steward_access import ACTIONS, steward_of
from dd_harness.steward_storage import GateDecision, ProposedEdit
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL, DocumentStub, make_conductor, request
from dd_sdk.contract.models import (
    DocumentKind,
    DraftRequest,
    OutcomeStatus,
    Principal,
    ReasonCode,
)

pytestmark = pytest.mark.requirement("C13.6")

LIBRARY_ONLY = profile(LIBRARY, FACULTY)


def scoped(*teams: dict[str, Any]) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data["stewardship"] = {"teams": list(teams), "visibility": "scope"}
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


@pytest.fixture
def escalated(projects: ProjectStore, project_id: str) -> dict[str, Any]:
    return open_one(projects, project_id, LIBRARY_ONLY, team_id="library-rdm")


def stewards_events(projects: ProjectStore, project_id: str, kind: str) -> list[dict[str, Any]]:
    return [e for e in projects.events(project_id) if e["event"] == kind]


def act(projects: ProjectStore, project_id: str, action: str, by: Principal, found: Profile) -> Any:
    """Take the steward's `action` as `by`, with what it needs."""
    common: dict[str, Any] = {"acted_for": by, "caused_by": "test"}
    if action == "read":
        if steward_api.read(projects, found, project_id, by, caused_by="test") is None:
            raise UnknownProjectError(project_id)
        return None
    if action == "message":
        return steward_api.message(projects, found, project_id, "A note", **common)
    if action == "pause":
        return steward_api.pause(projects, found, project_id, "Checking consent", **common)
    if action == "resume":
        return steward_api.resume(projects, found, project_id, "Consent confirmed", **common)
    if action in ("clear_gate", "refuse_gate"):
        decision = GateDecision(
            RUN, "cleared" if action == "clear_gate" else "refused", "Within policy"
        )
        envelope_of = runs(project_id, "referred", "policy_requires_approval")
        return steward_api.decide_gate(projects, found, project_id, decision, envelope_of, **common)
    if action == "propose_edit":
        edit = ProposedEdit("missing", 1, "0" * 64, "text")
        return steward_api.propose_edit(projects, found, project_id, edit, **common)
    assert action == "run"
    return steward_api.reach(projects, found, project_id, by, "run")


@pytest.mark.parametrize("action", [a for a in ACTIONS if a != "read"])
@pytest.mark.parametrize("member", [TEST_PRINCIPAL, COLLEAGUE])
def test_a_researcher_cannot_take_any_stewards_action(
    projects: ProjectStore,
    project_id: str,
    escalated: dict[str, Any],
    member: Principal,
    action: str,
) -> None:
    before = projects.events(project_id)
    with pytest.raises(StewardRefusedError) as refused:
        act(projects, project_id, action, member, LIBRARY_ONLY)
    assert refused.value.refusal is StewardRefusal.MEMBER_OF_PROJECT
    assert projects.events(project_id) == before


def test_a_member_who_is_also_a_steward_acts_as_a_member(
    projects: ProjectStore, project_id: str
) -> None:
    both = profile({**LIBRARY, "members": [STEWARD.principal_id, COLLEAGUE.principal_id]})
    open_one(projects, project_id, both)
    assert steward_of(projects, both, project_id, COLLEAGUE) is None
    with pytest.raises(StewardRefusedError) as refused:
        steward_api.pause(projects, both, project_id, "x", acted_for=COLLEAGUE, caused_by="t")
    assert refused.value.refusal is StewardRefusal.MEMBER_OF_PROJECT


@pytest.mark.parametrize("action", ACTIONS)
def test_a_steward_of_another_team_does_not_reach_the_project(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any], action: str
) -> None:
    before = projects.events(project_id)
    with pytest.raises(UnknownProjectError):
        act(projects, project_id, action, OTHER_STEWARD, LIBRARY_ONLY)
    assert projects.events(project_id) == before


def test_without_an_escalation_a_steward_does_not_reach_the_project(
    projects: ProjectStore, project_id: str
) -> None:
    assert steward_of(projects, LIBRARY_ONLY, project_id, STEWARD) is None
    with pytest.raises(UnknownProjectError):
        act(projects, project_id, "read", STEWARD, LIBRARY_ONLY)


def test_a_closed_escalation_ends_a_stewards_access(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    make(projects, project_id, LIBRARY_ONLY, escalated, "take", None)
    make(projects, project_id, LIBRARY_ONLY, escalated, "resolve", "Done")
    assert steward_of(projects, LIBRARY_ONLY, project_id, STEWARD) is None


@pytest.mark.parametrize("action", [a for a in ACTIONS if a != "read"])
def test_with_scope_a_supporting_steward_may_only_read_until_a_matter_is_escalated(
    projects: ProjectStore, project_id: str, action: str
) -> None:
    found = scoped(LIBRARY, FACULTY)
    projects.choose_support_team(project_id, "library-rdm", acted_for=TEST_PRINCIPAL, caused_by="t")
    act(projects, project_id, "read", STEWARD, found)
    with pytest.raises(StewardRefusedError) as refused:
        act(projects, project_id, action, STEWARD, found)
    assert refused.value.refusal is StewardRefusal.NOT_PERMITTED
    with pytest.raises(UnknownProjectError):
        act(projects, project_id, "read", OTHER_STEWARD, found)


def test_without_scope_a_support_team_does_not_reach_the_project(
    projects: ProjectStore, project_id: str
) -> None:
    projects.choose_support_team(project_id, "library-rdm", acted_for=TEST_PRINCIPAL, caused_by="t")
    assert steward_of(projects, LIBRARY_ONLY, project_id, STEWARD) is None


def test_a_stewards_read_is_recorded_once_a_day(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    for _ in range(3):
        act(projects, project_id, "read", STEWARD, LIBRARY_ONLY)
    (viewed,) = stewards_events(projects, project_id, STEWARD_VIEWED)
    assert viewed["acted_for"]["principal_id"] == STEWARD.principal_id
    assert viewed["acting_as"] == "steward"


def test_a_members_read_is_not_recorded_as_a_stewards(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    assert steward_api.read(projects, LIBRARY_ONLY, project_id, COLLEAGUE, caused_by="t") is None
    assert stewards_events(projects, project_id, STEWARD_VIEWED) == []


@pytest.mark.parametrize(
    ("action", "kind"),
    [("message", STEWARD_MESSAGE), ("pause", PROJECT_PAUSED), ("clear_gate", GATE_CLEARED)],
)
def test_each_stewards_action_is_recorded_naming_the_steward(
    projects: ProjectStore,
    project_id: str,
    escalated: dict[str, Any],
    action: str,
    kind: str,
) -> None:
    act(projects, project_id, action, STEWARD, LIBRARY_ONLY)
    (event,) = stewards_events(projects, project_id, kind)
    assert event["acted_for"]["principal_id"] == STEWARD.principal_id
    assert event["acting_as"] == "steward"


def test_a_stewards_edit_is_a_proposed_version_marked_as_theirs(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    conductor = make_conductor(projects.root.parent / "runs", DocumentStub())
    conductor.projects = projects
    asked = request("stub.document", DraftRequest(document_kind=DocumentKind.README))
    conductor.invoke(asked, acting_for=TEST_PRINCIPAL, in_project=project_id)
    (document,) = projects.documents(project_id)
    latest = document["versions"][-1]
    edit = ProposedEdit(document["document_id"], latest["version"], latest["digest"], "# Edited\n")

    steward_api.propose_edit(
        projects, LIBRARY_ONLY, project_id, edit, acted_for=STEWARD, caused_by="t"
    )

    (document,) = projects.documents(project_id)
    proposed = document["versions"][-1]
    assert proposed["state"] == "proposed"
    assert proposed["acting_as"] == "steward"
    assert proposed["added_by"]["principal_id"] == STEWARD.principal_id


def test_a_gate_decision_needs_a_referral_of_this_project(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    decision = GateDecision(RUN, "cleared", "Within policy")
    with pytest.raises(StewardRefusedError) as refused:
        steward_api.decide_gate(
            projects,
            LIBRARY_ONLY,
            project_id,
            decision,
            runs(project_id, "succeeded"),
            acted_for=STEWARD,
            caused_by="t",
        )
    assert refused.value.refusal is StewardRefusal.NOT_REFERRED
    act(projects, project_id, "clear_gate", STEWARD, LIBRARY_ONLY)
    with pytest.raises(StewardRefusedError) as again:
        act(projects, project_id, "refuse_gate", STEWARD, LIBRARY_ONLY)
    assert again.value.refusal is StewardRefusal.GATE_DECIDED


def test_a_pause_is_lifted_only_by_its_team_and_outlives_the_escalation(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    act(projects, project_id, "pause", STEWARD, LIBRARY_ONLY)
    held = pause_of(projects.events(project_id))
    assert held is not None and held["team_id"] == "library-rdm"
    escalation_api_withdraw(projects, project_id, escalated)
    # The team that holds the pause still finds the project through its index.
    assert project_id in projects.logs_naming(team_key("library-rdm"))

    found = steward_of(projects, LIBRARY_ONLY, project_id, STEWARD)
    assert found is not None and found.refusal("resume") is None
    assert found.refusal("pause") is not None
    with pytest.raises(UnknownProjectError):
        act(projects, project_id, "resume", OTHER_STEWARD, LIBRARY_ONLY)
    act(projects, project_id, "resume", STEWARD, LIBRARY_ONLY)
    assert pause_of(projects.events(project_id)) is None
    assert stewards_events(projects, project_id, PROJECT_RESUMED)
    assert steward_of(projects, LIBRARY_ONLY, project_id, STEWARD) is None


def escalation_api_withdraw(
    projects: ProjectStore, project_id: str, escalation: dict[str, Any]
) -> None:
    make(projects, project_id, LIBRARY_ONLY, escalation, "withdraw", None, by=TEST_PRINCIPAL)


def test_a_project_is_not_paused_twice(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    act(projects, project_id, "pause", STEWARD, LIBRARY_ONLY)
    with pytest.raises(StewardRefusedError) as refused:
        act(projects, project_id, "pause", STEWARD, LIBRARY_ONLY)
    assert refused.value.refusal is StewardRefusal.ALREADY_PAUSED


def test_a_steward_with_an_escalation_may_run_an_agent_in_the_project(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    conductor = make_conductor(projects.root.parent / "runs", DocumentStub())
    conductor.projects = projects
    conductor.profile = LIBRARY_ONLY
    asked = request("stub.document", DraftRequest(document_kind=DocumentKind.README))

    env = conductor.invoke(asked, acting_for=STEWARD, in_project=project_id)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.acting_for.principal_id == STEWARD.principal_id
    with pytest.raises(UnknownProjectError):
        conductor.invoke(
            request("stub.document", DraftRequest(document_kind=DocumentKind.README)),
            acting_for=OTHER_STEWARD,
            in_project=project_id,
        )


class DraftingStub(DocumentStub):
    """A drafter the profile assigns an action class other than `advise`, which needs no
    approval."""

    spec = replace(DocumentStub.spec, action_class="draft")


@pytest.fixture
def drafting_profile(tmp_path: Path) -> Path:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data["agents"]["stub.document"] = "draft"
    data["stewardship"] = {"teams": [LIBRARY]}
    path = tmp_path / "drafting.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_a_paused_project_refuses_a_consequential_run_until_the_pause_is_lifted(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any], drafting_profile: Path
) -> None:
    conductor = make_conductor(
        projects.root.parent / "runs", DraftingStub(), profile=drafting_profile
    )
    conductor.projects = projects
    act(projects, project_id, "pause", STEWARD, LIBRARY_ONLY)

    def draft() -> Any:
        asked = request("stub.document", DraftRequest(document_kind=DocumentKind.README))
        return conductor.invoke(asked, acting_for=TEST_PRINCIPAL, in_project=project_id)

    refused = draft()
    assert refused.outcome.status == OutcomeStatus.REFERRED
    assert refused.outcome.reason_code == ReasonCode.PROJECT_PAUSED
    assert projects.documents(project_id) == []

    act(projects, project_id, "resume", STEWARD, LIBRARY_ONLY)
    assert draft().outcome.status == OutcomeStatus.SUCCEEDED


def test_a_paused_project_still_runs_an_adviser(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    conductor = make_conductor(projects.root.parent / "runs", DocumentStub())
    conductor.projects = projects
    act(projects, project_id, "pause", STEWARD, LIBRARY_ONLY)
    asked = request("stub.document", DraftRequest(document_kind=DocumentKind.README))

    env = conductor.invoke(asked, acting_for=TEST_PRINCIPAL, in_project=project_id)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement


def test_permitted_actions_say_what_each_person_may_do(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    def permitted(principal: Principal) -> dict[str, Any]:
        found = steward_api.permitted_actions(projects, LIBRARY_ONLY, project_id, principal)
        return {row["action"]: row["permitted"] for row in found["actions"]} | {
            "as": found["acting_as"]
        }

    owner, colleague, steward = (permitted(p) for p in (TEST_PRINCIPAL, COLLEAGUE, STEWARD))
    assert owner["as"] == "member" and owner["decide"] and not owner["pause"]
    assert colleague["contribute"] and not colleague["decide"] and not colleague["message"]
    assert steward["as"] == "steward" and steward["pause"] and steward["read"]
    assert not steward["contribute"] and not steward["decide"] and not steward["resume"]
    with pytest.raises(UnknownProjectError):
        steward_api.permitted_actions(projects, LIBRARY_ONLY, project_id, OTHER_STEWARD)
    assert project_access.role_of(projects, project_id, STEWARD) is None


def test_a_paused_project_refuses_a_deposit(
    projects: ProjectStore, project_id: str, escalated: dict[str, Any]
) -> None:
    act(projects, project_id, "pause", STEWARD, LIBRARY_ONLY)
    with pytest.raises(DepositRefusedError) as refused:
        approve_and_deposit(
            projects,
            project_id,
            "0" * 64,
            requirements=cast(Any, None),
            setup=cast(Any, None),
            acted_for=TEST_PRINCIPAL,
            caused_by="t",
        )
    assert refused.value.refusal is DepositRefusal.PAUSED
