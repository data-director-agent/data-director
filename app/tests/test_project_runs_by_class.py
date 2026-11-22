"""A project's runs of one payload class (`GET /api/projects/{id}/runs`, docs/specs/app.md): the
shell reads the FAIR feedback on a project's metadata record over time from it (#433). It lists
succeeded runs in the project's conversations whose payload is of the class asked for, newest
first, delegated children included, and nothing to someone who may not read the project."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, new_governance

from dd_agent_advisor_fairness import factory as fairness
from dd_app.app import build_app
from dd_app.governance import Governance
from dd_app.routes.project_runs import ProjectRuns
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL, in_process
from dd_sdk.contract.models import Principal

FAIRNESS_CLASS = "FairnessReport"
# A draft DataCite record that meets some checks and not others.
DRAFT = {
    "titles": [{"title": "Peat depth survey, Kinder Scout, 2025"}],
    "creators": [
        {
            "name": "Byron, Ada",
            "nameIdentifiers": [
                {
                    "nameIdentifier": "https://orcid.org/0000-0002-1825-0097",
                    "nameIdentifierScheme": "ORCID",
                }
            ],
        },
        {"name": "Babbage, Charles"},
    ],
    "rightsList": [{"rights": "CC BY 4.0", "rightsIdentifier": "CC-BY-4.0"}],
    "formats": ["text/csv"],
    "types": {"resourceTypeGeneral": "Dataset"},
}
SOMEONE_ELSE = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    for found in new_governance():
        found.conductor.registry.add(in_process(fairness.build({fairness.SWITCH: "template"})))
        yield found


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def projects(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


def _report(client: TestClient) -> dict[str, Any]:
    """A real FAIR report on the sample draft, run outside any project."""
    draft = {"schema_class": "ProjectMetadataDraft", "draft_text": json.dumps(DRAFT)}
    body = client.post("/api/runs", json={"agent_id": "advisor.fairness", "input": draft})
    assert body.status_code == 200, body.text
    envelope: dict[str, Any] = body.json()["envelope"]
    assert envelope["payload"]["schema_class"] == FAIRNESS_CLASS
    return envelope


def _store_in(
    governance: Governance,
    base: dict[str, Any],
    n: int,
    *,
    project_id: str,
    conversation_id: str,
    **changes: Any,
) -> dict[str, Any]:
    """A copy of `base` stored as run `n` of a conversation in the project, as the conductor
    stores a run there."""
    envelope = copy.deepcopy(base)
    envelope.update(
        invocation_id=f"01900000-0000-7000-8000-{n:012d}",
        completed_at=f"2026-01-0{n}T00:00:00Z",
        project_id=project_id,
        conversation_id=conversation_id,
        **changes,
    )
    governance.conductor.store.append(envelope)
    return envelope


def test_the_project_runs_of_a_class_are_listed_newest_first(
    client: TestClient, governance: Governance, projects: ProjectStorage
) -> None:
    base = _report(client)
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    other = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    elsewhere = projects.start_conversation(other, acted_for=TEST_PRINCIPAL, caused_by="t")
    turn = {**base, "agent_id": "orchestrator.stub", "payload": {"schema_class": "Reply"}}
    _store_in(governance, turn, 1, project_id=project, conversation_id=conversation)
    first = _store_in(
        governance,
        base,
        2,
        project_id=project,
        conversation_id=conversation,
        parent_invocation_id="01900000-0000-7000-8000-000000000001",
    )
    _store_in(
        governance,
        base,
        3,
        project_id=project,
        conversation_id=conversation,
        outcome={"status": "failed", "statement": "The agent could not be reached."},
    )
    latest = _store_in(governance, base, 4, project_id=project, conversation_id=conversation)
    _store_in(governance, turn, 5, project_id=other, conversation_id=elsewhere)
    _store_in(governance, base, 6, project_id=other, conversation_id=elsewhere)

    found = client.get(f"/api/projects/{project}/runs", params={"payload": FAIRNESS_CLASS})
    assert found.status_code == 200
    runs = found.json()["runs"]
    assert [r["invocation_id"] for r in runs] == [latest["invocation_id"], first["invocation_id"]]
    assert {r["payload"]["schema_class"] for r in runs} == {FAIRNESS_CLASS}
    check_fixture("project-fairness-runs.json", found.json(), model=ProjectRuns)

    limited = client.get(
        f"/api/projects/{project}/runs", params={"payload": FAIRNESS_CLASS, "limit": "1"}
    )
    assert [r["invocation_id"] for r in limited.json()["runs"]] == [latest["invocation_id"]]
    none = client.get(f"/api/projects/{project}/runs", params={"payload": "Document"})
    assert none.json() == {"runs": []}


@pytest.mark.parametrize(
    "params",
    [{}, {"payload": "fairness report"}, {"payload": "FairnessReport", "limit": "0"}],
)
def test_a_listing_that_names_no_class_or_a_bad_limit_is_refused(
    client: TestClient, projects: ProjectStorage, params: dict[str, str]
) -> None:
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    refused = client.get(f"/api/projects/{project}/runs", params=params)
    assert refused.status_code == 400
    assert refused.json()["type"].endswith("/request-refused")


def test_someone_with_no_role_in_the_project_is_told_it_does_not_exist(
    client: TestClient, projects: ProjectStorage
) -> None:
    theirs = projects.create(acted_for=SOMEONE_ELSE, caused_by="test")
    found = client.get(f"/api/projects/{theirs}/runs", params={"payload": FAIRNESS_CLASS})
    assert found.status_code == 404
