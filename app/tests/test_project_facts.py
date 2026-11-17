"""A person's decisions on the facts check agents proposed, through the app's server
(docs/specs/projects.md): the server passes them to the harness with the principal its
authenticator names, answers with the proposals and facts read back from the project log, and lets
only an owner decide whether sensitive data may be published or which licence applies."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_app.routes.facts import FACT_REFUSED
from dd_harness.project_access import Role
from dd_harness.projects import DOCUMENT_CHANGE_REFUSED, FACT_DECIDED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import new_invocation_id

DUPLICATE = {
    "fact_kind": "file_inclusion",
    "fact_subject": "data/old/readings (copy).csv",
    "fact_file_path": "data/old/readings (copy).csv",
    "file_decision": "exclude",
    "fact_check_kind": "duplicate",
    "proposed_because": "It is byte for byte the same as data/readings.csv.",
}
SITES = {
    "fact_kind": "sensitivity",
    "fact_subject": "calibration/sites.csv",
    "sensitive_subject": "calibration/sites.csv",
    "sensitivity_decision": "undecided",
}


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


def proposed(store: ProjectStorage, *facts: dict[str, Any]) -> tuple[str, list[str]]:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    ids = store.propose_facts(
        project_id, facts, agent_id="advisor.files", acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    return project_id, ids


def decide(client: TestClient, project_id: str, body: Any) -> Any:
    return client.post(f"/api/projects/{project_id}/facts/decisions", json=body)


def test_a_confirmed_proposal_becomes_a_fact_acting_for_the_person_signed_in(
    client: TestClient, store: ProjectStorage
) -> None:
    project_id, (duplicate,) = proposed(store, DUPLICATE)
    offered = client.get(f"/api/projects/{project_id}/facts").json()
    assert [p["proposal"] for p in offered["proposals"]] == [duplicate]
    assert offered["decisions"] == []

    response = decide(client, project_id, {"verdict": "confirmed", "proposal": duplicate})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["proposals"] == []
    (fact,) = body["decisions"]
    assert fact["file_decision"] == "exclude"
    assert "proposed_because" not in fact

    event = store.events(project_id)[-1]
    assert event["event"] == FACT_DECIDED
    assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert event["caused_by"] == f"POST /api/projects/{project_id}/facts/decisions"


@pytest.mark.parametrize(
    "body",
    [
        {"verdict": "maybe"},
        {"verdict": "confirmed", "proposal": 3},
        {"verdict": "changed", "fact": "exclude it"},
        {"verdict": "changed", "fact": {"fact_kind": "funder", "fact_subject": "NERC"}},
        {"verdict": "confirmed"},
    ],
)
def test_a_malformed_decision_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage, body: dict[str, Any]
) -> None:
    project_id, _ = proposed(store, DUPLICATE)
    before = store.events(project_id)
    response = decide(client, project_id, body)
    assert response.status_code == 400, response.text
    assert response.json()["title"] == FACT_REFUSED
    assert store.events(project_id) == before


def test_a_decision_not_on_a_proposal_of_the_project_is_refused_and_recorded(
    client: TestClient, store: ProjectStorage
) -> None:
    project_id, (duplicate,) = proposed(store, DUPLICATE)
    missing = decide(client, project_id, {"verdict": "confirmed", "proposal": new_invocation_id()})
    assert missing.status_code == 404
    assert missing.json()["type"].endswith("proposal-not-found")
    readings = "data/readings.csv"
    other = {**DUPLICATE, "fact_subject": readings, "fact_file_path": readings}
    moved = decide(client, project_id, {"verdict": "changed", "proposal": duplicate, "fact": other})
    assert moved.status_code == 409
    assert moved.json()["type"].endswith("fact-not-proposed")
    assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED


def test_only_an_owner_decides_sensitivity_and_licence(
    client: TestClient,
    store: ProjectStorage,
    governance: Governance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A member may decide which files go in, but whether sensitive data may be published has
    legal consequences, so only an owner decides it. No one is a plain member until membership
    events are built (#389), so the role the check reads is stood in for here."""
    project_id, (duplicate, sites) = proposed(store, DUPLICATE, SITES)
    monkeypatch.setattr(governance, "role", lambda _project_id, _principal: Role.MEMBER)
    before = store.events(project_id)
    for body in (
        {"verdict": "confirmed", "proposal": sites},
        {"verdict": "changed", "fact": {**SITES, "sensitivity_decision": "withhold"}},
        {
            "verdict": "changed",
            "fact": {"fact_kind": "licence", "fact_subject": "licence", "licence_id": "CC-BY-4.0"},
        },
    ):
        response = decide(client, project_id, body)
        assert response.status_code == 403, response.text
        assert response.json()["type"].endswith("project-action-forbidden")
    assert store.events(project_id) == before

    response = decide(client, project_id, {"verdict": "confirmed", "proposal": duplicate})
    assert response.status_code == 201, response.text
