"""Deleting and restoring a project, through the app's server (docs/specs/projects.md, invariants
22 to 25, "Deletion and retention"): only an owner deletes, after typing the project's name; a
deleted project leaves every list, is answered as missing to anyone else, and takes no new work
until it is restored."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.project_access import Role
from dd_harness.projects import PROJECT_DELETED, PROJECT_RESTORED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

SOMEONE_ELSE = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
TURN = {"agent_id": "orchestrator.stub", "message_text": "Hello", "follows": None}


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


def delete(client: TestClient, project_id: str, title: str) -> Any:
    return client.request("DELETE", f"/api/projects/{project_id}", json={"title": title})


def test_an_owner_deletes_a_project_by_its_name_and_restores_it(
    client: TestClient, governance: Governance, store: ProjectStorage
) -> None:
    # Created as a person creates one, so that it is listed while it holds nothing.
    project = client.post("/api/projects", json={"title": "Soil cores"}).json()["project_id"]
    kept = client.post("/api/projects", json={"title": "Kept"}).json()["project_id"]
    # Conversations and runs are listed from the projects a person may read.
    assert project in (governance.readable(TEST_PRINCIPAL).project_ids or ())

    deleted = delete(client, project, " Soil cores ")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    event = store.events(project)[-1]
    assert (event["event"], event["caused_by"]) == (
        PROJECT_DELETED,
        f"DELETE /api/projects/{project}",
    )
    # It leaves every list, its conversations and runs with it, and is found only under deleted.
    assert [p["project_id"] for p in client.get("/api/projects").json()] == [kept]
    assert project not in (governance.readable(TEST_PRINCIPAL).project_ids or ())
    (listed,) = client.get("/api/projects/deleted").json()
    assert listed["project_id"] == project
    assert set(listed["deleted"]) == {"at", "by", "restorable_until"}
    # Its owner may still read it.
    assert client.get(f"/api/projects/{project}/documents").status_code == 200

    restored = client.post(f"/api/projects/{project}/restore", json={})
    assert restored.status_code == 200
    assert restored.json()["deleted"] is None
    assert store.events(project)[-1]["event"] == PROJECT_RESTORED
    assert {p["project_id"] for p in client.get("/api/projects").json()} == {project, kept}
    assert project in (governance.readable(TEST_PRINCIPAL).project_ids or ())
    assert client.get("/api/projects/deleted").json() == []


def test_a_name_that_is_not_the_projects_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage
) -> None:
    titled = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil cores")
    untitled = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    for project_id, body in (
        (titled, {"title": "Soil"}),
        (titled, {"title": "soil cores"}),
        (titled, {}),
        (titled, {"title": None}),
        (untitled, {"title": ""}),
    ):
        before = store.events(project_id)
        response = client.request("DELETE", f"/api/projects/{project_id}", json=body)
        assert response.status_code == 400
        assert store.events(project_id) == before
    # A project with no title is named by its identifier.
    assert delete(client, untitled, untitled).status_code == 200


def test_a_member_may_not_delete_or_restore(
    client: TestClient, governance: Governance, store: ProjectStorage, monkeypatch: Any
) -> None:
    """No one is a plain member until membership events are built (#389), so the role the check
    reads is stood in for here."""
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil cores")
    monkeypatch.setattr(governance, "role", lambda _project_id, _principal: Role.MEMBER)
    before = store.events(project)
    for response in (
        delete(client, project, "Soil cores"),
        client.post(f"/api/projects/{project}/restore", json={}),
    ):
        assert response.status_code == 403
        assert response.json()["type"].endswith("project-action-forbidden")
    assert store.events(project) == before


def test_a_deleted_project_is_answered_as_missing_to_anyone_but_its_owner(
    client: TestClient, store: ProjectStorage
) -> None:
    theirs = store.create(acted_for=SOMEONE_ELSE, caused_by="test", title="Theirs")
    store.delete(theirs, acted_for=SOMEONE_ELSE, caused_by="test")
    for response in (
        client.get(f"/api/projects/{theirs}/documents"),
        client.post(f"/api/projects/{theirs}/restore", json={}),
        client.post("/api/conversations", json={"project_id": theirs}),
    ):
        assert response.status_code == 404
        assert response.json()["type"].endswith("project-not-found")
    assert client.get("/api/projects/deleted").json() == []


def test_a_deleted_project_takes_no_new_work(client: TestClient, store: ProjectStorage) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil cores")
    conversation = client.post("/api/conversations", json={"project_id": project}).json()
    delete(client, project, "Soil cores")
    before = store.events(project)
    refused = [
        client.put(f"/api/projects/{project}/title", json={"title": "New"}),
        client.post(f"/api/projects/{project}/intake/dismiss", json={}),
        client.post(f"/api/projects/{project}/package", json={}),
        client.post("/api/conversations", json={"project_id": project}),
        client.post(f"/api/conversations/{conversation['conversation_id']}/turns", json=TURN),
    ]
    for response in refused:
        assert response.status_code == 409, response.json()
        assert response.json()["type"].endswith("project-deleted")
    assert store.events(project) == before
    # Deleting again, and restoring what is not deleted, are refused too.
    assert delete(client, project, "Soil cores").status_code == 409
    client.post(f"/api/projects/{project}/restore", json={})
    again = client.post(f"/api/projects/{project}/restore", json={})
    assert again.status_code == 409
    assert again.json()["type"].endswith("project-restore-refused")


def test_a_project_past_its_restore_period_is_not_listed_or_restored(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil cores")
    delete(client, project, "Soil cores")
    store.restore_period = store.restore_period * 0
    assert client.get("/api/projects/deleted").json() == []
    response = client.post(f"/api/projects/{project}/restore", json={})
    assert response.status_code == 409
    assert store.is_deleted(project)
