"""A person's request for a new draft of a document, through the app's server
(docs/specs/drafting.md, invariant 10): the server runs the agent that drafted the document in the
project, which the conductor gives the project's recorded answers, whether or not any question is
left open, and answers with the documents and the run's outcome."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import check_fixture
from test_document_answers import ASKED, asking, given
from test_document_decisions import normalised
from test_document_revisions import client, drafted, governance, store

from dd_app.routes.documents import DRAFT_REFUSED, ProjectDocuments
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL

__all__ = ["client", "governance", "store"]  # fixtures this module uses


def ask(client: TestClient, project_id: str, document_id: str, **body: Any) -> Any:
    return client.post(
        f"/api/projects/{project_id}/documents/{document_id}/drafts", json={"version": 1, **body}
    )


@pytest.mark.requirement("R5")
def test_a_new_draft_places_the_answers_given_and_leaves_none_open(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, document_id = asking(store, tmp_path)
    answered = client.post(
        f"/api/projects/{project_id}/documents/{document_id}/answers",
        json={"version": 1, "answers": given()},
    )
    assert answered.status_code == 201, answered.text

    response = ask(client, project_id, document_id)

    assert response.status_code == 201, response.text
    body = response.json()
    run = body["drafted"]
    assert run["status"] == "succeeded"
    assert run["version"] == {"document_id": document_id, "version": 2}
    assert "revised" not in body
    (document,) = body["documents"]
    second = document["versions"][-1]
    assert second["drafted_by"]["invocation_id"] == run["invocation_id"]
    assert second["revises"] == {"document_id": document_id, "version": 1}
    recorded = client.get(f"/api/runs/{run['invocation_id']}").json()
    given_input = recorded["request"]["input"]
    assert recorded["envelope"]["project_id"] == project_id
    assert given_input["redraft_document"] == document_id
    assert given_input.get("revise") is not True
    assert [a["answered_question"] for a in given_input["draft_answers"]] == [ASKED]
    check_fixture("project-drafted.json", normalised(body), model=ProjectDocuments)


def test_a_draft_with_no_question_open_can_be_drafted_again(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, shown = drafted(store, tmp_path)
    assert not shown["questions"]

    response = ask(client, project_id, shown["document_id"])

    assert response.status_code == 201, response.text
    assert response.json()["drafted"]["version"]["version"] == 2


def test_a_request_naming_an_earlier_version_is_refused_and_nothing_runs(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, shown = drafted(store, tmp_path)
    assert ask(client, project_id, shown["document_id"]).status_code == 201
    before = store.events(project_id)

    response = ask(client, project_id, shown["document_id"])

    assert response.status_code == 409
    assert response.json()["type"].endswith("/version-not-latest")
    assert store.events(project_id) == before


def test_after_a_persons_edit_the_agent_that_drafted_the_document_drafts_it_again(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, shown = drafted(store, tmp_path)
    edited = store.edit(
        project_id,
        shown["document_id"],
        1,
        shown["digest"],
        "# Edited\n",
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )

    response = ask(client, project_id, shown["document_id"], version=edited.version)

    assert response.status_code == 201, response.text
    assert response.json()["drafted"]["version"]["version"] == edited.version + 1


@pytest.mark.parametrize("body", [{"version": 0}, {"version": "latest"}])
def test_a_malformed_request_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage, tmp_path: Path, body: dict[str, Any]
) -> None:
    project_id, shown = drafted(store, tmp_path)
    before = store.events(project_id)
    response = ask(client, project_id, shown["document_id"], **body)
    assert response.status_code == 400
    assert response.json()["title"] == DRAFT_REFUSED
    assert store.events(project_id) == before


def test_an_unknown_project_or_document_is_not_found(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    unknown = "01900000-0000-7000-8000-000000000009"
    assert ask(client, unknown, unknown).status_code == 404
    project_id, _ = drafted(store, tmp_path)
    response = ask(client, project_id, unknown)
    assert response.status_code == 404
    assert response.json()["type"].endswith("/document-not-found")
