"""A person's answers to a draft's questions, through the app's server (docs/specs/drafting.md,
invariant 6): the server passes them to the harness with the principal its authenticator names,
and answers with the documents read back from the project log."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, new_governance
from test_document_decisions import normalised

from dd_app.app import ANSWERS_REFUSED, build_app
from dd_app.governance import Governance
from dd_harness.projects import DOCUMENT_CHANGE_REFUSED, DOCUMENT_QUESTION_ANSWERED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import (
    STUB_QUESTION,
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind

ASKED = STUB_QUESTION.question_id


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


def asking(store: ProjectStorage, runs_dir: Path) -> tuple[str, str]:
    """A project with a first draft of a README that asks `STUB_QUESTION`, and its document."""
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conductor = make_conductor(runs_dir / "drafts", DocumentStub(asks=True))
    envelope = conductor.invoke(
        request("stub.document", document_request(DocumentKind.README)), acting_for=TEST_PRINCIPAL
    )
    ref = store.record_draft(project_id, envelope)
    return project_id, ref.document_id


def answer(client: TestClient, project_id: str, document_id: str, body: Any) -> Any:
    return client.post(f"/api/projects/{project_id}/documents/{document_id}/answers", json=body)


def given(text: str = "Soil cores", question: str = ASKED) -> list[dict[str, str]]:
    return [{"answered_question": question, "answer_text": text}]


@pytest.mark.requirement("R5")
def test_an_answer_acts_for_the_person_signed_in_and_is_in_the_log(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    project_id, document_id = asking(store, tmp_path)
    response = answer(client, project_id, document_id, {"version": 1, "answers": given()})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["answered"] == {"document_id": document_id, "version": 1}
    (document,) = body["documents"]
    (recorded,) = document["answers"]
    assert (recorded["question_id"], recorded["answer_text"]) == (ASKED, "Soil cores")
    assert recorded["answered_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert body["answer_max_length"] > 0

    event = store.events(project_id)[-1]
    assert event["event"] == DOCUMENT_QUESTION_ANSWERED
    path = f"/api/projects/{project_id}/documents/{document_id}/answers"
    assert event["caused_by"] == f"POST {path}"
    assert store.answers(project_id, DocumentKind.README) == [
        {"answered_question": ASKED, "answer_text": "Soil cores"}
    ]
    # The shell's tests are drawn from a project whose README asks a question, answered.
    check_fixture("project-answers.json", normalised(body))


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"version": 1, "answers": given(), "acted_for": {}}, "never name who answered"),
        ({"version": 1, "answers": [{**given()[0], "answered_by": "x"}]}, "exactly"),
        ({"version": 0, "answers": given()}, "`version` must be"),
        ({"version": 1, "answers": []}, "at least one"),
        ({"version": 1, "answers": given(question="Q1")}, "question's identifier"),
        ({"version": 1, "answers": given(text="   ")}, "blank"),
        ({"version": 1, "answers": given() * 2}, "answered once"),
    ],
)
def test_malformed_answers_are_refused_and_record_nothing(
    client: TestClient,
    store: ProjectStorage,
    tmp_path: Path,
    body: dict[str, Any],
    message: str,
) -> None:
    project_id, document_id = asking(store, tmp_path)
    before = store.events(project_id)
    response = answer(client, project_id, document_id, body)
    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert response.json()["title"] == ANSWERS_REFUSED
    assert store.events(project_id) == before


@pytest.mark.parametrize(
    ("version", "question", "refusal"),
    [(2, ASKED, "version-not-latest"), (1, "q-" + "1" * 16, "question-not-asked")],
)
def test_an_answer_to_a_question_not_asked_is_a_conflict(
    client: TestClient,
    store: ProjectStorage,
    tmp_path: Path,
    version: int,
    question: str,
    refusal: str,
) -> None:
    project_id, document_id = asking(store, tmp_path)
    body = {"version": version, "answers": given(question=question)}
    response = answer(client, project_id, document_id, body)
    assert response.status_code == 409
    assert response.json()["type"].endswith(f"/{refusal}")
    assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED
    assert store.answers(project_id, DocumentKind.README) is None


def test_an_unknown_project_or_document_is_not_found(
    client: TestClient, store: ProjectStorage, tmp_path: Path
) -> None:
    unknown = "01900000-0000-7000-8000-000000000009"
    body = {"version": 1, "answers": given()}
    assert answer(client, unknown, unknown, body).status_code == 404
    project_id, _ = asking(store, tmp_path)
    response = answer(client, project_id, unknown, body)
    assert response.status_code == 404
    assert response.json()["type"].endswith("/document-not-found")
    malformed = answer(client, project_id, "x" * 5000, body)
    assert malformed.status_code == 400
