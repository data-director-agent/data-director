"""A document in which possible personal data or secrets are found is held until the researcher
confirms what was found, and neither the response nor the log repeats it (#473,
docs/specs/app.md)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.responses import Response
from starlette.testclient import TestClient
from support import JSON_HEADERS, a_document, configure_env, delegating_app, dist_dir, start, turn

from dd_app.governance import Governance
from dd_app.turn_body import AttachedDocument, Turn, parse_turn
from dd_harness.projects import ProjectStore

FLAGGED = "# Follow-up\n\nWrite to jane.doe@example.org or call 07700 900123 to book the visit.\n"
VALUES = ("jane.doe@example.org", "07700 900123")


@pytest.fixture
def in_projects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Governance, Any]]:
    env = configure_env(monkeypatch, tmp_path)
    yield delegating_app(env, dist_dir(tmp_path), ProjectStore(env / "projects"))


def documents_of(governance: Governance, conversation_id: str) -> list[dict[str, Any]]:
    assert governance.projects is not None
    project_id = governance.projects.project_of(conversation_id)
    assert project_id is not None
    return governance.projects.documentation(project_id)


@pytest.mark.requirement("C2")
def test_a_document_with_personal_data_is_held_naming_the_kinds_and_not_the_values(
    in_projects: tuple[Governance, Any], caplog: pytest.LogCaptureFixture
) -> None:
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    with caplog.at_level(logging.INFO):
        response = turn(client, conversation_id, "", documentation=a_document(FLAGGED))
    assert response.status_code == 409
    held = response.json()
    assert held["type"].endswith("documentation-held")
    assert {"email address", "phone number"} <= set(held["kinds"])
    said = json.dumps(held) + caplog.text
    assert not [v for v in VALUES if v in said]
    assert "held for confirmation" in caplog.text
    assert documents_of(governance, conversation_id) == []
    assert list(governance.conductor.store.iter_envelopes()) == []


def test_a_document_is_attached_once_every_kind_found_is_confirmed(
    in_projects: tuple[Governance, Any],
) -> None:
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    partly = {**a_document(FLAGGED), "confirmed": ["email address"]}
    assert turn(client, conversation_id, "", documentation=partly).status_code == 409
    assert documents_of(governance, conversation_id) == []
    confirmed = {**a_document(FLAGGED), "confirmed": ["email address", "phone number"]}
    response = turn(client, conversation_id, "", documentation=confirmed)
    assert response.status_code == 200, response.json()
    assert len(documents_of(governance, conversation_id)) == 1


def test_a_document_with_nothing_found_needs_no_confirmation(
    in_projects: tuple[Governance, Any],
) -> None:
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    assert turn(client, conversation_id, "", documentation=a_document()).status_code == 200
    assert len(documents_of(governance, conversation_id)) == 1


@pytest.mark.requirement("C2")
def test_the_check_names_what_it_found_and_keeps_nothing(
    in_projects: tuple[Governance, Any],
) -> None:
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    checked = client.post(
        "/api/documentation/check",
        headers=JSON_HEADERS,
        json=a_document(FLAGGED),
    )
    assert checked.status_code == 200
    body = checked.json()
    assert {"email address", "phone number"} <= set(body["kinds"])
    assert body["checked_with"]
    assert not [v for v in VALUES if v in json.dumps(body)]
    assert documents_of(governance, conversation_id) == []
    refused = client.post(
        "/api/documentation/check",
        headers=JSON_HEADERS,
        json={**a_document(FLAGGED), "media_type": "application/pdf"},
    )
    assert refused.status_code == 400


def test_a_streamed_turn_carries_what_was_confirmed() -> None:
    body = {
        "agent_id": "orchestrator",
        "message_text": "",
        "follows": None,
        "documentation": {**a_document(FLAGGED), "confirmed": ["email address"]},
    }
    parsed = parse_turn(body)
    assert isinstance(parsed, Turn)
    assert isinstance(parsed.documentation, AttachedDocument)
    assert parsed.documentation.confirmed == ("email address",)
    wrong = {**body, "documentation": {**a_document(FLAGGED), "confirmed": "email address"}}
    refused = parse_turn(wrong)
    assert isinstance(refused, Response)
    assert refused.status_code == 400
