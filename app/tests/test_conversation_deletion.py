"""Deleting and restoring a conversation, through the app's server (docs/specs/app.md, rule 30;
docs/specs/projects.md, invariants 29 to 31): a deleted conversation leaves every list, is
answered as missing, takes no new turn, removes nothing from the run store, and comes back as it
was when restored."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import JSON_HEADERS, OTHER, configure_env, delegating_app, dist_dir, start, turn

from dd_app.conversation_deletion import ConversationDeletion
from dd_app.governance import Governance, UnknownConversationError
from dd_harness.projects import CONVERSATION_DELETED, CONVERSATION_RESTORED, ProjectStore
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Governance, Any]:
    """The app over the orchestrator, served in process, each conversation in a project."""
    env = configure_env(monkeypatch, tmp_path)
    return delegating_app(env, dist_dir(tmp_path), ProjectStore(env / "projects"))


@pytest.fixture
def governance(served: tuple[Governance, Any]) -> Governance:
    return served[0]


@pytest.fixture
def client(served: tuple[Governance, Any]) -> TestClient:
    return TestClient(served[1])


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


def a_conversation(client: TestClient) -> tuple[str, str]:
    """A conversation with one turn, and that turn's `invocation_id`."""
    conversation_id = start(client)
    answered = turn(client, conversation_id, "Hello")
    assert answered.status_code == 200
    return conversation_id, answered.json()["envelope"]["invocation_id"]


def listed(client: TestClient) -> list[str]:
    return [c["conversation_id"] for c in client.get("/api/conversations").json()]


def test_a_starter_deletes_a_conversation_and_restores_it(
    client: TestClient, governance: Governance, store: ProjectStorage
) -> None:
    deleted_id, invocation_id = a_conversation(client)
    kept_id, _ = a_conversation(client)
    project_id = store.project_of(deleted_id)
    assert project_id is not None

    deleted = client.delete(f"/api/conversations/{deleted_id}", headers=JSON_HEADERS)
    assert deleted.status_code == 200
    body = deleted.json()
    assert (body["conversation_id"], body["project_id"]) == (deleted_id, project_id)
    assert body["by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert {"at", "restorable_until"} <= set(body)
    event = store.events(project_id)[-1]
    assert (event["event"], event["caused_by"]) == (
        CONVERSATION_DELETED,
        f"DELETE /api/conversations/{deleted_id}",
    )

    # It leaves every list, and is answered as missing; its runs are kept, but not listed.
    assert listed(client) == [kept_id]
    assert client.get(f"/api/conversations/{deleted_id}").status_code == 404
    assert turn(client, deleted_id, "Again", invocation_id).status_code == 404
    assert governance.conductor.store.get(invocation_id) is not None
    assert invocation_id not in {r["invocation_id"] for r in client.get("/api/runs").json()}
    projects = {p["project_id"]: p for p in client.get("/api/projects").json()}
    assert project_id not in projects or projects[project_id]["conversations"] == []
    (found,) = client.get("/api/conversations/deleted").json()
    assert (found["conversation_id"], found["project_id"]) == (deleted_id, project_id)
    assert found["title"]
    # Deleting it again is a conflict.
    assert (
        client.delete(f"/api/conversations/{deleted_id}", headers=JSON_HEADERS).status_code == 409
    )

    assert (
        client.post(f"/api/conversations/{deleted_id}/restore", headers=JSON_HEADERS).status_code
        == 204
    )
    assert store.events(project_id)[-1]["event"] == CONVERSATION_RESTORED
    assert set(listed(client)) == {deleted_id, kept_id}
    assert client.get(f"/api/conversations/{deleted_id}").status_code == 200
    assert client.get("/api/conversations/deleted").json() == []
    # Restoring one that is not deleted is refused.
    assert (
        client.post(f"/api/conversations/{deleted_id}/restore", headers=JSON_HEADERS).status_code
        == 409
    )


def test_someone_who_may_not_read_a_conversation_is_told_it_does_not_exist(
    client: TestClient, governance: Governance, store: ProjectStorage
) -> None:
    conversation_id, _ = a_conversation(client)
    deletion = ConversationDeletion(governance)
    with pytest.raises(UnknownConversationError):
        deletion.delete(conversation_id, acted_for=OTHER, caused_by="test")
    deletion.delete(conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    with pytest.raises(UnknownConversationError):
        deletion.restore(conversation_id, acted_for=OTHER, caused_by="test")
    assert deletion.deleted_for(OTHER).items == []
    for unknown in ("not-a-conversation", "0190a5e4-2b2c-7c3d-8e4f-5a6b7c8d9e0f"):
        assert (
            client.delete(f"/api/conversations/{unknown}", headers=JSON_HEADERS).status_code == 404
        )
        assert (
            client.post(f"/api/conversations/{unknown}/restore", headers=JSON_HEADERS).status_code
            == 404
        )


def test_a_conversation_in_a_deleted_project_is_not_changed(
    client: TestClient, store: ProjectStorage
) -> None:
    conversation_id, _ = a_conversation(client)
    project_id = store.project_of(conversation_id)
    assert project_id is not None
    store.delete(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    response = client.delete(f"/api/conversations/{conversation_id}", headers=JSON_HEADERS)
    assert response.status_code == 409
    assert response.json()["type"].endswith("project-deleted")


def test_an_app_that_keeps_no_projects_deletes_no_conversation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = configure_env(monkeypatch, tmp_path)
    _, app = delegating_app(env, dist_dir(tmp_path), None)
    client = TestClient(app)
    conversation_id = start(client)
    assert turn(client, conversation_id, "Hello").status_code == 200
    assert (
        client.delete(f"/api/conversations/{conversation_id}", headers=JSON_HEADERS).status_code
        == 404
    )
    assert client.get("/api/conversations/deleted").json() == []
    assert listed(client) == [conversation_id]
