"""Validating a project and building its deposit package through the app's server
(docs/specs/deposit.md, #623): the server calls the harness in-process and passes on what it
says, and a package is downloaded by its digest."""

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
from support import ORDA, check_fixture, configure_env, dist_dir, new_governance, pin_export

from dd_app.app import PACKAGE_REFUSED, build_app
from dd_app.governance import Governance
from dd_harness.projects import APPROVED, PACKAGE_BUILT, PROJECT_VALIDATED, Decision
from dd_harness.storage import ProjectStorage
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    file_inventory,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind, new_invocation_id

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
FIXED_TIME = "2026-01-01T00:00:00+00:00"
# A DataCite record with every field ORDA's override requires (app/config/repositories).
RECORD: dict[str, Any] = {
    "titles": [{"title": "Soil cores from Hope Valley"}],
    "creators": [{"name": "Carberry, Josiah"}],
    "types": {"resourceTypeGeneral": "Dataset"},
    "subjects": [
        {"subject": "Soil sciences", "subjectScheme": "ANZSRC Fields of Research"},
        {"subject": "soil cores"},
    ],
    "descriptions": [{"description": "Cores taken in 2026.", "descriptionType": "Abstract"}],
    "rightsList": [{"rights": "CC BY 4.0", "rightsIdentifier": "CC-BY-4.0"}],
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


@pytest.fixture
def chosen(governance: Governance, store: ProjectStorage) -> str:
    """A project with an inventory and ORDA chosen, and no document."""
    assert governance.requirements is not None
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    store.add_inventory(
        project_id, file_inventory("data/cores.csv"), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    store.choose_repository(
        project_id,
        ORDA,
        registry=governance.conductor.sources,
        requirements=governance.requirements,
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    return project_id


def approve(
    store: ProjectStorage, runs_dir: Path, project_id: str, kind: DocumentKind, text: str | None
) -> None:
    """Draft a document of `kind` with the stub and approve it, as drafted or edited to `text`."""
    conductor = make_conductor(runs_dir, DocumentStub(), crate=True)
    envelope = conductor.invoke(
        request("stub.document", document_request(kind)), acting_for=TEST_PRINCIPAL
    )
    ref = store.record_draft(project_id, envelope)
    (document,) = [d for d in store.documents(project_id) if d["document_id"] == ref.document_id]
    decision = Decision(
        ref.document_id,
        ref.version,
        document["versions"][-1]["digest"],
        APPROVED,
        reason="Checked." if text is not None else None,
        edited_text=text,
    )
    store.decide(project_id, decision, acted_for=TEST_PRINCIPAL, caused_by="test")


@pytest.fixture
def ready(store: ProjectStorage, chosen: str, tmp_path: Path) -> str:
    """A project valid for ORDA: an approved metadata record, and an approved README."""
    approve(store, tmp_path, chosen, DocumentKind.METADATA_RECORD, json.dumps(RECORD))
    approve(store, tmp_path, chosen, DocumentKind.README, None)
    return chosen


def fixed(view: dict[str, Any]) -> dict[str, Any]:
    """A validation view with its time fixed and each identifier numbered in order of first
    appearance, the project first, for a fixture."""
    text = json.dumps(view, sort_keys=True)
    seen: dict[str, str] = {view["project_id"]: "01900000-0000-7000-8000-000000000001"}

    def numbered(match: re.Match[str]) -> str:
        return seen.setdefault(match.group(0), f"01900000-0000-7000-8000-{len(seen) + 1:012d}")

    found: dict[str, Any] = json.loads(UUID.sub(numbered, text))
    found["made_at"] = FIXED_TIME
    found["report"]["dd:validated_at"]["@value"] = FIXED_TIME
    found.pop("report_digest", None)
    return found


@pytest.mark.requirement("R4.2")
def test_a_project_without_a_required_document_is_invalid_and_says_why(
    client: TestClient, store: ProjectStorage, chosen: str, tmp_path: Path
) -> None:
    approve(store, tmp_path, chosen, DocumentKind.README, None)
    response = client.post(f"/api/projects/{chosen}/validations")
    assert response.status_code == 201
    body = response.json()
    assert body["conforms"] is False
    assert any("metadata record" in v["message"] for v in body["violations"])
    assert body["report"]["@type"] == "sh:ValidationReport"
    assert body["report"]["sh:conforms"] is False
    (event,) = [e for e in store.events(chosen) if e["event"] == PROJECT_VALIDATED]
    assert event["caused_by"] == f"POST /api/projects/{chosen}/validations"
    check_fixture("project-validation-refused.json", fixed(body))

    refused = client.post(f"/api/projects/{chosen}/packages")
    assert refused.status_code == 409
    problem = refused.json()
    assert problem["title"] == PACKAGE_REFUSED
    assert problem["validation"]["violations"] == body["violations"]
    assert not [e for e in store.events(chosen) if e["event"] == PACKAGE_BUILT]


def test_a_project_with_no_repository_chosen_is_invalid(
    client: TestClient, store: ProjectStorage
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    body = client.post(f"/api/projects/{project_id}/validations").json()
    assert body["conforms"] is False
    assert any("repository" in v["message"].lower() for v in body["violations"])


@pytest.mark.requirement("R4.2")
def test_a_valid_project_builds_a_package_that_downloads_by_its_digest(
    client: TestClient, store: ProjectStorage, ready: str
) -> None:
    validated = client.post(f"/api/projects/{ready}/validations")
    assert validated.json()["conforms"] is True, validated.json()["violations"]
    check_fixture("project-validation.json", fixed(validated.json()))

    built = client.post(f"/api/projects/{ready}/packages")
    assert built.status_code == 201, built.json()
    package = built.json()
    assert package["validation"]["conforms"] is True
    (event,) = [e for e in store.events(ready) if e["event"] == PACKAGE_BUILT]
    assert event["digest"] == package["digest"]
    assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id

    downloaded = client.get(f"/api/projects/{ready}/packages/{package['digest']}")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"
    assert f"deposit-{ready}-" in downloaded.headers["content-disposition"]
    assert hashlib.sha256(downloaded.content).hexdigest() == package["digest"]
    assert len(downloaded.content) == package["size"]
    names = zipfile.ZipFile(io.BytesIO(downloaded.content)).namelist()
    assert "ro-crate-metadata.json" in names


def test_an_unknown_package_or_project_answers_404(
    client: TestClient, store: ProjectStorage
) -> None:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    assert client.get(f"/api/projects/{project_id}/packages/{'0' * 64}").status_code == 404
    assert client.get(f"/api/projects/{project_id}/packages/not-a-digest").status_code == 404
    unknown = new_invocation_id()
    assert client.post(f"/api/projects/{unknown}/validations").status_code == 404
    assert client.post(f"/api/projects/{unknown}/packages").status_code == 404
    assert client.get(f"/api/projects/{unknown}/packages/{'0' * 64}").status_code == 404
