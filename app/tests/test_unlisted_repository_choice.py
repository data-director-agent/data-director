"""A repository re3data does not list, found and chosen on a project's page by its DataCite
identifier (#1342, docs/specs/deposit.md)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import (
    DURHAM,
    JSON_HEADERS,
    configure_env,
    dist_dir,
    new_governance,
    pin_export,
)

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.testing import TEST_PRINCIPAL


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_export(tmp_path / "re3data", datacite=True)))
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


def test_a_repository_only_datacite_registers_is_found_by_name_and_chosen_by_its_id(
    client: TestClient, governance: Governance
) -> None:
    (found,) = client.get("/api/repositories", params={"q": "durham"}).json()["repositories"]
    assert (found["repository_id"], found["registry"], found["re3data_id"]) == (
        DURHAM,
        "datacite",
        None,
    )
    assert governance.projects is not None
    project = governance.projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    chosen = client.put(
        f"/api/projects/{project}/repository",
        json={"repository_id": DURHAM},
        headers=JSON_HEADERS,
    )
    assert chosen.status_code == 201, chosen.text
    assert chosen.json()["repository_id"] == DURHAM
    assert "re3data_id" not in chosen.json()
    summary = governance.projects.summary(project)["repository"]
    assert (summary["repository_id"], summary["re3data_id"]) == (DURHAM, None)
    # It registers DataCite DOIs, so DataCite's set is no fallback: only the override is missed.
    (warning,) = chosen.json()["warnings"]
    assert "no override" in warning
