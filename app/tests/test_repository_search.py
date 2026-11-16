"""Searching the pinned re3data export through the app's server, so that a researcher can choose
a repository on a project's page (docs/specs/deposit.md)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import (
    EXPORT,
    ORDA,
    ZENODO,
    check_fixture,
    configure_env,
    dist_dir,
    new_governance,
    pin_export,
)

from dd_app.app import build_app
from dd_app.governance import Governance


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_export(tmp_path / "re3data")))
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


def test_without_a_query_the_deployments_suggestions_come_overrides_first(
    client: TestClient,
) -> None:
    found = client.get("/api/repositories")
    assert found.status_code == 200
    body = found.json()
    assert body["suggested"] is True
    assert body["snapshot_ref"] == EXPORT
    # The deployment's list names repositories this export does not hold; they are left out.
    assert [r["re3data_id"] for r in body["repositories"]] == [ORDA, ZENODO]
    check_fixture("repositories-suggested.json", body)


@pytest.mark.parametrize(
    ("query", "expected"),
    [("zen", [ZENODO]), (ORDA, [ORDA]), ("orda.shef.ac.uk", [ORDA]), ("zz", [])],
)
def test_a_query_searches_the_pinned_export(
    client: TestClient, query: str, expected: list[str]
) -> None:
    found = client.get("/api/repositories", params={"q": query})
    assert found.status_code == 200
    body = found.json()
    assert body["suggested"] is False
    assert [r["re3data_id"] for r in body["repositories"]] == expected


def test_an_unbuilt_export_is_answered_as_unavailable(
    client: TestClient, governance: Governance
) -> None:
    governance.conductor.sources = type(governance.conductor.sources)()
    refused = client.get("/api/repositories", params={"q": "zenodo"})
    assert refused.status_code == 503
    assert refused.json()["type"].endswith("/re3data-unavailable")
