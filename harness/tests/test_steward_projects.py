"""A data steward's list of the projects they may see (docs/specs/stewardship.md, invariant 3;
#232).

The steward path decides which projects are listed, from the profile's visibility; listing one is
a read of it, recorded as opening it is; and each row says what awaits a person's review there
and what the steward may do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from test_escalations import COLLEAGUE, FACULTY, LIBRARY, OTHER_STEWARD, STEWARD, make, open_one
from test_escalations import profile as with_teams

from dd_harness import steward_api, steward_projects
from dd_harness.listing import Page, Readable, run_summary
from dd_harness.policy import Profile
from dd_harness.projects import STEWARD_VIEWED, ProjectStore
from dd_harness.steward_storage import GateDecision
from dd_harness.storage import RunStorage
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

pytestmark = pytest.mark.requirement("C13.6")

ESCALATED = with_teams(LIBRARY, FACULTY)


def scoped(*teams: dict[str, Any]) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data["stewardship"] = {"teams": list(teams), "visibility": "scope"}
    return Profile.from_mapping(data, source="test", digest="0" * 64)


class Runs:
    """The run store's listing, over envelopes kept in the order stored."""

    def __init__(self, *envelopes: dict[str, Any]) -> None:
        self.envelopes = list(envelopes)

    def list_runs(
        self, *, readable: Readable | None = None, limit: int, before: str | None = None
    ) -> Page:
        found = [e for e in reversed(self.envelopes) if readable is None or readable.includes(e)]
        return Page([run_summary(e) for e in found[:limit]])


def envelope(
    n: int, project_id: str | None, status: str, reason: str | None = None
) -> dict[str, Any]:
    outcome = {"status": status, **({"reason_code": reason} if reason else {})}
    return {
        "invocation_id": f"019a0000-0000-7000-8000-{n:012d}",
        "agent_id": "advisor.metadata",
        "project_id": project_id,
        "outcome": outcome,
        "completed_at": f"2026-11-0{n}T10:00:00Z",
        "acting_for": {"principal_id": TEST_PRINCIPAL.principal_id, "name": "Researcher"},
    }


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def new_project(projects: ProjectStore, by: Principal = TEST_PRINCIPAL) -> str:
    return projects.create(acted_for=by, caused_by="test")


def listed(
    projects: ProjectStore,
    found: Profile,
    steward: Principal = STEWARD,
    runs: Runs | None = None,
    **paging: Any,
) -> Page:
    return steward_projects.listing(
        projects,
        cast(RunStorage, runs or Runs()),
        found,
        steward,
        limit=paging.pop("limit", 50),
        caused_by="test",
        **paging,
    )


def ids(page: Page) -> list[str]:
    return [row["project_id"] for row in page.items]


def views(projects: ProjectStore, project_id: str) -> list[dict[str, Any]]:
    return [e for e in projects.events(project_id) if e["event"] == STEWARD_VIEWED]


def test_by_default_only_projects_escalated_to_the_stewards_team_are_listed(
    projects: ProjectStore,
) -> None:
    escalated = new_project(projects)
    open_one(projects, escalated, ESCALATED, team_id="library-rdm")
    elsewhere = new_project(projects)
    open_one(projects, elsewhere, ESCALATED, team_id="faculty")
    supported = new_project(projects)
    projects.choose_support_team(
        supported, "library-rdm", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    new_project(projects)

    assert ids(listed(projects, ESCALATED)) == [escalated]
    assert ids(listed(projects, ESCALATED, OTHER_STEWARD)) == [elsewhere]
    assert ids(listed(projects, ESCALATED, TEST_PRINCIPAL)) == []


def test_with_scope_the_projects_that_chose_the_team_are_listed_too(
    projects: ProjectStore,
) -> None:
    found = scoped(LIBRARY, FACULTY)
    supported = new_project(projects)
    projects.choose_support_team(
        supported, "library-rdm", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    (row,) = listed(projects, found).items
    assert row["project_id"] == supported
    assert row["access"]["escalated"] is False
    assert [t["team_id"] for t in row["access"]["teams"]] == ["library-rdm"]
    permitted = {a["action"]: a["permitted"] for a in row["permitted_actions"]["actions"]}
    assert row["permitted_actions"]["acting_as"] == "steward"
    assert permitted["read"] is True
    assert permitted["pause"] is False


def test_a_project_closed_deleted_or_joined_is_not_listed(projects: ProjectStore) -> None:
    resolved = new_project(projects)
    escalation = open_one(projects, resolved, ESCALATED, team_id="library-rdm")
    make(projects, resolved, ESCALATED, escalation, "take")
    make(projects, resolved, ESCALATED, escalation, "resolve")
    deleted = new_project(projects)
    open_one(projects, deleted, ESCALATED, team_id="library-rdm")
    projects.delete(deleted, acted_for=TEST_PRINCIPAL, caused_by="test")
    joined = new_project(projects)
    projects.add_member(joined, STEWARD.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    open_one(projects, joined, ESCALATED, team_id="library-rdm")

    assert ids(listed(projects, ESCALATED)) == []


def test_a_pause_the_team_holds_keeps_the_project_listed(projects: ProjectStore) -> None:
    project_id = new_project(projects)
    escalation = open_one(projects, project_id, ESCALATED, team_id="library-rdm")
    steward_api.pause(
        projects, ESCALATED, project_id, "Checking consent", acted_for=STEWARD, caused_by="test"
    )
    make(projects, project_id, ESCALATED, escalation, "take")
    make(projects, project_id, ESCALATED, escalation, "resolve")

    (row,) = listed(projects, ESCALATED).items
    assert row["access"]["holds_pause"] is True
    assert row["paused"] is not None
    assert row["escalations"] == []


def test_a_project_reached_through_two_teams_is_listed_once(projects: ProjectStore) -> None:
    both = with_teams(LIBRARY, {**FACULTY, "members": [STEWARD.principal_id]})
    project_id = new_project(projects)
    open_one(projects, project_id, both, team_id="library-rdm")
    projects.choose_support_team(project_id, "faculty", acted_for=TEST_PRINCIPAL, caused_by="test")
    open_one(projects, project_id, both, team_id="faculty")

    (row,) = listed(projects, both).items
    assert {t["team_id"] for t in row["access"]["teams"]} == {"library-rdm", "faculty"}
    assert len(row["escalations"]) == 2


def test_listing_records_one_view_a_day_of_each_project_on_the_page(
    projects: ProjectStore,
) -> None:
    first, second = new_project(projects), new_project(projects)
    for project_id in (first, second):
        open_one(projects, project_id, ESCALATED, team_id="library-rdm")

    page = listed(projects, ESCALATED, limit=1)
    assert ids(page) == [second]
    assert page.next == second
    assert len(views(projects, second)) == 1
    assert views(projects, first) == []

    listed(projects, ESCALATED, limit=1)
    assert len(views(projects, second)) == 1
    (view,) = views(projects, second)
    assert view["acted_for"]["principal_id"] == STEWARD.principal_id

    rest = listed(projects, ESCALATED, limit=1, before=second)
    assert ids(rest) == [first]
    assert rest.next is None
    assert len(views(projects, first)) == 1
    assert listed(projects, ESCALATED, before="not-a-project").items == []


def test_each_row_shows_its_latest_runs_and_what_awaits_review(projects: ProjectStore) -> None:
    project_id = new_project(projects)
    other = new_project(projects, COLLEAGUE)
    open_one(projects, project_id, ESCALATED, team_id="library-rdm")
    cleared = envelope(1, project_id, "referred", "policy_requires_approval")
    waiting = envelope(2, project_id, "referred", "policy_requires_approval")
    runs = Runs(
        cleared,
        waiting,
        envelope(3, project_id, "abstained", "insufficient_input"),
        envelope(4, other, "succeeded"),
        envelope(5, None, "succeeded"),
    )
    steward_api.decide_gate(
        projects,
        ESCALATED,
        project_id,
        GateDecision(cleared["invocation_id"], "cleared", "Within policy"),
        lambda invocation_id: cleared if invocation_id == cleared["invocation_id"] else None,
        acted_for=STEWARD,
        caused_by="test",
    )

    (row,) = listed(projects, ESCALATED, runs=runs).items
    assert [r["status"] for r in row["recent_runs"]] == ["abstained", "referred", "referred"]
    assert {r["project_id"] for r in row["recent_runs"]} == {project_id}
    assert row["awaiting_review"]["referred_runs"] == [waiting["invocation_id"]]
    assert row["owners"] == [TEST_PRINCIPAL.principal_id]
    assert row["escalations"][0]["state"] == "open"


def test_a_person_in_no_team_sees_no_projects(projects: ProjectStore) -> None:
    project_id = new_project(projects)
    open_one(projects, project_id, ESCALATED, team_id="library-rdm")
    assert listed(projects, with_teams(), STEWARD).items == []
    assert views(projects, project_id) == []
