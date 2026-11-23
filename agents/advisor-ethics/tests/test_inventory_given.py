"""advisor.ethics given a project's inventory (`GivenProjectInventory`, #1540): it checks the
tables' field names and the file and folder names, says where each flagged name appears, and
carries over what the inventory's personal data detector found, keeping "no detector ran" apart
from "found nothing" (docs/specs/personal-data.md)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from dd_agent_advisor_ethics.agent import (
    DETECTOR_LIMITATION,
    NO_DETECTOR_LIMITATION,
    NO_INVENTORY_LIMITATION,
    EthicsAdviser,
)
from dd_agent_advisor_ethics.classes import SensitivityContext, SensitivityFlags
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.inventory import (
    ConfidenceBand,
    FileInventory,
    FindingTarget,
    IdentificationMethod,
    InventoryFile,
    PersonalDataFinding,
    PersonalDataKind,
    TableField,
)
from dd_sdk.contract.models import Derivation, OutcomeStatus

FINDING = PersonalDataFinding(
    finding_kind=PersonalDataKind.EMAIL_ADDRESS,
    finding_file="notes/lab_notebook.md",
    finding_target=FindingTarget.TEXT,
    finding_confidence=ConfidenceBand.HIGH,
    finding_detector="presidio",
)


def file(path: str, *fields: str) -> InventoryFile:
    return InventoryFile(
        file_path=path,
        file_size=10,
        file_sha256=hashlib.sha256(path.encode()).hexdigest(),
        file_media_type="text/csv" if fields else "text/markdown",
        file_identified_by=IdentificationMethod.EXTENSION,
        file_fields=[TableField(name=name) for name in fields],
    )


def inventory(found: list[PersonalDataFinding] | None) -> FileInventory:
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 11, 1, tzinfo=UTC),
        inventory_files=[
            file("sample_log.csv", "sample_id", "mn_content", "operator_email"),
            file("notes/lab_notebook.md"),
        ],
        inventory_personal_data=found,
    )


def run(context: SensitivityContext, runs_dir: Path) -> SensitivityFlags:
    env = make_conductor(runs_dir, EthicsAdviser()).invoke(
        request("advisor.ethics", context), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(SensitivityFlags)


def test_an_inventory_alone_is_enough_to_check_and_its_field_names_are_flagged(
    runs_dir: Path,
) -> None:
    payload = run(SensitivityContext(project_file_inventory=inventory([FINDING])), runs_dir)

    (flag,) = [f for f in payload.flags if f.field == "operator_email"]
    assert flag.derivation == Derivation.LEXICAL
    assert flag.files == ["sample_log.csv"]


def test_the_detectors_findings_are_carried_over_and_raise_a_question(runs_dir: Path) -> None:
    payload = run(SensitivityContext(project_file_inventory=inventory([FINDING])), runs_dir)

    assert payload.inventory_findings == [FINDING]
    assert DETECTOR_LIMITATION in payload.limitations
    assert any(str(FINDING.finding_kind) in q.text for q in payload.questions)


def test_files_whose_names_suggest_free_text_are_named_for_a_person_to_read(
    runs_dir: Path,
) -> None:
    payload = run(SensitivityContext(project_file_inventory=inventory([])), runs_dir)

    assert any("notes/lab_notebook.md" in q.text for q in payload.questions)


def test_no_detector_and_nothing_found_are_kept_apart(runs_dir: Path) -> None:
    none_ran = run(SensitivityContext(project_file_inventory=inventory(None)), runs_dir)
    nothing_found = run(SensitivityContext(project_file_inventory=inventory([])), runs_dir)

    assert none_ran.inventory_findings is None
    assert NO_DETECTOR_LIMITATION in none_ran.limitations
    assert nothing_found.inventory_findings == []
    assert DETECTOR_LIMITATION in nothing_found.limitations


def test_without_an_inventory_it_says_one_would_check_more(runs_dir: Path) -> None:
    payload = run(SensitivityContext(fields=["sample_id"]), runs_dir)

    assert payload.inventory_findings is None
    assert NO_INVENTORY_LIMITATION in payload.limitations


def test_a_name_given_by_the_caller_and_the_inventory_is_checked_once(runs_dir: Path) -> None:
    context = SensitivityContext(fields=["operator_email"], project_file_inventory=inventory(None))
    payload = run(context, runs_dir)

    flagged = [f.field for f in payload.flags]
    assert flagged.count("operator_email") == 1
