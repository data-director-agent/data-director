"""Choosing a project's metadata standard through the app's server (docs/specs/deposit.md,
invariant 5; #1362): the standard of the repository chosen last and why, the standards the
deployment has a set for, and the refusal of one its override is not written for."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import ORDA, configure_env, dist_dir, new_governance, pin_export

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL

DATACITE = "http://datacite.org/schema/kernel-4"
OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_export(tmp_path / "re3data")))
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


def test_a_standard_is_chosen_only_once_a_repository_is(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    path = f"/api/projects/{project}/repository/standard"
    for answer in (client.get(path), client.put(path, json={"conforms_to": DATACITE})):
        assert answer.status_code == 404
        assert answer.json()["type"].endswith("/repository-not-chosen")


def test_a_standard_the_override_is_not_written_for_is_refused(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert (
        client.put(f"/api/projects/{project}/repository", json={"repository_id": ORDA}).status_code
        == 201
    )
    path = f"/api/projects/{project}/repository/standard"
    offered = client.get(path).json()
    # The deployment's standards, in its order of preference; ORDA's override names DataCite.
    assert [s["conforms_to"] for s in offered["standards"]] == [DATACITE, OAI_DC]
    assert offered["standard"]["reason"] == "override"
    assert offered["may_choose"] is False
    refused = client.put(path, json={"conforms_to": OAI_DC})
    assert refused.status_code == 400
    assert "written for" in refused.json()["detail"]
    # ORDA's own standard is accepted, and the summary says the override decides it.
    kept = client.put(path, json={"conforms_to": DATACITE})
    assert kept.status_code == 201
    assert kept.json()["standard"]["reason"] == "override"
    assert client.get(f"/api/projects/{project}/repository").json()["conforms_to"] == DATACITE
    assert store.summary(project)["repository"]["standard"]["reason"] == "override"
    assert client.put(path, json={"standard": OAI_DC}).status_code == 400
