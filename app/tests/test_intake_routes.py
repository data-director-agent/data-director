"""The project intake through the app's server (docs/specs/app.md, rule 25): the next question is
read, an answer or a dismissal is recorded for the principal the authenticator names, and what the
harness refuses records nothing. The shell's intake fixtures are written from here."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.progress import ENTRY_CHOSEN, INTAKE_ANSWERED, INTAKE_DISMISSED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.intake import ENTRY, NO, NOT_SURE, YES
from dd_sdk.process_flow import ENTRIES

INTAKE_EVENTS = (ENTRY_CHOSEN, INTAKE_ANSWERED, INTAKE_DISMISSED)


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


@pytest.fixture
def project(store: ProjectStorage) -> str:
    return store.create(acted_for=TEST_PRINCIPAL, caused_by="test")


def path(project: str, rest: str = "") -> str:
    return f"/api/projects/{project}/intake{rest}"


def test_a_new_project_reads_the_entry_question_next(client: TestClient, project: str) -> None:
    found = client.get(path(project))
    assert found.status_code == 200
    body = found.json()
    assert body["state"] == "pending"
    assert body["next"] == ENTRY
    assert body["questions"][0]["question_id"] == ENTRY
    assert body["questions"][0]["answer_values"] is None
    check_fixture("intake-pending.json", body)


def test_answering_each_question_in_turn_completes_the_intake_with_a_suggestion(
    client: TestClient, store: ProjectStorage, project: str
) -> None:
    first = ENTRIES[0].number
    answered = client.post(path(project, f"/{ENTRY}"), json={"answer_values": [str(first)]})
    assert answered.status_code == 201
    body = answered.json()
    assert body["progress"]["entry"] == first
    seen = {ENTRY}
    while body["next"] is not None:
        asked = body["next"]
        assert asked not in seen
        seen.add(asked)
        values = [NO] if asked == "intake.dmp" else [NOT_SURE]
        answered = client.post(path(project, f"/{asked}"), json={"answer_values": values})
        assert answered.status_code == 201
        body = answered.json()
    assert body["state"] == "complete"
    assert body["progress"]["suggested"] is not None
    assert {q["question_id"] for q in body["questions"]} == seen
    check_fixture("intake-complete.json", body)

    events = [e for e in store.events(project) if e["event"] in INTAKE_EVENTS]
    assert len(events) == len(seen)
    assert all(e["caused_by"].startswith("POST /api/projects/") for e in events)
    assert all(e["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id for e in events)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"answer_values": "yes"},
        {"answer_values": [1]},
        ["yes"],
    ],
)
def test_a_malformed_answer_is_refused_with_400_and_records_nothing(
    client: TestClient, store: ProjectStorage, project: str, body: object
) -> None:
    before = store.events(project)
    refused = client.post(path(project, f"/{ENTRY}"), json=body)
    assert refused.status_code == 400
    assert store.events(project) == before


@pytest.mark.parametrize(
    ("question_id", "values"),
    [
        (ENTRY, ["9"]),
        (ENTRY, []),
        ("intake.unknown", [YES]),
        # Not asked before an entry point is known.
        ("intake.dmp", [YES]),
    ],
)
def test_an_answer_the_harness_rejects_is_refused_with_409_and_records_nothing(
    client: TestClient, store: ProjectStorage, project: str, question_id: str, values: list[str]
) -> None:
    before = store.events(project)
    refused = client.post(path(project, f"/{question_id}"), json={"answer_values": values})
    assert refused.status_code == 409
    assert refused.headers["content-type"] == "application/problem+json"
    assert store.events(project) == before


def test_dismissing_records_the_dismissal_and_an_answer_opens_the_intake_again(
    client: TestClient, project: str
) -> None:
    dismissed = client.post(path(project, "/dismiss"), json={})
    assert dismissed.status_code == 201
    assert dismissed.json()["state"] == "dismissed"
    assert dismissed.json()["next"] is None
    assert client.get(path(project)).json()["state"] == "dismissed"

    reopened = client.post(path(project, f"/{ENTRY}"), json={"answer_values": ["1"]})
    assert reopened.json()["state"] == "pending"


def test_an_unknown_project_has_no_intake(client: TestClient) -> None:
    unknown = "01900000-0000-7000-8000-000000000001"
    assert client.get(path(unknown)).status_code == 404
    assert client.post(path(unknown, "/dismiss"), json={}).status_code == 404
    assert client.post(path(unknown, f"/{ENTRY}"), json={"answer_values": ["1"]}).status_code == 404
