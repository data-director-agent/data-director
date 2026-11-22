"""advisor.files through the conductor: the File Archivist (docs/specs/agents.md)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import dd_agent_advisor_files
import dd_formats
from dd_agent_advisor_files.agent import LIMITATIONS, UNKNOWN, FileArchivist, load_formats
from dd_agent_advisor_files.classes import CheckKind, FormatAssessment, JudgedBy
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import (
    EvidenceItem,
    FileInventory,
    GroundingMode,
    IdentificationMethod,
    InventoryFile,
    OutcomeStatus,
    ReasonCode,
    TableField,
)
from dd_sdk.evidence import verify
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
    path: str,
    *,
    size: int = 10,
    digest: int | None = None,
    fields: tuple[str, ...] = (),
    pronom: tuple[str, ...] = (),
    media_type: str | None = None,
) -> InventoryFile:
    return InventoryFile(
        file_path=path,
        file_size=size,
        file_sha256=f"{digest if digest is not None else hash(path) & 0xFFFF:064x}",
        file_media_type=media_type,
        file_pronom_ids=list(pronom),
        file_identified_by=IdentificationMethod.SIGNATURE
        if pronom
        else IdentificationMethod.EXTENSION,
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


def _record_name(puid: str) -> str:
    record = dd_formats.lookup(puid)
    assert record is not None
    return record.name


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_describes_each_file_from_the_pronom_record_of_its_identification(
    runs_dir: Path,
) -> None:
    conductor = make_conductor(runs_dir, FileArchivist())
    env = conductor.invoke(request("advisor.files", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.RETRIEVAL
    payload = env.payload_as(FormatAssessment)
    for a, given in zip(payload.assessments, sample().inventory_files, strict=True):
        assert a.judged_by == JudgedBy.PRONOM
        assert a.pronom_id == given.file_pronom_ids[0]
        assert a.format_name.startswith(_record_name(a.pronom_id))
        assert a.open_format is True
        assert [g.source_id for g in a.grounded_on] == [a.pronom_id]
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


def test_each_record_cited_is_in_the_evidence_and_rehashes(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, FileArchivist()).invoke(
        request("advisor.files", sample()), acting_for=TEST_PRINCIPAL
    )
    payload = env.payload_as(FormatAssessment)
    evidence: dict[tuple[str, str], EvidenceItem] = {
        (e.source_id, e.content_hash): e for e in env.evidence
    }
    for ref in (g for a in payload.assessments for g in a.grounded_on):
        item = evidence[(ref.source_id, ref.content_hash)]
        assert item.content is not None and item.snapshot_ref
        assert verify(item.content, item.canonicalisation, item.content_hash)
        assert ref in payload.grounded_on


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
        ("rdx", UNKNOWN, None, JudgedBy.NOTHING),
    ]
    assert payload.assessments[1].media_type == "application/x-unrecognised"
    assert payload.assessments[2].media_type is None
    assert payload.checks == []
    # Identified by extension only: no PRONOM record is cited.
    assert all(a.grounded_on == [] and a.pronom_id is None for a in payload.assessments)


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


def test_asks_a_person_whether_a_configuration_file_holds_credentials(runs_dir: Path) -> None:
    """A workshop dataset's `config.ini` held credentials and was not flagged (#1320)."""
    files = of_files(
        file("README.md"),
        file("config.ini"),
        file("data/survey_responses.csv", fields=("respondent", "q1", "q2")),
        file("scripts/clean.py"),
    )
    env = make_conductor(runs_dir, FileArchivist()).invoke(
        request("advisor.files", files), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    checks = env.payload_as(FormatAssessment).checks
    flagged = [c for c in checks if c.kind == CheckKind.CREDENTIALS]
    assert [c.path for c in flagged] == ["config.ini"]
    assert flagged[0].question


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
    assert not entry["description"].startswith("Mock.")
    assert entry["serves"] == ["preparation.files"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"


def test_pronom_identification_is_preferred_to_media_type_and_extension() -> None:
    files = of_files(file("data/export.dat", pronom=("x-fmt/18",), media_type="text/plain"))
    assessment = FileArchivist()._assess(files.inventory_files[0])
    assert assessment.format_name == _record_name("x-fmt/18")
    assert (assessment.judged_by, assessment.pronom_id) == (JudgedBy.PRONOM, "x-fmt/18")


def test_the_first_identifier_the_release_has_is_used() -> None:
    assessment = FileArchivist()._assess(file("a.bin", pronom=("fmt/999999", "fmt/276")))
    assert assessment.pronom_id == "fmt/276"
    assert assessment.format_name.startswith(_record_name("fmt/276"))


def test_a_deprecated_identifier_is_described_by_the_record_that_replaces_it() -> None:
    old = next(r for r in dd_formats.records() if r.superseded_by == "fmt/353")
    assessment = FileArchivist()._assess(file("scan.tif", pronom=(old.puid,)))
    assert assessment.pronom_id == "fmt/353"
    assert [g.source_id for g in assessment.grounded_on] == ["fmt/353"]


def test_an_identifier_the_release_lacks_is_reported_as_such() -> None:
    assessment = FileArchivist()._assess(
        file("data/readings.csv", pronom=("fmt/999999",), media_type="text/csv")
    )
    assert assessment.judged_by == JudgedBy.PRONOM_UNLISTED
    assert assessment.pronom_id == "fmt/999999"
    assert assessment.format_name == UNKNOWN
    assert assessment.open_format is None
    assert assessment.grounded_on == []


def test_a_format_the_table_does_not_judge_is_described_but_not_judged() -> None:
    table = load_formats()
    unjudged = next(r for r in dd_formats.records() if r.puid not in table.open)
    assessment = FileArchivist()._assess(file("x.bin", pronom=(unjudged.puid,)))
    assert assessment.judged_by == JudgedBy.PRONOM
    assert assessment.format_name != UNKNOWN
    assert assessment.open_format is None


def test_content_that_disagrees_with_the_extension_is_a_check() -> None:
    files = of_files(
        file("data/readings.csv", pronom=("fmt/18",)),
        file("data/other.csv", pronom=("x-fmt/18",)),
        file("data/odd.dat", pronom=("x-fmt/18",)),
    )
    checks = FileArchivist()._checks(files.inventory_files)
    assert [(c.path, c.kind, c.matched) for c in checks] == [
        ("data/readings.csv", CheckKind.EXTENSION_MISMATCH, "csv")
    ]
    assert checks[0].question


def test_every_puid_the_table_judges_is_a_current_record_of_the_release() -> None:
    for puid in load_formats().open:
        record = dd_formats.lookup(puid)
        assert record is not None, puid
        assert record.puid == puid, f"{puid} is deprecated in favour of {record.puid}"


@pytest.mark.parametrize(
    ("path", "pronom"),
    [
        ("analysis/plot_temp_gradient.R", ("fmt/1599",)),
        ("analysis/fit.py", ("fmt/938", "fido-fmt/python")),
        ("analysis/run.sh", ()),
        ("analysis/model.jl", ()),
    ],
)
def test_code_is_an_open_format(path: str, pronom: tuple[str, ...]) -> None:
    # #1071: as the inventory identifies a script, by PRONOM or by extension alone.
    assessment = FileArchivist()._assess(file(path, pronom=pronom))
    assert assessment.format_name != UNKNOWN
    assert assessment.open_format
