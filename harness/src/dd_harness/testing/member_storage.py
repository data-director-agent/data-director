"""`ProjectStorage` checks of a project's members (docs/specs/projects.md, invariants 16, 17 and
19): the projects a person may read are those they have a role in, a project someone is added to
later is listed where it was created, and removing them takes it out of their list again.
`dd_harness.testing.storage` runs them with every other check."""

from __future__ import annotations

from collections.abc import Callable

from dd_harness.project_access import readable_projects
from dd_harness.storage import ProjectStorage
from dd_harness.testing.escalation_storage import ESCALATION_STORAGE_CHECKS
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

type MakeProjectStorage = Callable[[str], ProjectStorage]

# An ORCID iD no check gives a role to.
NOBODY = "https://orcid.org/0000-0003-0000-0000"


def check_a_person_reads_the_projects_they_have_a_role_in(make: MakeProjectStorage) -> None:
    """The projects a person may read are the ones they have a role in, the one created first
    first, found by any store over the record and after a restart (storage.md, "Listing")."""
    store = make("projects")
    someone = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
    first = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    theirs = store.create(acted_for=someone, caused_by="check")
    # Acting in a project names no one a member; only membership events do.
    store.start_conversation(theirs, acted_for=TEST_PRINCIPAL, caused_by="check")
    second = make("projects").create(acted_for=TEST_PRINCIPAL, caused_by="check")
    assert readable_projects(store, TEST_PRINCIPAL) == [first, second]
    assert readable_projects(make("projects"), someone) == [theirs]
    # A project someone is added to later is listed where it was created, and leaves their list
    # when they are removed.
    make("projects").add_member(
        first, someone.principal_id, acted_for=TEST_PRINCIPAL, caused_by="check"
    )
    assert readable_projects(make("projects"), someone) == [first, theirs]
    store.remove_member(first, someone.principal_id, acted_for=TEST_PRINCIPAL, caused_by="check")
    assert readable_projects(make("projects"), someone) == [theirs]
    nobody = Principal(principal_id=NOBODY, name="Nobody")
    assert readable_projects(store, nobody) == []


# With the checks of the same index naming a steward team (`dd_harness.role_events.team_key`).
MEMBERSHIP_STORAGE_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "a person reads the projects they have a role in": (
        check_a_person_reads_the_projects_they_have_a_role_in
    ),
    **ESCALATION_STORAGE_CHECKS,
}
