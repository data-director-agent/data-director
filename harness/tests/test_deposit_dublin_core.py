"""A project whose repository declares Dublin Core: its set applies, and a record in OAI-DC XML is
validated and packaged through Dublin Core's definition, as a DataCite record is through
DataCite's (docs/specs/metadata-standards.md; #1360)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from requirement_sets import ORDA, pinned, standard, write
from test_deposit import FILES

from dd_harness.deposit import VIOLATION, build_package, validate
from dd_harness.projects import APPROVED, Decision, ProjectStore
from dd_harness.requirements import load_requirements
from dd_harness.store import RunStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    clear_review,
    document_request,
    file_inventory,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind

OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"
XML = "application/xml"


def dublin_core(**changes: Any) -> dict[str, Any]:
    return {
        "schema_class": "RequirementSet",
        "requirement_set_id": "dublin-core",
        "version": 1,
        "title": "Dublin Core (OAI-DC)",
        "url": "https://www.dublincore.org/specifications/dublin-core/dces/",
        "conforms_to": OAI_DC,
        "re3data_names": ["Dublin Core"],
        "fields": [
            {"property": "title", "obligation": "required"},
            {"property": "creator", "obligation": "required"},
            {"property": "description", "obligation": "recommended"},
        ],
        "required_documents": ["metadata_record"],
        **changes,
    }


def record(*, title: str | None = "Soil cores from Hope Valley") -> str:
    elements = [
        f"<dc:title>{title}</dc:title>" if title else "<dc:title>:unav</dc:title>",
        "<dc:creator>Carberry, Josiah</dc:creator>",
        "<dc:description>Cores taken in 2026.</dc:description>",
        "<dc:rights>https://creativecommons.org/licenses/by/4.0/</dc:rights>",
    ]
    return (
        f'<oai_dc:dc xmlns:oai_dc="{OAI_DC}" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        + "".join(elements)
        + "</oai_dc:dc>"
    )


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def runs(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


@pytest.fixture
def chosen(projects: ProjectStore, tmp_path: Path) -> str:
    """A project with ORDA chosen, which re3data lists as declaring Dublin Core, and no override."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    projects.add_inventory(
        project_id, file_inventory(*FILES), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    folder = tmp_path / "repositories"
    write(folder, ("standards", standard()), ("standards", dublin_core()))
    projects.choose_repository(
        project_id,
        ORDA,
        registry=pinned(folder / "re3data"),
        requirements=load_requirements(folder),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    return project_id


def approve(
    projects: ProjectStore,
    runs: RunStore,
    project_id: str,
    kind: DocumentKind,
    text: str | None = None,
) -> None:
    stub = DocumentStub(record_standard=(OAI_DC, XML))
    conductor = make_conductor(runs.root, stub, crate=True)
    envelope = conductor.invoke(
        request("stub.document", document_request(kind)), acting_for=TEST_PRINCIPAL
    )
    ref = projects.record_draft(project_id, envelope)
    (document,) = [d for d in projects.documents(project_id) if d["document_id"] == ref.document_id]
    digest = document["versions"][-1]["digest"]
    decision = Decision(
        ref.document_id,
        ref.version,
        digest,
        APPROVED,
        reason="Written in OAI-DC." if text is not None else None,
        edited_text=text,
    )
    projects.decide(project_id, decision, acted_for=TEST_PRINCIPAL, caused_by="test")


def test_a_repository_that_declares_dublin_core_is_checked_against_its_set(
    projects: ProjectStore, chosen: str
) -> None:
    (event,) = [e for e in projects.events(chosen) if e["event"] == "repository_chosen"]
    assert [s["ref"].partition("@")[0] for s in event["requirement_sets"]] == ["dublin-core"]
    assert event["standard"]["ref"].startswith("dublin-core-oai@v")
    assert event["standard"]["codecs"] == {XML: "xml-indent-2"}
    assert not any("DataCite" in w for w in event["warnings"])


def test_an_oai_dc_record_is_validated_through_its_definition(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, record())
    validation = validate(projects, chosen)
    assert not [r for r in validation.violations if r.field in {"title", "creator"}]


def test_a_gap_in_a_required_element_is_a_violation(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    """A gap (`:unav`) is no value (invariant 6), so the required title is missing."""
    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, record(title=None))
    violations = [r for r in validate(projects, chosen).results if r.severity == VIOLATION]
    assert [r.field for r in violations if r.field == "title"] == ["title"]


def test_the_package_keeps_the_record_as_xml_and_describes_the_dataset_from_it(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, record())
    approve(projects, runs, chosen, DocumentKind.README)
    clear_review(projects, chosen, acted_for=TEST_PRINCIPAL)
    package = build_package(projects, runs, chosen, acted_for=TEST_PRINCIPAL, caused_by="test")
    archive = zipfile.ZipFile(io.BytesIO(package.content))
    kept = [n for n in archive.namelist() if n.startswith("documents/metadata_record-")]
    assert len(kept) == 1 and kept[0].endswith(".xml")
    assert archive.read(kept[0]).decode() == record()
    graph = {e["@id"]: e for e in json.loads(archive.read("ro-crate-metadata.json"))["@graph"]}
    root = graph["./"]
    assert root["name"] == "Soil cores from Hope Valley"
    assert root["description"] == "Cores taken in 2026."
    assert root["license"] == {"@id": "https://creativecommons.org/licenses/by/4.0/"}
