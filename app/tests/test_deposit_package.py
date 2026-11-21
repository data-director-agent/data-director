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
from support import (
    JSON_HEADERS,
    ZENODO,
    check_fixture,
    configure_env,
    dist_dir,
    new_governance,
    pin_export,
)

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_app.routes.deposit import BuiltPackage, DepositReview, PackageRefusedProblem
from dd_harness.projects import (
    DEPOSIT_CHECKS_CONFIRMED,
    DEPOSIT_ITEM_DECIDED,
    PACKAGE_BUILT,
    PROJECT_VALIDATED,
    text_digest,
)
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
    Zenodo is checked against DataCite and the deployment's override for it."""
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    store.add_inventory(
        project_id, file_inventory("data/cores.csv"), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    chose = client.put(f"/api/projects/{project_id}/repository", json={"repository_id": ZENODO})
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


@pytest.fixture
def ready(client: TestClient, valid: str) -> str:
    """`valid` with every item the deposit check lists decided, and the checks before deposit
    confirmed, through the server."""
    review = client.get(f"/api/projects/{valid}/review").json()
    for item in review["items"]:
        decided = client.put(
            f"/api/projects/{valid}/review/items/{item['item_id']}", json={"decision": "keep"}
        )
        assert decided.status_code == 200, decided.text
    confirmed = client.put(
        f"/api/projects/{valid}/review/confirmation",
        json={"confirmed": [s["id"] for s in review["statements"]]},
    )
    assert confirmed.status_code == 200, confirmed.text
    return valid


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
    response = client.post(f"/api/projects/{chosen}/validation", headers=JSON_HEADERS)
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
    response = client.post(f"/api/projects/{chosen}/package", headers=JSON_HEADERS)
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
    check_fixture("project-package-refused.json", normalised(problem), model=PackageRefusedProblem)


def test_a_valid_project_builds_a_package_to_download_by_its_digest(
    client: TestClient, store: ProjectStorage, ready: str
) -> None:
    valid = ready
    response = client.post(f"/api/projects/{valid}/package", headers=JSON_HEADERS)
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
    check_fixture("project-package.json", normalised(body), model=BuiltPackage)


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
    response = client.request(method, f"/api/projects/{UNKNOWN}/{path}", headers=JSON_HEADERS)
    assert response.status_code == 404
    assert response.json()["type"].endswith("/project-not-found")


@pytest.mark.requirement("C2")
def test_a_marked_file_holds_the_package_until_the_person_decides_it(
    client: TestClient, store: ProjectStorage, valid: str
) -> None:
    """Field notes in the inventory hold the package until the person signed in decides them and
    confirms the checks before deposit; each is recorded for them (docs/specs/deposit.md, "The
    pause before packaging")."""
    store.add_inventory(
        valid,
        file_inventory("data/cores.csv", "fieldnotes/day1.txt"),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    refused = client.post(f"/api/projects/{valid}/package", headers=JSON_HEADERS)
    assert refused.status_code == 409
    validation = refused.json()["validation"]
    assert (validation["conforms"], validation["ready"]) == (True, False)
    review = validation["review"]
    assert {i["path"] for i in review["items"]} >= {"fieldnotes/day1.txt"}
    assert review["confirmation"] is None
    assert review["not_checked"]
    check_fixture("project-review.json", normalised(review), model=DepositReview)

    unknown = client.put(
        f"/api/projects/{valid}/review/items/{'0' * 24}", json={"decision": "keep"}
    )
    assert unknown.status_code == 404
    assert unknown.json()["type"].endswith("/review-item-not-found")
    malformed = client.put(
        f"/api/projects/{valid}/review/items/{review['items'][0]['item_id']}",
        json={"decision": "publish"},
    )
    assert malformed.status_code == 400
    partial = client.put(
        f"/api/projects/{valid}/review/confirmation", json={"confirmed": ["ethics_approval"]}
    )
    assert partial.status_code == 400
    assert events(store, valid, DEPOSIT_ITEM_DECIDED) == []
    assert events(store, valid, DEPOSIT_CHECKS_CONFIRMED) == []

    for item in review["items"]:
        decided = client.put(
            f"/api/projects/{valid}/review/items/{item['item_id']}",
            json={"decision": "leave_out", "note": "Not part of the dataset."},
        )
        assert decided.status_code == 200
    confirmed = client.put(
        f"/api/projects/{valid}/review/confirmation",
        json={"confirmed": [s["id"] for s in review["statements"]]},
    )
    after = confirmed.json()
    assert after["confirmation"]["confirmed_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert all(i["decision"]["decision"] == "leave_out" for i in after["items"])
    assert client.get(f"/api/projects/{valid}/review").json() == after
    for event in events(store, valid, DEPOSIT_ITEM_DECIDED):
        assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
        assert event["caused_by"].startswith("PUT /api/projects/")
    assert client.post(f"/api/projects/{valid}/package", headers=JSON_HEADERS).status_code == 201
