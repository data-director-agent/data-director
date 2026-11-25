"""An approved metadata record converted to another standard, kept as a package derived from it
(docs/specs/metadata-standards.md, invariant 9; #1363)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from requirement_sets import standard, write
from test_deposit import RECORD, approve

from dd_harness.conversion import (
    METADATA_RECORD,
    ConversionError,
    Converted,
    Refused,
    conversions,
    convert_record,
)
from dd_harness.projects import PACKAGE_BUILT, ProjectStore
from dd_harness.requirements import Requirements, load_requirements
from dd_harness.store import RunStore
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import DocumentKind

OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DATACITE = "http://datacite.org/schema/kernel-4"


def dublin_core(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return standard(
        requirement_set_id="dublin-core",
        title="Dublin Core (OAI-DC)",
        conforms_to=OAI_DC,
        re3data_names=["Dublin Core"],
        fields=fields,
    )


def requirements(tmp_path: Path, fields: list[dict[str, Any]]) -> Requirements:
    root = write(
        tmp_path / "repositories", ("standards", standard()), ("standards", dublin_core(fields))
    )
    return load_requirements(root)


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def approved(projects: ProjectStore, tmp_path: Path) -> str:
    """A project with RECORD approved as its DataCite metadata record."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    approve(
        projects,
        RunStore(tmp_path / "runs"),
        project_id,
        DocumentKind.METADATA_RECORD,
        json.dumps(RECORD),
    )
    return project_id


def test_a_conversion_is_kept_as_a_package_derived_from_the_approved_record(
    projects: ProjectStore, approved: str, tmp_path: Path
) -> None:
    sets = requirements(tmp_path, [{"property": "title", "obligation": "required"}])
    converted = convert_record(
        projects, approved, OAI_DC, requirements=sets, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert isinstance(converted, Converted)
    text = projects.package(approved, converted.digest)
    assert text is not None and b"<dc:title>Soil cores from Hope Valley</dc:title>" in text
    (event,) = conversions(projects, approved)
    assert event["event"] == PACKAGE_BUILT and event["format"] == METADATA_RECORD
    assert (event["conforms_to"], event["media_type"]) == (OAI_DC, "application/xml")
    record = projects.metadata_record(approved)
    assert record is not None
    # It names the record it came from, and both standards' definitions.
    assert event["derived_from"] == hashlib.sha256(record["document_text"].encode()).hexdigest()
    assert event["documents"] == [record["version_ref"]]
    assert event["standards"]["source"]["ref"].startswith("datacite-4@v")
    assert event["standards"]["target"]["ref"].startswith("dublin-core-oai@v")
    # Every value it could not place, or placed less precisely, is named.
    assert "rightsList" not in event["unplaced"]
    assert any(r["path"] == "rightsList" for r in event["reduced"])


def test_a_conversion_that_would_leave_a_required_field_empty_is_refused(
    projects: ProjectStore, approved: str, tmp_path: Path
) -> None:
    sets = requirements(
        tmp_path,
        [
            {"property": "title", "obligation": "required"},
            {"property": "language", "obligation": "required"},
        ],
    )
    refused = convert_record(
        projects, approved, OAI_DC, requirements=sets, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert isinstance(refused, Refused)
    assert [m["property"] for m in refused.missing] == ["language"]
    assert refused.missing[0]["question"]
    # Nothing is kept.
    assert conversions(projects, approved) == []


def test_a_conversion_needs_an_approved_record_and_another_registered_standard(
    projects: ProjectStore, approved: str, tmp_path: Path
) -> None:
    sets = requirements(tmp_path, [{"property": "title", "obligation": "required"}])
    empty = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Empty")
    asked: dict[str, Any] = {"requirements": sets, "acted_for": TEST_PRINCIPAL, "caused_by": "test"}
    with pytest.raises(ConversionError, match="no approved metadata record"):
        convert_record(projects, empty, OAI_DC, **asked)
    with pytest.raises(ConversionError, match="already in DataCite"):
        convert_record(projects, approved, DATACITE, **asked)
    with pytest.raises(ConversionError, match="no registered standard"):
        convert_record(projects, approved, "https://ddialliance.org/", **asked)
