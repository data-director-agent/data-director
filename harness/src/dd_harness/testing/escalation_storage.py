"""`ProjectStorage` checks of a project's escalations to a data steward
(docs/specs/stewardship.md, invariant 4): a steward team's projects are found through the same
index as a person's, so a team's queue is one read in every backend, and an escalation's moves are
kept in order. `dd_harness.testing.member_storage` runs them with the listing checks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from dd_harness.projects.escalations import NewEscalation, escalations
from dd_harness.projects.stewarding import pause_of
from dd_harness.role_events import team_key
from dd_harness.storage import ProjectStorage
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal, now

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


def check_a_pause_keeps_the_project_in_its_teams_index(make: MakeProjectStorage) -> None:
    """A pause names the team that holds it, so the team finds the project through its index
    once the escalation is withdrawn, until it lifts the pause (docs/specs/stewardship.md,
    invariant 8)."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    store.pause(project_id, "faculty", "Checking consent", acted_for=STEWARD, caused_by="check")
    again = make("projects")
    assert again.projects_naming(team_key("faculty")) == [project_id]
    assert pause_of(again.events(project_id)) is not None


def check_an_escalation_sent_again_stays_open_and_once(make: MakeProjectStorage) -> None:
    """An `open` escalation last routed before the time given is sent to its team again, and
    one routed since is not, as any store over the record reads it; a taken one is not
    (docs/specs/stewardship.md, invariant 13)."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    opened = store.open_escalation(
        project_id,
        NewEscalation(team_id="library-rdm", origin={"kind": "researcher"}, note="Help, please"),
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    later = now() + timedelta(days=1)
    escalation_id = opened["escalation_id"]
    again = store.reroute_escalation(
        project_id, escalation_id, routed_before=later, acted_for=STEWARD, caused_by="check"
    )
    assert again is not None and again["state"] == "open"
    assert again["history"][-1]["move"] == "reroute"
    # Due only if last routed before the time given: not again for a time before this routing.
    routed = datetime.fromisoformat(again["routed_at"])
    assert (
        store.reroute_escalation(
            project_id, escalation_id, routed_before=routed, acted_for=STEWARD, caused_by="check"
        )
        is None
    )
    store.move_escalation(
        project_id, escalation_id, "take", side="steward", acted_for=STEWARD, caused_by="check"
    )
    far = now() + timedelta(days=30)
    assert (
        store.reroute_escalation(
            project_id, escalation_id, routed_before=far, acted_for=STEWARD, caused_by="check"
        )
        is None
    )
    (found,) = escalations(make("projects").events(project_id))
    assert [entry["move"] for entry in found["history"]] == ["open", "reroute", "take"]


ESCALATION_STORAGE_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "a team's projects are found through the index": (
        check_a_teams_projects_are_found_through_the_index
    ),
    "a pause keeps the project in its team's index": (
        check_a_pause_keeps_the_project_in_its_teams_index
    ),
    "an escalation sent again stays open, and is sent once": (
        check_an_escalation_sent_again_stays_open_and_once
    ),
}
