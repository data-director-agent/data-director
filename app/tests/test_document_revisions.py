"""A person's request for changes to a document, through the app's server (docs/specs/drafting.md,
invariant 12): the server records it for the principal its authenticator names, runs the agent
that drafted the document in the project, and answers with the documents and the run's outcome."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, new_governance
from test_document_decisions import normalised

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_app.routes.documents import REVISION_REFUSED, ProjectDocuments
from dd_harness.projects import DOCUMENT_CHANGE_REFUSED, text_digest
from dd_harness.storage import ProjectStorage
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    in_process,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind

ASK = "Shorten the Files paragraph."


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    for governance in new_governance():
        stub = DocumentStub()
        conductor = governance.conductor
        conductor.registry.add(in_process(stub))
        # The deployment enables the drafter, as a profile that runs one does.
        enabled = {**conductor.profile.agents, stub.spec.agent_id: stub.spec.action_class}
        conductor.profile = dataclasses.replace(conductor.profile, agents=enabled)
        yield governance


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


def drafted(store: ProjectStorage, runs_dir: Path) -> tuple[str, dict[str, Any]]:
    """A project with a first draft of a README by `stub.document`, and that version."""
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conductor = make_conductor(runs_dir / "drafts", DocumentStub())
    envelope = conductor.invoke(
        request("stub.document", document_request(DocumentKind.README)), acting_for=TEST_PRINCIPAL
    )
    store.record_draft(project_id, envelope)
    (document,) = store.documents(project_id)
    return project_id, document["versions"][-1]


def ask(client: TestClient, project_id: str, shown: dict[str, Any], **body: Any) -> Any:
    sent = {
        "version": shown["version"],
        "digest": text_digest(shown["text"]),
        "instruction": ASK,
        **body,
    }
    return client.post(
        f"/api/projects/{project_id}/documents/{shown['document_id']}/revisions", json=sent
    )


@pytest.mark.requirement("R5")
def test_a_request_is_recorded_for_the_person_and_its_drafter_revises_the_document(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, shown = drafted(store, tmp_path)

    response = ask(client, project_id, shown)

    assert response.status_code == 201, response.text
    body = response.json()
    (document,) = body["documents"]
    assert body["revised"]["status"] == "succeeded", body["revised"]
    first, second = document["versions"]
    assert first["revision_request"]["instruction"] == ASK
    assert first["revision_request"]["requested_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert second["revises"] == {"document_id": shown["document_id"], "version": 1}
    revised = body["revised"]
    assert revised["status"] == "succeeded"
    assert revised["version"] == {"document_id": shown["document_id"], "version": 2}
    assert second["drafted_by"]["invocation_id"] == revised["invocation_id"]
    assert body["request_max_length"] > 0
    # The run is in the project and no conversation.
    run = client.get(f"/api/runs/{revised['invocation_id']}").json()
    assert run["envelope"]["project_id"] == project_id
    assert "conversation_id" not in run["envelope"]
    assert run["request"]["input"]["revise"] is True
    assert run["request"]["input"]["current_version"]["revision_request"] == ASK
    check_fixture("project-revised.json", normalised(body), model=ProjectDocuments)


@pytest.mark.requirement("R5")
def test_a_request_for_a_stale_version_is_refused_and_nothing_runs(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, shown = drafted(store, tmp_path)
    store.edit(
        project_id,
        shown["document_id"],
        1,
        shown["digest"],
        "# Newer\n",
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )

    response = ask(client, project_id, shown)

    assert response.status_code == 409
    assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED
    assert len(store.documents(project_id)[0]["versions"]) == 2


def test_a_request_naming_other_text_is_refused(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, shown = drafted(store, tmp_path)
    response = ask(client, project_id, shown, digest="0" * 64)
    assert response.status_code == 409
    assert response.json()["type"].endswith("digest-mismatch")
    assert len(store.documents(project_id)[0]["versions"]) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"instruction": ""},
        {"acted_for": {"principal_id": "someone"}},
        {"version": 0},
        {"digest": "not-a-digest"},
    ],
)
def test_a_malformed_request_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage, tmp_path: Path, body: dict[str, Any]
) -> None:
    project_id, shown = drafted(store, tmp_path)
    before = store.events(project_id)
    response = ask(client, project_id, shown, **body)
    if "acted_for" in body:
        # A field the request does not take is ignored, never used to name who asked.
        assert response.status_code == 201
        event = next(
            e for e in store.events(project_id) if e["event"] == "document_revision_requested"
        )
        assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
        return
    assert response.status_code == 400
    assert response.json()["title"] == REVISION_REFUSED
    assert store.events(project_id) == before
