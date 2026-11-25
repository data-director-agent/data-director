"""Converting the approved metadata record to another standard through the app's server
(docs/specs/metadata-standards.md, invariant 9; #1363): the conversion kept as a package derived
from the record, listed and downloaded in its own media type, and refused with what to add when
the target requires a field the record cannot supply."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import ZENODO, configure_env, dist_dir, new_governance, pin_export

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.projects import text_digest
from dd_harness.storage import ProjectStorage
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind

DATACITE = "http://datacite.org/schema/kernel-4"
OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"
RECORD: dict[str, Any] = {
    "titles": [{"title": "Soil cores from Hope Valley"}],
    "creators": [{"name": "Carberry, Josiah"}],
    "types": {"resourceTypeGeneral": "Dataset"},
    "descriptions": [{"description": "Cores taken in 2026.", "descriptionType": "Abstract"}],
    "publicationYear": "2026",
}


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


def approved(
    client: TestClient, store: ProjectStorage, governance: Governance, tmp_path: Path, record: Any
) -> str:
    """A project with Zenodo chosen and a metadata record approved as `record`, through the
    server; the draft's run is in the store the server reads."""
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    chose = client.put(f"/api/projects/{project_id}/repository", json={"repository_id": ZENODO})
    assert chose.status_code == 201
    conductor = make_conductor(tmp_path / "drafts", DocumentStub(), crate=True)
    conductor.store = governance.conductor.store
    envelope = conductor.invoke(
        request("stub.document", document_request(DocumentKind.METADATA_RECORD)),
        acting_for=TEST_PRINCIPAL,
    )
    ref = store.record_draft(project_id, envelope)
    (document,) = client.get(f"/api/projects/{project_id}/documents").json()["documents"]
    shown = document["versions"][-1]
    decided = client.post(
        f"/api/projects/{project_id}/documents/{ref.document_id}/decisions",
        json={
            "version": shown["version"],
            "digest": text_digest(shown["text"]),
            "decision": "approved",
            "edited_text": json.dumps(record),
            "reason": "Checked against the field notebook.",
        },
    )
    assert decided.status_code == 201, decided.text
    return project_id


def test_a_conversion_is_kept_listed_and_downloaded_in_its_own_media_type(
    client: TestClient, store: ProjectStorage, governance: Governance, tmp_path: Path
) -> None:
    project = approved(client, store, governance, tmp_path, RECORD)
    path = f"/api/projects/{project}/conversions"
    made = client.post(path, json={"conforms_to": OAI_DC})
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["conforms_to"] == OAI_DC
    assert body["media_type"] == "application/xml"
    assert "publicationYear" in body["unplaced"]
    assert all(r["path"] and r["reason"] for r in body["reduced"])
    listed = client.get(path).json()["conversions"]
    assert [c["digest"] for c in listed] == [body["digest"]]
    download = client.get(f"{path}/{body['digest']}")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/xml")
    assert download.headers["content-disposition"].endswith(f'{body["digest"][:12]}.xml"')
    assert b"Soil cores from Hope Valley" in download.content
    assert client.get(f"{path}/{'0' * 64}").status_code == 404


def test_a_conversion_missing_a_required_field_is_refused_with_what_to_add(
    client: TestClient, store: ProjectStorage, governance: Governance, tmp_path: Path
) -> None:
    untitled = {key: value for key, value in RECORD.items() if key != "titles"}
    project = approved(client, store, governance, tmp_path, untitled)
    path = f"/api/projects/{project}/conversions"
    refused = client.post(path, json={"conforms_to": OAI_DC})
    assert refused.status_code == 409
    assert refused.headers["content-type"] == "application/problem+json"
    missing = refused.json()["missing"]
    assert [m["property"] for m in missing] == ["title"]
    assert all(m["label"] and m["question"] for m in missing)
    assert client.get(path).json()["conversions"] == []


def test_a_conversion_that_cannot_be_asked_for_is_refused(
    client: TestClient, store: ProjectStorage, governance: Governance, tmp_path: Path
) -> None:
    bare = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    no_record = client.post(f"/api/projects/{bare}/conversions", json={"conforms_to": OAI_DC})
    assert no_record.status_code == 400
    project = approved(client, store, governance, tmp_path, RECORD)
    path = f"/api/projects/{project}/conversions"
    for standard in (DATACITE, "https://example.org/no-such-standard"):
        answer = client.post(path, json={"conforms_to": standard})
        assert answer.status_code == 400
        assert answer.json()["type"].endswith("/request-refused")
    assert client.post(path, json={"standard": OAI_DC}).status_code == 400
