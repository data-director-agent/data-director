"""Deleting and restoring a conversation started in a project (docs/specs/projects.md,
invariants 29 to 31): events in the project's log that hide it and bring it back, removing
nothing, and who may append them."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from dd_harness.project_access import (
    conversation_deleted,
    hidden_conversations,
    may_delete_conversation,
)
from dd_harness.projects import (
    CONVERSATION_DELETED,
    CONVERSATION_RESTORED,
    ConversationDeletedError,
    ProjectDeletedError,
    ProjectStore,
    RestoreRefusedError,
    UnknownConversationError,
)
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal, new_invocation_id

SOMEONE_ELSE = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def started(projects: ProjectStore) -> tuple[str, str]:
    """A project, and a conversation its owner started in it."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    return project_id, projects.start_conversation(
        project_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )


def test_a_deleted_conversation_is_hidden_until_it_is_restored(projects: ProjectStore) -> None:
    project_id, conversation_id = started(projects)
    kept = projects.start_conversation(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    before = projects.events(project_id)

    deleted = projects.delete_conversation(
        project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert deleted["conversation_id"] == conversation_id
    assert deleted["by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    # Nothing is removed: the log only grows.
    events = projects.events(project_id)
    assert events[: len(before)] == before
    assert events[-1]["event"] == CONVERSATION_DELETED
    assert conversation_deleted(projects, project_id, conversation_id)
    assert hidden_conversations(projects, [project_id]) == {conversation_id}
    assert projects.summary(project_id)["conversation_count"] == 1
    (listed,) = projects.deleted_conversations(project_id)
    assert (listed["conversation_id"], listed["started_by"]) == (
        conversation_id,
        TEST_PRINCIPAL.principal_id,
    )
    assert {"at", "by", "restorable_until"} <= set(listed)
    with pytest.raises(ConversationDeletedError):
        projects.delete_conversation(
            project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
        )

    projects.restore_conversation(
        project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert projects.events(project_id)[-1]["event"] == CONVERSATION_RESTORED
    assert not conversation_deleted(projects, project_id, conversation_id)
    assert hidden_conversations(projects, [project_id]) == frozenset()
    assert projects.deleted_conversations(project_id) == []
    assert projects.summary(project_id)["conversation_count"] == 2
    assert not conversation_deleted(projects, project_id, kept)
    with pytest.raises(RestoreRefusedError):
        projects.restore_conversation(
            project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
        )


def test_only_a_conversation_started_in_the_project_is_deleted(projects: ProjectStore) -> None:
    project_id, _ = started(projects)
    other_project, elsewhere = started(projects)
    for conversation_id in (elsewhere, new_invocation_id()):
        with pytest.raises(UnknownConversationError):
            projects.delete_conversation(
                project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
            )
    assert projects.deleted_conversations(project_id) == []
    assert projects.deleted_conversations(other_project) == []


def test_a_conversation_is_restored_only_within_the_restore_period(tmp_path: Path) -> None:
    final = ProjectStore(tmp_path / "projects", restore_period=timedelta(0))
    project_id, conversation_id = started(final)
    final.delete_conversation(
        project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    with pytest.raises(RestoreRefusedError):
        final.restore_conversation(
            project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
        )
    assert conversation_deleted(final, project_id, conversation_id)


def test_a_conversation_in_a_deleted_project_is_not_changed(projects: ProjectStore) -> None:
    project_id, conversation_id = started(projects)
    projects.delete(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    with pytest.raises(ProjectDeletedError):
        projects.delete_conversation(
            project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
        )


def test_the_owner_and_a_starter_who_may_contribute_may_delete(projects: ProjectStore) -> None:
    """Docs/specs/projects.md, invariant 30."""
    project_id, owners = started(projects)
    # Started by someone with no role in the project, as only the harness itself could.
    theirs = projects.start_conversation(project_id, acted_for=SOMEONE_ELSE, caused_by="test")
    assert projects.started_by(project_id, theirs) == SOMEONE_ELSE.principal_id
    for conversation_id in (owners, theirs):
        assert may_delete_conversation(projects, project_id, conversation_id, TEST_PRINCIPAL)
        # Starting it is not enough without a role that may contribute.
        assert not may_delete_conversation(projects, project_id, conversation_id, SOMEONE_ELSE)
    assert projects.started_by(project_id, new_invocation_id()) is None
