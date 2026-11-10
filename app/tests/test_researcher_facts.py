"""Facts from a researcher's public ORCID record, through the app's server
(docs/specs/projects.md): a person sees what their own record offers, keeps what they tick in a
project, and withdraws it; the record is read again before anything is kept."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import JSON_HEADERS, check_fixture, configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.projects import RESEARCHER_ADDED, RESEARCHER_WITHDRAWN
from dd_harness.storage import ProjectStorage
from dd_harness.testing import SAMPLE_ID, TEST_PRINCIPAL, FakeOrcidRegistry, sample_record

# The test principal is the iD in ORCID's documentation, asserted by the operator.
assert TEST_PRINCIPAL.principal_id.endswith(SAMPLE_ID)


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


@pytest.fixture
def registry() -> FakeOrcidRegistry:
    return FakeOrcidRegistry(
        issuer="https://orcid.org", records={SAMPLE_ID: sample_record(host="orcid.org")}
    )


@pytest.fixture
def client(governance: Governance, tmp_path: Path, registry: FakeOrcidRegistry) -> TestClient:
    return TestClient(
        build_app(governance, dist_dir(tmp_path), orcid_transport=registry.transport())
    )


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


@pytest.fixture
def project(store: ProjectStorage) -> str:
    return store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")


def normalised(body: Any) -> Any:
    """`body` with the time the record was read fixed, for a fixture."""
    if isinstance(body, list):
        return [normalised(item) for item in body]
    return {**body, "record_retrieved_at": "2026-11-10T12:00:00+00:00"}


def test_a_person_sees_what_their_own_record_offers_and_nothing_is_kept(
    client: TestClient, store: ProjectStorage, project: str
) -> None:
    offered = client.get("/api/researcher/orcid")
    assert offered.status_code == 200
    body = offered.json()
    assert body["orcid_id"] == TEST_PRINCIPAL.principal_id
    assert body["affiliations"] and body["works"] and body["keywords"]
    assert "@" not in offered.text
    check_fixture("orcid-record.json", normalised(body))
    assert store.researchers(project) is None


def test_only_what_is_ticked_is_kept_and_given_back(
    client: TestClient, store: ProjectStorage, project: str, registry: FakeOrcidRegistry
) -> None:
    offered = client.get("/api/researcher/orcid").json()
    employment = offered["affiliations"][0]["put_code"]
    keep = {"sections": ["researcher_name", "keywords"], "affiliations": [employment]}
    before = registry.requests

    kept = client.put(f"/api/projects/{project}/researchers/me", json={"keep": keep})

    assert kept.status_code == 201
    assert registry.requests == before + 1  # read again, never taken from the body
    [record] = kept.json()
    assert set(record) == {
        "orcid_id",
        "researcher_name",
        "keywords",
        "affiliations",
        "record_retrieved_at",
        "record_source",
    }
    assert [a["put_code"] for a in record["affiliations"]] == [employment]
    assert client.get(f"/api/projects/{project}/researchers").json() == [record]
    check_fixture("project-researchers.json", normalised(kept.json()))
    (event,) = [e for e in store.events(project) if e["event"] == RESEARCHER_ADDED]
    assert event["caused_by"] == f"PUT /api/projects/{project}/researchers/me"
    assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id


def test_a_withdrawn_record_is_no_longer_given(
    client: TestClient, store: ProjectStorage, project: str
) -> None:
    path = f"/api/projects/{project}/researchers/me"
    assert client.put(path, json={"keep": {"sections": ["keywords"]}}).status_code == 201
    withdrawn = client.delete(path, headers=JSON_HEADERS)
    assert withdrawn.status_code == 200
    assert withdrawn.json() == []
    assert store.researchers(project) is None
    assert store.events(project)[-1]["event"] == RESEARCHER_WITHDRAWN
    assert client.delete(path, headers=JSON_HEADERS).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"keep": ["keywords"]},
        {"keep": {"sections": ["emails"]}},
        {"keep": {"works": ["999"]}},
        {"facts": {"researcher_name": "Someone Else"}},
    ],
)
def test_a_choice_that_is_not_the_records_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage, project: str, body: Any
) -> None:
    before = store.events(project)
    refused = client.put(f"/api/projects/{project}/researchers/me", json=body)
    assert refused.status_code == 400, body
    assert store.events(project) == before


def test_an_orcid_that_cannot_be_reached_records_nothing(
    client: TestClient, store: ProjectStorage, project: str, registry: FakeOrcidRegistry
) -> None:
    registry.failing = 503
    before = store.events(project)
    assert client.get("/api/researcher/orcid").status_code == 502
    kept = client.put(f"/api/projects/{project}/researchers/me", json={"keep": {}})
    assert kept.status_code == 502
    assert store.events(project) == before


def test_a_project_the_person_may_not_read_is_not_found(
    client: TestClient, store: ProjectStorage
) -> None:
    unknown = "01900000-0000-7000-8000-000000000001"
    path = f"/api/projects/{unknown}/researchers"
    assert client.get(path).status_code == 404
    assert client.put(path + "/me", json={"keep": {}}).status_code == 404
