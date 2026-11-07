"""A researcher chooses a repository from `advisor.repository`'s shortlist through the app's server
(docs/specs/deposit.md, #400): the body names the run and the candidate, the repository's name and
declared standards come from the run's evidence, and the harness resolves and records the choice."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, new_governance

from dd_app.app import CHOICE_REFUSED, build_app
from dd_app.governance import Governance
from dd_harness.projects import REPOSITORY_CHOSEN
from dd_harness.storage import ProjectStorage, RunStorage
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import new_invocation_id

ORDA = "r3d100012124"
ZENODO = "r3d100010468"
FIXED_TIME = "2026-01-01T00:00:00Z"


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
def runs(governance: Governance) -> RunStorage:
    return governance.conductor.store


def _record(re3data_id: str, name: str, standards: list[str]) -> dict[str, Any]:
    return {
        "source_id": re3data_id,
        "source_uri": f"https://www.re3data.org/repository/{re3data_id}",
        "content": {"re3data_id": re3data_id, "name": name, "metadata_standards": standards},
    }


def shortlist(
    runs: RunStorage, project_id: str | None, agent_id: str = "advisor.repository"
) -> str:
    """A stored `advisor.repository` run shortlisting ORDA and Zenodo, with each one's re3data
    record as evidence, as the conductor stores it."""
    invocation_id = new_invocation_id()
    runs.append(
        {
            "invocation_id": invocation_id,
            "agent_id": agent_id,
            "agent_version": "0.1.0",
            "project_id": project_id,
            "completed_at": datetime.now(UTC).isoformat(),
            "outcome": {"status": "succeeded", "statement": "Two candidates."},
            "payload": {
                "candidates": [
                    {"basis": "recommended", "grounded_on": [{"source_id": ORDA}]},
                    {"basis": "recommended", "grounded_on": [{"source_id": ZENODO}]},
                ]
            },
            "evidence": [
                _record(ORDA, "ORDA", ["Dublin Core"]),
                _record(ZENODO, "Zenodo", ["DataCite Metadata Schema", "Dublin Core"]),
            ],
        }
    )
    return invocation_id


def choose(client: TestClient, project_id: str, **body: Any) -> Any:
    return client.post(f"/api/projects/{project_id}/repository", json=body)


def test_a_choice_takes_the_repository_from_the_runs_evidence(
    client: TestClient, store: ProjectStorage, runs: RunStorage
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    run = shortlist(runs, project_id)
    response = choose(client, project_id, invocation_id=run, re3data_id=ORDA)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["repository_name"] == "ORDA"
    assert body["declared_standards"] == ["Dublin Core"]
    assert [s["ref"].split("@")[0] for s in body["requirement_sets"]] == ["datacite-4", "orda"]
    assert body["warnings"] == []
    assert body["chosen_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert body["requirements"]["repository_name"] == "ORDA"
    (event,) = [e for e in store.events(project_id) if e["event"] == REPOSITORY_CHOSEN]
    assert event["caused_by"] == f"POST /api/projects/{project_id}/repository"
    assert client.get(f"/api/projects/{project_id}/repository").json() == body
    check_fixture("project-repository.json", {**body, "chosen_at": FIXED_TIME})


def test_a_repository_without_an_override_is_chosen_with_its_warning_and_the_last_choice_counts(
    client: TestClient, store: ProjectStorage, runs: RunStorage
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    run = shortlist(runs, project_id)
    assert choose(client, project_id, invocation_id=run, re3data_id=ORDA).status_code == 201
    response = choose(client, project_id, invocation_id=run, re3data_id=ZENODO)
    assert response.status_code == 201
    (warning,) = response.json()["warnings"]
    assert "no override for Zenodo" in warning
    current = client.get(f"/api/projects/{project_id}/repository").json()
    assert current["repository_name"] == "Zenodo"
    assert store.summary(project_id)["repository"]["repository_name"] == "Zenodo"


@pytest.mark.parametrize(
    ("case", "detail"),
    [
        ("another project", "not in this project"),
        ("another agent", "advisor.repository"),
        ("not shortlisted", "does not shortlist"),
        ("no run", "no such run"),
    ],
)
def test_a_choice_the_run_does_not_support_is_refused_and_nothing_recorded(
    client: TestClient, store: ProjectStorage, runs: RunStorage, case: str, detail: str
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    re3data_id = ORDA
    if case == "another project":
        run = shortlist(runs, store.create(acted_for=TEST_PRINCIPAL, caused_by="test"))
    elif case == "another agent":
        run = shortlist(runs, project_id, agent_id="advisor.standards")
    elif case == "not shortlisted":
        run, re3data_id = shortlist(runs, project_id), "r3d100000001"
    else:
        run = new_invocation_id()
    response = choose(client, project_id, invocation_id=run, re3data_id=re3data_id)
    assert response.status_code == 400
    assert response.json()["title"] == CHOICE_REFUSED
    assert detail.lower() in response.json()["detail"].lower()
    assert not [e for e in store.events(project_id) if e["event"] == REPOSITORY_CHOSEN]


def test_a_choice_never_names_who_chose_or_the_repository(
    client: TestClient, store: ProjectStorage, runs: RunStorage
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    run = shortlist(runs, project_id)
    for extra in ({"repository_name": "Mine"}, {"acted_for": "someone"}):
        response = choose(client, project_id, invocation_id=run, re3data_id=ORDA, **extra)
        assert response.status_code == 400
    assert choose(client, project_id, invocation_id="nope", re3data_id=ORDA).status_code == 400


def test_an_unknown_project_or_no_choice_answers_404(
    client: TestClient, store: ProjectStorage, runs: RunStorage
) -> None:
    unknown = new_invocation_id()
    run = shortlist(runs, unknown)
    assert choose(client, unknown, invocation_id=run, re3data_id=ORDA).status_code == 404
    assert client.get(f"/api/projects/{unknown}/repository").status_code == 404
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    response = client.get(f"/api/projects/{project_id}/repository")
    assert response.status_code == 404
    assert response.json()["title"] == "No repository chosen"
