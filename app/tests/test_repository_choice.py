"""Choosing a repository through the app's server (docs/specs/deposit.md): the researcher names a
re3data identifier, the harness reads its name and declared standards from the pinned re3data
export, and the server answers with the requirements it resolved to and their warnings."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.projects import REPOSITORY_CHOSEN
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL

ORDA = "r3d100012124"
ZENODO = "r3d100010468"
EXPORT = "re3data:export:2026-11"
# The fields a choice reads, as the export's registry.jsonl holds them.
RECORDS = (
    {
        "re3data_id": ORDA,
        "name": "ORDA - The University of Sheffield Research Data Catalogue and Repository",
        "metadata_standards": ["Dublin Core"],
    },
    {"re3data_id": ZENODO, "name": "Zenodo", "metadata_standards": ["DataCite Metadata Schema"]},
)


def pin_export(root: Path) -> Path:
    """A `sources.yaml` pinning a re3data export of `RECORDS`, as `dd-re3data fetch` builds."""
    root.mkdir(parents=True, exist_ok=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in RECORDS).encode()
    (root / "registry.jsonl").write_bytes(data)
    entry = {
        "snapshot_refs": [EXPORT],
        "path": "registry.jsonl",
        "id_field": "re3data_id",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    config = root / "sources.yaml"
    config.write_text(yaml.safe_dump({"sources": [entry]}), "utf-8")
    return config


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


def test_a_choice_resolves_from_re3data_and_the_last_one_counts(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    path = f"/api/projects/{project}/repository"
    none = client.get(path)
    assert none.status_code == 404
    assert none.json()["type"].endswith("/repository-not-chosen")

    zenodo = client.put(path, json={"re3data_id": ZENODO})
    assert zenodo.status_code == 201
    assert zenodo.json()["repository_name"] == "Zenodo"
    (warning,) = zenodo.json()["warnings"]
    assert "no override for Zenodo" in warning

    orda = client.put(path, json={"re3data_id": ORDA})
    assert orda.status_code == 201
    chosen = orda.json()
    assert chosen["re3data_id"] == ORDA
    assert [s["ref"] for s in chosen["requirement_sets"]] == ["datacite-4@v1", "orda@v2"]
    assert chosen["warnings"] == []
    assert client.get(path).json() == chosen
    check_fixture("repository-chosen.json", chosen)

    events = [e for e in store.events(project) if e["event"] == REPOSITORY_CHOSEN]
    assert [e["re3data_id"] for e in events] == [ZENODO, ORDA]
    assert all(e["caused_by"] == f"PUT {path}" for e in events)
    assert all(e["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id for e in events)
    assert events[-1]["snapshot_ref"] == EXPORT
    assert store.summary(project)["repository"]["re3data_id"] == ORDA


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"re3data_id": "r3d100099999"}, "holds no repository r3d100099999"),
        ({"re3data_id": "orda"}, "not a re3data identifier"),
        ({"name": "ORDA"}, "`re3data_id`"),
        ([ORDA], "`re3data_id`"),
    ],
)
def test_what_is_not_a_repository_re3data_holds_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage, body: object, detail: str
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    refused = client.put(f"/api/projects/{project}/repository", json=body)
    assert refused.status_code == 400
    assert detail in refused.json()["detail"]
    assert len(store.events(project)) == 1


def test_an_unknown_project_or_an_unbuilt_export_is_answered_as_such(
    client: TestClient, store: ProjectStorage, governance: Governance, tmp_path: Path
) -> None:
    unknown = "0" * 8 + "-0000-7000-8000-" + "0" * 12
    assert (
        client.put(f"/api/projects/{unknown}/repository", json={"re3data_id": ORDA}).status_code
        == 404
    )
    assert client.get(f"/api/projects/{unknown}/repository").status_code == 404

    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    governance.conductor.sources = type(governance.conductor.sources)()
    refused = client.put(f"/api/projects/{project}/repository", json={"re3data_id": ORDA})
    assert refused.status_code == 503
    assert "pins no re3data export" in refused.json()["detail"]
    assert len(store.events(project)) == 1
