"""The access check (docs/specs/projects.md, invariants 16 and 17): who may do what in a project,
read from its log."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness.project_access import Action, Role, allowed, may, role_of, roles
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL
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
