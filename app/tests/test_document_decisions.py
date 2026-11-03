"""A project's documents and a person's decision on each, through the app's server
(docs/specs/projects.md): the server passes the decision to the harness with the principal its
authenticator names, and answers with the state read back from the project log."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.projects import (
    DOCUMENT_CHANGE_REFUSED,
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_VERSION_DECIDED,
    ProjectStore,
    text_digest,
)
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")
FIXED_TIME = "2026-01-01T00:00:00Z"


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def store(governance: Governance) -> ProjectStore:
    assert governance.projects is not None
    return governance.projects


def drafted(store: ProjectStore, runs_dir: Path, *kinds: DocumentKind) -> str:
    """A project with a first draft of each of `kinds`, recorded as the conductor will (#394)."""
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conductor = make_conductor(runs_dir / "drafts", DocumentStub())
    for kind in kinds:
        envelope = conductor.invoke(
            request("stub.document", document_request(kind)), acting_for=TEST_PRINCIPAL
        )
        store.record_draft(project_id, envelope)
    return project_id


def normalised(body: Any) -> Any:
    """`body` with each identifier numbered in order of first appearance, and every time fixed.
    A digest is of the text, which does not change, so it stays."""
    text = json.dumps(body, sort_keys=True)
    seen: dict[str, str] = {}

    def fixed(match: re.Match[str]) -> str:
        return seen.setdefault(match.group(0), f"01900000-0000-7000-8000-{len(seen) + 1:012d}")

    return json.loads(TIMESTAMP.sub(FIXED_TIME, UUID.sub(fixed, text)))


def decide(client: TestClient, project_id: str, shown: dict[str, Any], **body: Any) -> Any:
    """Decide on the version `shown`, naming the digest of its text, unless `body` says else."""
    sent = {"version": shown["version"], "digest": text_digest(shown["text"]), **body}
    return client.post(
        f"/api/projects/{project_id}/documents/{shown['document_id']}/decisions", json=sent
    )


def test_a_project_lists_its_documents_with_the_rule_for_reasons(
    client: TestClient, store: ProjectStore, tmp_path: Path
) -> None:
    project_id = drafted(store, tmp_path, DocumentKind.README, DocumentKind.DATA_DICTIONARY)
    response = client.get(f"/api/projects/{project_id}/documents")
    assert response.status_code == 200
    body = response.json()
    assert [d["document_kind"] for d in body["documents"]] == ["readme", "data_dictionary"]
    assert {v["state"] for d in body["documents"] for v in d["versions"]} == {"proposed"}
    assert body["review"]["reason_required"] == {
        "approved": False,
        "edited_and_approved": True,
        "rejected": True,
    }
    # The shell's tests are drawn from a project whose data dictionary has been approved.
    dictionary = body["documents"][1]["versions"][0]
    approved = decide(client, project_id, dictionary, decision="approved")
    assert approved.status_code == 201
    check_fixture("project-documents.json", normalised(approved.json()))


@pytest.mark.requirement("C13.3")
def test_a_decision_acts_for_the_person_signed_in_and_is_in_the_log(
    client: TestClient, store: ProjectStore, tmp_path: Path
) -> None:
    project_id = drafted(store, tmp_path, DocumentKind.README)
    (document,) = store.documents(project_id)
    response = decide(
        client,
        project_id,
        document["versions"][0],
        decision="approved",
        reason="Named the field site.",
        edited_text="# Soil cores from Moor House\n",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decided"] == {"document_id": document["document_id"], "version": 2}
    first, second = body["documents"][0]["versions"]
    assert (first["state"], second["state"]) == ("proposed", "approved")
    assert second["decision"]["decided_by"]["principal_id"] == TEST_PRINCIPAL.principal_id

    added, decided = store.events(project_id)[-2:]
    assert (added["event"], decided["event"]) == (DOCUMENT_VERSION_ADDED, DOCUMENT_VERSION_DECIDED)
    assert decided["reason"] == "Named the field site."
    assert decided["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    path = f"/api/projects/{project_id}/documents/{document['document_id']}/decisions"
    assert decided["caused_by"] == f"POST {path}"


def test_a_decision_on_a_version_already_decided_is_a_conflict(
    client: TestClient, store: ProjectStore, tmp_path: Path
) -> None:
    project_id = drafted(store, tmp_path, DocumentKind.README)
    version = store.documents(project_id)[0]["versions"][0]
    assert decide(client, project_id, version, decision="approved").status_code == 201
    again = decide(client, project_id, version, decision="rejected", reason="Second thoughts.")
    assert again.status_code == 409
    assert again.headers["content-type"] == "application/problem+json"
    assert again.json()["type"].endswith("/version-decided")
    assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED
    assert store.documents(project_id)[0]["versions"][0]["state"] == "approved"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"decision": "rejected"}, "rejecting needs a reason"),
        ({"decision": "approved", "edited_text": "# New\n"}, "approving an edit needs a reason"),
        ({"decision": "approved", "decided_by": "someone else"}, "never names who decided"),
        ({"decision": "approved", "acted_for": {}}, "never names who decided"),
        ({"decision": "maybe"}, "`decision` must be"),
        ({"decision": "approved", "version": 0}, "`version` must be"),
        ({"decision": "approved", "digest": "abc"}, "`digest` must be"),
    ],
)
def test_a_malformed_decision_is_refused_and_records_nothing(
    client: TestClient,
    store: ProjectStore,
    tmp_path: Path,
    body: dict[str, Any],
    message: str,
) -> None:
    project_id = drafted(store, tmp_path, DocumentKind.README)
    version = store.documents(project_id)[0]["versions"][0]
    before = store.events(project_id)
    response = decide(client, project_id, version, **body)
    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert response.json()["title"] == "Data Director could not record this decision"
    assert store.events(project_id) == before


def test_an_unknown_project_or_document_is_not_found(
    client: TestClient, store: ProjectStore, tmp_path: Path
) -> None:
    unknown = "01900000-0000-7000-8000-000000000009"
    assert client.get(f"/api/projects/{unknown}/documents").status_code == 404
    assert client.get("/api/projects/..%2F..%2Fetc/documents").status_code == 404
    project_id = drafted(store, tmp_path, DocumentKind.README)
    version = {**store.documents(project_id)[0]["versions"][0], "document_id": unknown}
    response = decide(client, project_id, version, decision="approved")
    assert response.status_code == 404
    assert response.json()["type"].endswith("/document-not-found")


def test_a_document_named_by_anything_but_its_identifier_records_nothing(
    client: TestClient, store: ProjectStore, tmp_path: Path
) -> None:
    # Otherwise anyone signed in could grow a project's log with names of their choosing.
    project_id = drafted(store, tmp_path, DocumentKind.README)
    version = {**store.documents(project_id)[0]["versions"][0], "document_id": "x" * 5000}
    before = store.events(project_id)
    response = decide(client, project_id, version, decision="approved")
    assert response.status_code == 400
    assert "UUIDv7" in response.json()["detail"]
    assert store.events(project_id) == before


def test_the_project_page_is_served_by_the_shell(client: TestClient) -> None:
    response = client.get("/projects/01900000-0000-7000-8000-000000000001")
    assert response.status_code == 200
    assert "<title>shell</title>" in response.text
