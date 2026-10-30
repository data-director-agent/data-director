"""advisor.files through the conductor: the File Archivist mock (ADR-0033)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import dd_agent_advisor_files
from dd_agent_advisor_files.agent import UNKNOWN, FileArchivist
from dd_agent_advisor_files.classes import FormatAssessment, JudgedBy
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import (
    FileInventory,
    GroundingMode,
    IdentificationMethod,
    InventoryFile,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_files.__file__).parent / "schema" / "files.yaml"


def sample() -> FileInventory:
    return FileInventory.model_validate(
        json.loads((SAMPLES / "soil-survey.inventory.json").read_text(encoding="utf-8"))
    )


def inventory(*files: tuple[str, str | None]) -> FileInventory:
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 10, 30, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path=path,
                file_size=1,
                file_sha256="0" * 64,
                file_media_type=media_type,
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for path, media_type in files
        ],
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_judges_each_file_of_the_inventory_by_its_media_type(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, FileArchivist())
    env = conductor.invoke(request("advisor.files", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(FormatAssessment)
    assert [(a.path, a.format_name, a.open_format, a.judged_by) for a in payload.assessments] == [
        ("README.md", "Markdown", True, JudgedBy.MEDIA_TYPE),
        ("data/readings.csv", "Comma-separated values", True, JudgedBy.MEDIA_TYPE),
        ("data/sites.tsv", "Tab-separated values", True, JudgedBy.MEDIA_TYPE),
        ("docs/protocol.pdf", "PDF", True, JudgedBy.MEDIA_TYPE),
        ("docs/site-map.png", "PNG", True, JudgedBy.MEDIA_TYPE),
    ]
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


def test_falls_back_to_the_extension_and_says_when_nothing_is_known(runs_dir: Path) -> None:
    files = inventory(
        ("data/survey_responses.sav", None),
        ("data/old.DOC", "application/x-unrecognised"),
        ("analysis/model_output.rdx", None),
    )
    env = make_conductor(runs_dir, FileArchivist()).invoke(
        request("advisor.files", files), acting_for=TEST_PRINCIPAL
    )
    payload = env.payload_as(FormatAssessment)
    assert [
        (a.extension, a.format_name, a.open_format, a.judged_by) for a in payload.assessments
    ] == [
        ("sav", "SPSS data file", False, JudgedBy.EXTENSION),
        ("doc", "Microsoft Word 97-2003", False, JudgedBy.EXTENSION),
        ("rdx", UNKNOWN, False, JudgedBy.NOTHING),
    ]
    assert payload.assessments[1].media_type == "application/x-unrecognised"
    assert payload.assessments[2].media_type is None
    assert env.outcome.statement is not None
    assert env.outcome.statement.startswith("Mock: 3 of 3 files")


@pytest.mark.requirement("DD-OUTCOME")
def test_an_empty_inventory_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, FileArchivist()).invoke(
        request("advisor.files", inventory()), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_the_card_names_the_persona_and_its_step() -> None:
    entry = describe(FileArchivist.spec)
    assert entry["title"] == "File Archivist"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["preparation.files"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
