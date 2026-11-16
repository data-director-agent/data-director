"""advisor.files through the conductor: the File Archivist mock (docs/specs/agents.md)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import dd_agent_advisor_files
from dd_agent_advisor_files.agent import LIMITATIONS, UNKNOWN, FileArchivist
from dd_agent_advisor_files.classes import CheckKind, FormatAssessment, JudgedBy
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import (
    FileInventory,
    GroundingMode,
    IdentificationMethod,
    InventoryFile,
    OutcomeStatus,
    ReasonCode,
    TableField,
)
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_files.__file__).parent / "schema" / "files.yaml"


def sample() -> FileInventory:
    return FileInventory.model_validate(
        json.loads((SAMPLES / "soil-survey.inventory.json").read_text(encoding="utf-8"))
    )


def inventory(*files: tuple[str, str | None]) -> FileInventory:
    return of_files(
        *(
            InventoryFile(
                file_path=path,
                file_size=1,
                file_sha256=f"{n:064x}",
                file_media_type=media_type,
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for n, (path, media_type) in enumerate(files)
        )
    )


def of_files(*files: InventoryFile) -> FileInventory:
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 10, 30, tzinfo=UTC),
        inventory_files=list(files),
    )


def file(
    path: str, *, size: int = 10, digest: int | None = None, fields: tuple[str, ...] = ()
) -> InventoryFile:
    return InventoryFile(
        file_path=path,
        file_size=size,
        file_sha256=f"{digest if digest is not None else hash(path) & 0xFFFF:064x}",
        file_identified_by=IdentificationMethod.EXTENSION,
        file_fields=[TableField(name=n, field_type="string") for n in fields],
    )


def moorland() -> FileInventory:
    """Shaped like dataset A of data-director-agent/sample-data, whose problems are in contents."""
    return of_files(
        file("analysis/plot_temp_gradient.R"),
        file("calibration/sites.csv", fields=("node", "lat", "lon", "elev")),
        file("data/N01-N06_v3.csv", fields=("timestamp_utc", "node_id", "ta", "rh")),
        file("data/Thumbs.db", size=0),
        file("data/logger_export.csv", digest=7, fields=("Date", "Node", "T_air")),
        file("data/old/logger_export (copy).csv", digest=7, fields=("Date", "Node", "T_air")),
        file("fieldnotes/fieldnotes_2024.txt"),
        file("governance/landowner-access-agreement.md"),
        file("reference/WeatherNest_Stn442_hourly.csv", fields=("time", "temp")),
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
    assert payload.checks == []


def test_asks_a_person_to_look_at_files_whose_names_call_for_it(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, FileArchivist()).invoke(
        request("advisor.files", moorland()), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    checks = env.payload_as(FormatAssessment).checks
    assert {(c.path, c.kind) for c in checks} == {
        ("calibration/sites.csv", CheckKind.COORDINATES),
        ("data/Thumbs.db", CheckKind.SYSTEM_FILE),
        ("data/Thumbs.db", CheckKind.EMPTY),
        ("data/logger_export.csv", CheckKind.DUPLICATE),
        ("data/old/logger_export (copy).csv", CheckKind.DUPLICATE),
        ("fieldnotes/fieldnotes_2024.txt", CheckKind.FREE_TEXT),
        ("governance/landowner-access-agreement.md", CheckKind.GOVERNANCE),
        ("reference/WeatherNest_Stn442_hourly.csv", CheckKind.THIRD_PARTY),
    }
    assert all(c.question for c in checks)


def test_a_duplicate_names_its_copies() -> None:
    files = of_files(file("a.csv", digest=1), file("b/a.csv", digest=1), file("c.csv", digest=1))
    checks = FileArchivist()._checks(files.inventory_files)
    assert {c.path: set(c.related_paths) for c in checks} == {
        "a.csv": {"b/a.csv", "c.csv"},
        "b/a.csv": {"a.csv", "c.csv"},
        "c.csv": {"a.csv", "b/a.csv"},
    }


def test_empty_files_are_not_copies_of_each_other() -> None:
    files = of_files(file("a.txt", size=0, digest=3), file("b.txt", size=0, digest=3))
    kinds = {c.kind for c in FileArchivist()._checks(files.inventory_files)}
    assert kinds == {CheckKind.EMPTY}


@pytest.mark.parametrize(
    "name", ["notes_lat.csv", "translation.txt", "logger_export.csv", "longitudinal.csv"]
)
def test_words_are_matched_whole_not_inside_other_words(name: str) -> None:
    files = of_files(file(f"data/{name}", fields=("translated", "salon", "plateau")))
    kinds = {c.kind for c in FileArchivist()._checks(files.inventory_files)}
    assert CheckKind.COORDINATES not in kinds
    assert (CheckKind.FREE_TEXT in kinds) == name.startswith("notes")


def test_no_check_is_not_presented_as_clearance(runs_dir: Path) -> None:
    files = inventory(("README.md", "text/markdown"), ("data/readings.csv", "text/csv"))
    env = make_conductor(runs_dir, FileArchivist()).invoke(
        request("advisor.files", files), acting_for=TEST_PRINCIPAL
    )
    payload = env.payload_as(FormatAssessment)
    assert payload.checks == []
    assert set(LIMITATIONS) <= set(payload.limitations)


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
