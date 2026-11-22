"""`ProjectStorage` checks of a project's escalations to a data steward
(docs/specs/stewardship.md, invariant 4): a steward team's projects are found through the same
index as a person's, so a team's queue is one read in every backend, and an escalation's moves are
kept in order. `dd_harness.testing.member_storage` runs them with the listing checks."""

from __future__ import annotations

from collections.abc import Callable

from dd_harness.projects.escalations import NewEscalation, escalations
from dd_harness.role_events import team_key
from dd_harness.storage import ProjectStorage
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

type MakeProjectStorage = Callable[[str], ProjectStorage]

STEWARD = Principal(principal_id="https://orcid.org/0000-0001-5000-0007", name="A Steward")


def check_a_teams_projects_are_found_through_the_index(make: MakeProjectStorage) -> None:
    """The projects an escalation or a support-team choice routes to a team are found by its team
    key, in the order created, by any store over the record; the others are not."""
    store = make("projects")
    first = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    untouched = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    second = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    store.choose_support_team(second, "library-rdm", acted_for=TEST_PRINCIPAL, caused_by="check")
    opened = store.open_escalation(
        first,
        NewEscalation(team_id="library-rdm", origin={"kind": "researcher"}, note="Help, please"),
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    store.move_escalation(
        first,
        opened["escalation_id"],
        "take",
        side="steward",
        acted_for=STEWARD,
        caused_by="check",
    )
    again = make("projects")
    assert again.projects_naming(team_key("library-rdm")) == [first, second]
    assert untouched not in again.logs_naming(team_key("library-rdm"))
    assert again.projects_naming(team_key("faculty")) == []
    (found,) = escalations(again.logs_naming(team_key("library-rdm"))[first])
    assert found["state"] == "taken"
    assert found["taken_by"]["principal_id"] == STEWARD.principal_id


ESCALATION_STORAGE_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "a team's projects are found through the index": (
        check_a_teams_projects_are_found_through_the_index
    ),
}
