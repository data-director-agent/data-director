"""Validating a project and building its deposit package, through the app's server
(docs/specs/deposit.md): the server calls the harness for the person signed in and answers with
what the harness found, each violation and warning in the harness's own words."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import ZENODO, check_fixture, configure_env, dist_dir, new_governance, pin_export

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.projects import PACKAGE_BUILT, PROJECT_VALIDATED, text_digest
from dd_harness.storage import ProjectStorage
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    file_inventory,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind

# A DataCite record, in its JSON form, with every field the DataCite set requires or recommends.
RECORD: dict[str, Any] = {
    "titles": [{"title": "Soil cores from Hope Valley"}],
    "creators": [{"name": "Carberry, Josiah"}],
    "types": {"resourceTypeGeneral": "Dataset"},
    "subjects": [{"subject": "soil science"}],
    "descriptions": [{"description": "Cores taken in 2026.", "descriptionType": "Abstract"}],
    "rightsList": [
        {
            "rights": "Creative Commons Attribution 4.0 International",
            "rightsIdentifier": "CC-BY-4.0",
            "rightsUri": "https://creativecommons.org/licenses/by/4.0/legalcode",
        }
    ],
    "publisher": {"name": "University of Sheffield"},
    "publicationYear": "2026",
}
UNKNOWN = "01900000-0000-7000-8000-000000000001"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
HEX_DIGEST = re.compile(r"\b[0-9a-f]{64}\b")
NI_DIGEST = re.compile(r"ni:///sha-256;[A-Za-z0-9_-]+")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")


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


@pytest.fixture
def chosen(client: TestClient, store: ProjectStorage) -> str:
    """A project with an inventory and Zenodo chosen through the server, and no document.
    Zenodo has no override, so it is checked against DataCite with a warning."""
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    store.add_inventory(
        project_id, file_inventory("data/cores.csv"), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    chose = client.put(f"/api/projects/{project_id}/repository", json={"re3data_id": ZENODO})
    assert chose.status_code == 201
    return project_id


@pytest.fixture
def valid(
    client: TestClient,
    store: ProjectStorage,
    governance: Governance,
    chosen: str,
    tmp_path: Path,
) -> str:
    """`chosen` with a metadata record drafted and approved, edited to `RECORD`, through the
    server; its run is in the store the server reads, as the conductor's own would be."""
    conductor = make_conductor(tmp_path / "drafts", DocumentStub(), crate=True)
    conductor.store = governance.conductor.store
    envelope = conductor.invoke(
        request("stub.document", document_request(DocumentKind.METADATA_RECORD)),
        acting_for=TEST_PRINCIPAL,
    )
    ref = store.record_draft(chosen, envelope)
    (document,) = client.get(f"/api/projects/{chosen}/documents").json()["documents"]
    shown = document["versions"][-1]
    decided = client.post(
        f"/api/projects/{chosen}/documents/{ref.document_id}/decisions",
        json={
            "version": shown["version"],
            "digest": text_digest(shown["text"]),
            "decision": "approved",
            "edited_text": json.dumps(RECORD),
            "reason": "Checked against the field notebook.",
        },
    )
    assert decided.status_code == 201
    return chosen


def normalised(body: Any) -> Any:
    """`body` with each identifier and digest numbered in order of first appearance, every time
    fixed and the package's size, which follows the times it holds, fixed too."""
    text = json.dumps(body, sort_keys=True)
    seen: dict[str, str] = {}

    def numbered(template: str) -> Any:
        def fixed(match: re.Match[str]) -> str:
            return seen.setdefault(match.group(0), template.format(len(seen) + 1))

        return fixed

    text = UUID.sub(numbered("01900000-0000-7000-8000-{:012d}"), text)
    text = HEX_DIGEST.sub(numbered("{:064d}"), text)
    text = NI_DIGEST.sub(numbered("ni:///sha-256;{:043d}"), text)
    found = json.loads(TIMESTAMP.sub("2026-01-01T00:00:00Z", text))
    if "package" in found:
        found["package"]["size"] = 1
    return found


def events(store: ProjectStorage, project_id: str, kind: str) -> list[dict[str, Any]]:
    return [e for e in store.events(project_id) if e["event"] == kind]


def test_validating_a_project_keeps_the_report_and_names_what_is_missing(
    client: TestClient, store: ProjectStorage, chosen: str
) -> None:
    response = client.post(f"/api/projects/{chosen}/validation")
    assert response.status_code == 201
    body = response.json()
    assert body["conforms"] is False
    assert body["violations"] and body["warnings"]
    assert all(r["message"] for r in body["violations"] + body["warnings"])
    assert body["report"]["@type"] == "sh:ValidationReport"
    (kept,) = events(store, chosen, PROJECT_VALIDATED)
    assert kept["digest"] == body["report_digest"]
    assert kept["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id


def test_a_project_with_a_violation_builds_no_package_and_says_why(
    client: TestClient, store: ProjectStorage, chosen: str
) -> None:
    response = client.post(f"/api/projects/{chosen}/package")
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["type"].endswith("/package-refused")
    validation = problem["validation"]
    assert validation["conforms"] is False
    assert all(r["message"] in problem["detail"] for r in validation["violations"])
    # The report is kept, and no package is.
    (kept,) = events(store, chosen, PROJECT_VALIDATED)
    assert kept["digest"] == validation["report_digest"]
    assert events(store, chosen, PACKAGE_BUILT) == []
    check_fixture("project-package-refused.json", normalised(problem))


def test_a_valid_project_builds_a_package_to_download_by_its_digest(
    client: TestClient, store: ProjectStorage, valid: str
) -> None:
    response = client.post(f"/api/projects/{valid}/package")
    assert response.status_code == 201
    body = response.json()
    assert body["conforms"] is True
    assert body["violations"] == []
    package = body["package"]
    (built,) = events(store, valid, PACKAGE_BUILT)
    assert built["digest"] == package["digest"]
    assert package["href"] == f"/api/projects/{valid}/packages/{package['digest']}"

    download = client.get(package["href"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert "attachment" in download.headers["content-disposition"]
    assert hashlib.sha256(download.content).hexdigest() == package["digest"]
    assert len(download.content) == package["size"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as zipped:
        assert "ro-crate-metadata.json" in zipped.namelist()
    check_fixture("project-package.json", normalised(body))


@pytest.mark.parametrize("digest", ["0" * 64, "not-a-digest", "A" * 64])
def test_a_package_the_log_does_not_record_is_not_found(
    client: TestClient, chosen: str, digest: str
) -> None:
    response = client.get(f"/api/projects/{chosen}/packages/{digest}")
    assert response.status_code == 404
    assert response.json()["type"].endswith("/package-not-found")


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "validation"), ("POST", "package"), ("GET", f"packages/{'0' * 64}")],
)
def test_an_unknown_project_is_not_found(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, f"/api/projects/{UNKNOWN}/{path}")
    assert response.status_code == 404
    assert response.json()["type"].endswith("/project-not-found")
