"""advisor.files through the conductor: the File Archivist mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_files
from dd_agent_advisor_files.agent import UNKNOWN, FileArchivist
from dd_agent_advisor_files.classes import FileInventory, FileList
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_files.__file__).parent / "schema" / "files.yaml"


def sample() -> FileList:
    return FileList.model_validate(
        json.loads((SAMPLES / "files-list.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_lists_each_file_with_the_format_its_extension_suggests(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, FileArchivist())
    env = conductor.invoke(request("advisor.files", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(FileInventory)
    assert [(e.extension, e.format_name, e.open_format) for e in payload.entries] == [
        ("md", "Markdown", True),
        ("sav", "SPSS data file", False),
        ("csv", "Comma-separated values", True),
        ("docx", "Microsoft Word (OOXML)", True),
        ("rdx", UNKNOWN, False),
    ]
    assert payload.entries[-1].media_type is None
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-OUTCOME")
def test_no_files_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, FileArchivist()).invoke(
        request("advisor.files", FileList()), acting_for=TEST_PRINCIPAL
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
