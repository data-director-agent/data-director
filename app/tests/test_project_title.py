"""A project's name, through the app's server (docs/specs/projects.md): a person renames a project
with the principal the authenticator names, and a model's name never replaces theirs."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.projects import PROJECT_RENAMED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL


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


def test_a_person_renames_a_project_and_a_model_cannot_rename_it_after(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert store.rename(
        project, "Named by a model", source="model", acted_for=TEST_PRINCIPAL, caused_by="run"
    )
    renamed = client.put(f"/api/projects/{project}/title", json={"title": "  Soil cores  "})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Soil cores"
    assert renamed.json()["title_source"] == "researcher"
    (event,) = [e for e in store.events(project) if e["caused_by"].startswith("PUT ")]
    assert event["event"] == PROJECT_RENAMED
    assert event["caused_by"] == f"PUT /api/projects/{project}/title"

    assert not store.rename(
        project, "Another", source="model", acted_for=TEST_PRINCIPAL, caused_by="run"
    )
    assert store.summary(project)["title"] == "Soil cores"


def test_what_is_no_title_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    before = store.events(project)
    for body in ({}, {"title": 3}, {"title": "   "}, {"title": "x" * 201}, ["Soil"]):
        refused = client.put(f"/api/projects/{project}/title", json=body)
        assert refused.status_code == 400, body
    assert store.events(project) == before
    unknown = "01900000-0000-7000-8000-000000000001"
    assert client.put(f"/api/projects/{unknown}/title", json={"title": "A"}).status_code == 404
