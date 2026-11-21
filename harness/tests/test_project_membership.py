"""A project's members and their roles (docs/specs/projects.md, invariants 16, 17 and 19): the
membership events, the rules over them, who may read a project after a change, and the command
line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_harness.project_access import (
    Action,
    Role,
    may,
    may_delete_conversation,
    may_leave,
    may_remove_member,
    readable_projects,
    role_of,
    roles,
)
from dd_harness.projects import (
    MEMBER_ADDED,
    MEMBER_REMOVED,
    MEMBER_ROLE_CHANGED,
    MembershipRefusal,
    MembershipRefusedError,
    ProjectDeletedError,
    ProjectError,
    ProjectStore,
    UnknownProjectError,
    principal_identifier,
)
from dd_harness.role_events import names
from dd_harness.server import main
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

COLLEAGUE = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="A Colleague")
STRANGER = Principal(principal_id="https://orcid.org/0000-0001-5109-3700", name="A Stranger")


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project_id(projects: ProjectStore) -> str:
    return projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")


def test_an_owner_adds_a_member_who_may_then_read_and_contribute(
    projects: ProjectStore, project_id: str
) -> None:
    assert not may(projects, project_id, COLLEAGUE, Action.READ)
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert role_of(projects, project_id, COLLEAGUE) is Role.MEMBER
    assert {a for a in Action if may(projects, project_id, COLLEAGUE, a)} == {
        Action.READ,
        Action.CONTRIBUTE,
    }
    assert readable_projects(projects, COLLEAGUE) == [project_id]
    assert not may(projects, project_id, STRANGER, Action.READ)
    assert readable_projects(projects, STRANGER) == []


def test_membership_events_name_the_member_and_no_name(
    projects: ProjectStore, project_id: str
) -> None:
    projects.add_member(
        project_id, COLLEAGUE.principal_id, "owner", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.change_role(
        project_id, COLLEAGUE.principal_id, "member", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.remove_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    events = projects.events(project_id)[1:]
    assert [e["event"] for e in events] == [MEMBER_ADDED, MEMBER_ROLE_CHANGED, MEMBER_REMOVED]
    for event in events:
        assert event["member_id"] == COLLEAGUE.principal_id
        assert names(event) == COLLEAGUE.principal_id
        assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
        assert COLLEAGUE.name not in json.dumps(event)


def test_members_are_listed_creator_first_with_their_roles(
    projects: ProjectStore, project_id: str
) -> None:
    projects.add_member(
        project_id, STRANGER.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.add_member(
        project_id, COLLEAGUE.principal_id, "owner", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.remove_member(
        project_id, STRANGER.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    members = projects.members(project_id)
    assert [(m["member_id"], m["role"]) for m in members] == [
        (TEST_PRINCIPAL.principal_id, "owner"),
        (COLLEAGUE.principal_id, "owner"),
    ]
    assert all(m["member_since"] for m in members)


def test_a_role_change_takes_effect(projects: ProjectStore, project_id: str) -> None:
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.change_role(
        project_id, COLLEAGUE.principal_id, "owner", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert may(projects, project_id, COLLEAGUE, Action.MANAGE)
    assert may(projects, project_id, COLLEAGUE, Action.DECIDE)


@pytest.mark.parametrize("change", ["remove", "demote"])
def test_the_last_owner_is_never_removed_or_demoted(
    projects: ProjectStore, project_id: str, change: str
) -> None:
    before = projects.events(project_id)
    with pytest.raises(MembershipRefusedError) as refused:
        if change == "remove":
            projects.remove_member(
                project_id, TEST_PRINCIPAL.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
            )
        else:
            projects.add_member(
                project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
            )
            before = projects.events(project_id)
            projects.change_role(
                project_id,
                TEST_PRINCIPAL.principal_id,
                "member",
                acted_for=TEST_PRINCIPAL,
                caused_by="test",
            )
    assert refused.value.refusal is MembershipRefusal.LAST_OWNER
    assert projects.events(project_id) == before
    assert role_of(projects, project_id, TEST_PRINCIPAL) is Role.OWNER


def test_with_a_second_owner_the_first_may_leave(projects: ProjectStore, project_id: str) -> None:
    projects.add_member(
        project_id, COLLEAGUE.principal_id, "owner", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.remove_member(
        project_id, TEST_PRINCIPAL.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert role_of(projects, project_id, TEST_PRINCIPAL) is None
    assert roles(projects.events(project_id)) == {COLLEAGUE.principal_id: Role.OWNER}
    # The creation still names who created the project (invariant 19).
    assert projects.events(project_id)[0]["acted_for"]["principal_id"] == (
        TEST_PRINCIPAL.principal_id
    )


@pytest.mark.parametrize(
    ("change", "refusal"),
    [
        ("add twice", MembershipRefusal.ALREADY_MEMBER),
        ("remove a stranger", MembershipRefusal.NOT_A_MEMBER),
        ("change a stranger", MembershipRefusal.NOT_A_MEMBER),
        ("same role", MembershipRefusal.SAME_ROLE),
    ],
)
def test_a_change_that_changes_nothing_is_refused_and_records_nothing(
    projects: ProjectStore, project_id: str, change: str, refusal: MembershipRefusal
) -> None:
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    before = projects.events(project_id)
    with pytest.raises(MembershipRefusedError) as refused:
        match change:
            case "add twice":
                projects.add_member(
                    project_id,
                    COLLEAGUE.principal_id,
                    "owner",
                    acted_for=TEST_PRINCIPAL,
                    caused_by="test",
                )
            case "remove a stranger":
                projects.remove_member(
                    project_id, STRANGER.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
                )
            case "change a stranger":
                projects.change_role(
                    project_id,
                    STRANGER.principal_id,
                    "owner",
                    acted_for=TEST_PRINCIPAL,
                    caused_by="test",
                )
            case _:
                projects.change_role(
                    project_id,
                    COLLEAGUE.principal_id,
                    "member",
                    acted_for=TEST_PRINCIPAL,
                    caused_by="test",
                )
    assert refused.value.refusal is refusal
    assert projects.events(project_id) == before


@pytest.mark.parametrize(
    ("member_id", "role"),
    [("0000-0002-1694-233X", "member"), (COLLEAGUE.principal_id, "admin")],
)
def test_a_malformed_member_or_role_is_refused(
    projects: ProjectStore, project_id: str, member_id: str, role: str
) -> None:
    with pytest.raises(ProjectError):
        projects.add_member(project_id, member_id, role, acted_for=TEST_PRINCIPAL, caused_by="test")  # type: ignore[arg-type]
    assert len(projects.events(project_id)) == 1


def test_membership_of_a_deleted_or_unknown_project_is_refused(
    projects: ProjectStore, project_id: str
) -> None:
    projects.delete(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    with pytest.raises(ProjectDeletedError):
        projects.add_member(
            project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
        )
    with pytest.raises(UnknownProjectError):
        projects.add_member(
            "01900000-0000-7000-8000-000000000000",
            COLLEAGUE.principal_id,
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )


def test_a_removed_member_loses_access_and_keeps_their_attribution(
    projects: ProjectStore, project_id: str
) -> None:
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    conversation_id = projects.start_conversation(project_id, acted_for=COLLEAGUE, caused_by="t")
    assert may_delete_conversation(projects, project_id, conversation_id, COLLEAGUE)
    projects.remove_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert not any(may(projects, project_id, COLLEAGUE, a) for a in Action)
    assert readable_projects(projects, COLLEAGUE) == []
    assert not may_delete_conversation(projects, project_id, conversation_id, COLLEAGUE)
    started = projects.events(project_id)[2]
    assert started["acted_for"]["principal_id"] == COLLEAGUE.principal_id


def test_a_project_a_member_was_added_to_later_is_listed_where_it_was_created(
    projects: ProjectStore,
) -> None:
    theirs = projects.create(acted_for=COLLEAGUE, caused_by="test")
    shared = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    own = projects.create(acted_for=COLLEAGUE, caused_by="test")
    projects.add_member(shared, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert readable_projects(projects, COLLEAGUE) == [theirs, shared, own]


def test_an_owner_removes_anyone_and_a_member_only_themselves(
    projects: ProjectStore, project_id: str
) -> None:
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.add_member(
        project_id, STRANGER.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert may_remove_member(projects, project_id, TEST_PRINCIPAL, COLLEAGUE.principal_id)
    assert may_remove_member(projects, project_id, COLLEAGUE, COLLEAGUE.principal_id)
    assert not may_remove_member(projects, project_id, COLLEAGUE, STRANGER.principal_id)
    outsider = Principal(principal_id="https://orcid.org/0000-0003-1415-9269", name="Outsider")
    assert not may_remove_member(projects, project_id, outsider, outsider.principal_id)


# --- The command line ----------------------------------------------------------------------------


@pytest.fixture
def operator(monkeypatch: pytest.MonkeyPatch, projects: ProjectStore) -> ProjectStore:
    monkeypatch.setenv("DD_PROJECTS_DIR", str(projects.root))
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    return projects


def test_a_bare_orcid_id_names_its_iri() -> None:
    assert principal_identifier(" 0000-0002-1694-233X ") == COLLEAGUE.principal_id
    assert principal_identifier(COLLEAGUE.principal_id) == COLLEAGUE.principal_id


def test_a_member_may_leave_and_the_last_owner_may_not(
    projects: ProjectStore, project_id: str
) -> None:
    assert not may_leave(projects, project_id, TEST_PRINCIPAL)
    assert not may_leave(projects, project_id, COLLEAGUE)
    projects.add_member(
        project_id, COLLEAGUE.principal_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert may_leave(projects, project_id, COLLEAGUE)
    assert not may_leave(projects, project_id, TEST_PRINCIPAL)
    projects.change_role(
        project_id, COLLEAGUE.principal_id, "owner", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert may_leave(projects, project_id, TEST_PRINCIPAL)


def test_an_operator_who_owns_a_project_manages_its_members_from_the_command_line(
    operator: ProjectStore, project_id: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["project", "member-add", project_id, "0000-0002-1694-233X"]) == 0
    assert main(["project", "member-role", project_id, "0000-0002-1694-233X", "owner"]) == 0
    capsys.readouterr()
    assert main(["project", "members", project_id]) == 0
    listed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(m["member_id"], m["role"]) for m in listed] == [
        (TEST_PRINCIPAL.principal_id, "owner"),
        (COLLEAGUE.principal_id, "owner"),
    ]
    assert main(["project", "member-remove", project_id, COLLEAGUE.principal_id]) == 0
    assert role_of(operator, project_id, COLLEAGUE) is None


def test_an_operator_who_is_not_an_owner_is_refused(operator: ProjectStore) -> None:
    theirs = operator.create(acted_for=COLLEAGUE, caused_by="test")
    with pytest.raises(SystemExit):
        main(["project", "member-add", theirs, STRANGER.principal_id])
    with pytest.raises(SystemExit):
        main(["project", "members", theirs])
    assert len(operator.events(theirs)) == 1
