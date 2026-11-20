"""The access check (docs/specs/projects.md, invariants 16 and 17): who may do what in a project,
read from its log."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness.project_access import (
    Action,
    Role,
    allowed,
    deleted_projects,
    hidden_in,
    may,
    readable_logs,
    readable_projects,
    role_of,
    roles,
)
from dd_harness.project_files import FileProjectLog
from dd_harness.projects import Projects, ProjectStore, UnknownProjectError
from dd_harness.role_events import names
from dd_harness.testing import TEST_PRINCIPAL, CountingLog
from dd_sdk.contract.models import Principal

SOMEONE_ELSE = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def test_the_creator_of_a_project_is_its_owner(projects: ProjectStore) -> None:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert roles(projects.events(project_id)) == {TEST_PRINCIPAL.principal_id: Role.OWNER}
    assert role_of(projects, project_id, TEST_PRINCIPAL) is Role.OWNER


@pytest.mark.parametrize("action", list(Action))
def test_an_owner_may_do_anything_and_a_non_member_nothing(action: Action) -> None:
    assert allowed(Role.OWNER, action)
    assert not allowed(None, action)


def test_a_member_may_read_and_contribute_but_not_decide_or_manage() -> None:
    assert {a for a in Action if allowed(Role.MEMBER, a)} == {Action.READ, Action.CONTRIBUTE}


def test_someone_who_did_not_create_a_project_may_do_nothing_in_it(
    projects: ProjectStore,
) -> None:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert role_of(projects, project_id, SOMEONE_ELSE) is None
    assert not any(may(projects, project_id, SOMEONE_ELSE, a) for a in Action)


@pytest.mark.parametrize(
    "project_id", ["01900000-0000-7000-8000-000000000000", "../elsewhere", "", "not-an-id"]
)
def test_a_project_that_does_not_exist_gives_no_one_a_role(
    projects: ProjectStore, project_id: str
) -> None:
    assert role_of(projects, project_id, TEST_PRINCIPAL) is None
    assert not may(projects, project_id, TEST_PRINCIPAL, Action.READ)


def test_only_the_creation_of_a_project_names_whose_role_it_may_change(
    projects: ProjectStore,
) -> None:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.start_conversation(project_id, acted_for=SOMEONE_ELSE, caused_by="test")
    created, started = projects.events(project_id)
    assert names(created) == TEST_PRINCIPAL.principal_id
    assert names(started) is None


def test_a_person_reads_the_projects_they_created_and_no_others(projects: ProjectStore) -> None:
    mine = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    theirs = projects.create(acted_for=SOMEONE_ELSE, caused_by="test")
    assert readable_projects(projects, TEST_PRINCIPAL) == [mine]
    assert readable_projects(projects, SOMEONE_ELSE) == [theirs]


def test_a_deleted_project_is_hidden_from_all_but_its_owner(projects: ProjectStore) -> None:
    """Docs/specs/projects.md, invariant 23."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.delete(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert readable_projects(projects, TEST_PRINCIPAL) == []
    assert deleted_projects(projects, TEST_PRINCIPAL) == [project_id]
    assert role_of(projects, project_id, TEST_PRINCIPAL) is Role.OWNER
    assert may(projects, project_id, TEST_PRINCIPAL, Action.MANAGE)
    assert role_of(projects, project_id, SOMEONE_ELSE) is None
    assert deleted_projects(projects, SOMEONE_ELSE) == []


def _counted(root: Path) -> tuple[Projects, CountingLog]:
    log = CountingLog(FileProjectLog(root))
    return Projects(log.as_log()), log


@pytest.mark.parametrize("count", [1, 20])
def test_deciding_what_a_person_may_read_is_one_read_whatever_their_projects(
    tmp_path: Path, count: int
) -> None:
    """Issue #1257: the projects a person may read, their deleted projects and their deleted
    conversations are each decided from one read of the store, not one per project."""
    projects, log = _counted(tmp_path / "projects")
    mine = [projects.create(acted_for=TEST_PRINCIPAL, caused_by="test") for _ in range(count)]
    conversation_id = projects.start_conversation(
        mine[0], acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.delete_conversation(
        mine[0], conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    gone = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.delete(gone, acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.create(acted_for=SOMEONE_ELSE, caused_by="test")
    log.calls.clear()
    logs = readable_logs(projects, TEST_PRINCIPAL)
    assert list(logs) == readable_projects(projects, TEST_PRINCIPAL) == mine
    assert hidden_in(logs.values()) == {conversation_id}
    assert deleted_projects(projects, TEST_PRINCIPAL) == [gone]
    assert log.calls == {"logs_naming": 3}


def test_reading_a_projects_log_asks_nothing_else(tmp_path: Path) -> None:
    """A read of a project's events is one read: no `exists` before it (#1257). An unknown or
    malformed project still raises."""
    projects, log = _counted(tmp_path / "projects")
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    log.calls.clear()
    projects.events(project_id)
    assert log.calls == {"events": 1}
    for unknown in ("01900000-0000-7000-8000-000000000000", "../elsewhere", ""):
        with pytest.raises(UnknownProjectError):
            projects.events(unknown)
