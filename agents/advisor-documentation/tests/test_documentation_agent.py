"""advisor.documentation through the conductor: the Documentation Editor mock
(docs/specs/agents.md) as the stub drafter of the README and the data dictionary (#200)."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pytest

from dd_agent_advisor_documentation.agent import (
    DICTIONARY_COLUMNS,
    VALUE_COLUMNS,
    DocumentationEditor,
    Source,
)
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import (
    CurrentVersion,
    Document,
    DocumentKind,
    DocumentVersionRef,
    DraftAnswer,
    DraftRequest,
    Envelope,
    GroundingMode,
    OutcomeStatus,
    ReasonCode,
    VersionState,
    new_invocation_id,
)

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"


def sample(name: str) -> DraftRequest:
    return DraftRequest.model_validate_json((SAMPLES / name).read_text(encoding="utf-8"))


def draft(runs_dir: Path, asked: DraftRequest) -> tuple[Envelope, bool]:
    conductor = make_conductor(runs_dir, DocumentationEditor())
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    return env, conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_drafts_a_readme_from_the_inventory_and_marks_the_rest(runs_dir: Path) -> None:
    asked = sample("soil-survey.readme.draft.json")
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE and grounded
    document = env.payload_as(Document)
    assert document.document_kind == DocumentKind.README
    assert document.media_type == "text/markdown"
    assert document.revises is None
    text = document.document_text
    headings = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "General information",
        "Description",
        "Files",
        "Methods",
        "Variables",
        "Access and licence",
        "How to cite",
        "Software requirements",
    ]
    assert text.count("_To be written by the researcher:") == len(headings)
    assert asked.inventory is not None
    for f in asked.inventory.inventory_files:
        assert f"`{f.file_path}`" in text
        for field in f.file_fields:
            assert f"`{field.name}`" in text
    assert asked.requirements is not None and asked.requirements.licences
    assert f"`{asked.requirements.licences[0]}`" in text
    assert env.outcome.statement.startswith("Mock:")


def test_drafts_a_data_dictionary_with_a_row_per_field(runs_dir: Path) -> None:
    asked = sample("soil-survey.data-dictionary.draft.json")
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    document = env.payload_as(Document)
    assert (document.document_kind, document.media_type) == (
        DocumentKind.DATA_DICTIONARY,
        "text/csv",
    )
    rows = list(csv.DictReader(io.StringIO(document.document_text)))
    assert asked.inventory is not None
    expected = [
        (f.file_path, c.name) for f in asked.inventory.inventory_files for c in f.file_fields
    ]
    assert [(r["file"], r["field"]) for r in rows] == expected
    assert tuple(rows[0]) == DICTIONARY_COLUMNS
    for r in rows:
        assert {r[f"{c}_source"] for c in VALUE_COLUMNS} <= set(Source)
        assert r["type_source"] == (Source.INFERRED if r["type"] else Source.UNKNOWN)
        for column in ("unit", "missing_values"):
            assert (r[column], r[f"{column}_source"]) == ("", Source.UNKNOWN)
    assert "inferred from the inventory" in env.outcome.statement


def regenerate(runs_dir: Path, earlier: str) -> list[dict[str, str]]:
    """The rows of a data dictionary regenerated from an earlier version with this CSV text."""
    asked = sample("soil-survey.data-dictionary.draft.json").model_copy(
        update={
            "current_version": CurrentVersion(
                version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=1),
                document_title="Data dictionary",
                media_type="text/csv",
                document_text=earlier,
                version_state=VersionState.PROPOSED,
            )
        }
    )
    env, _ = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return list(csv.DictReader(io.StringIO(env.payload_as(Document).document_text)))


def first_rows(runs_dir: Path) -> list[dict[str, str]]:
    env, _ = draft(runs_dir, sample("soil-survey.data-dictionary.draft.json"))
    return list(csv.DictReader(io.StringIO(env.payload_as(Document).document_text)))


def write_csv(rows: list[dict[str, str]], columns: tuple[str, ...]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def test_regenerating_keeps_what_the_researcher_supplied(runs_dir: Path) -> None:
    rows = first_rows(runs_dir)
    assert len(rows) >= 2
    rows[0] |= {"unit": "pH units", "description": "Soil acidity", "missing_values": "-99"}
    rows[1] |= {"type": "string"}  # the researcher corrects an inferred type
    again = regenerate(runs_dir, write_csv(rows, DICTIONARY_COLUMNS))
    assert [(r["file"], r["field"]) for r in again] == [(r["file"], r["field"]) for r in rows]
    for column in ("unit", "description", "missing_values"):
        assert (again[0][column], again[0][f"{column}_source"]) == (rows[0][column], "supplied")
    assert (again[1]["type"], again[1]["type_source"]) == ("string", "supplied")
    assert again[2:] == rows[2:]
    assert again[0]["type_source"] == rows[0]["type_source"]


def test_a_hand_made_dictionary_is_all_supplied(runs_dir: Path) -> None:
    rows = first_rows(runs_dir)
    rows[0] |= {"unit": "cm"}
    again = regenerate(runs_dir, write_csv(rows, ("file", "field", "type", "unit")))
    assert (again[0]["unit"], again[0]["unit_source"]) == ("cm", "supplied")
    # A value equal to the inventory's keeps the inventory's source.
    assert again[0]["type_source"] == rows[0]["type_source"]


def test_regenerating_names_the_version_it_replaces(runs_dir: Path) -> None:
    previous = DocumentVersionRef(document_id=new_invocation_id(), version=2)
    asked = sample("soil-survey.readme.draft.json").model_copy(
        update={
            "current_version": CurrentVersion(
                version_ref=previous,
                document_title="README for the soil survey",
                media_type="text/markdown",
                document_text="# README\n",
                version_state=VersionState.REJECTED,
                decision_reason="The files table is missing.",
            )
        }
    )
    env, _ = draft(runs_dir, asked)
    document = env.payload_as(Document)
    assert document.revises == previous
    assert document.document_title == "README for the soil survey"
    assert "replaces version 2" in env.outcome.statement


@pytest.mark.requirement("DD-OUTCOME")
@pytest.mark.parametrize(
    ("asked", "reason"),
    [
        (DraftRequest(document_kind=DocumentKind.README), ReasonCode.INSUFFICIENT_INPUT),
        (
            DraftRequest(document_kind=DocumentKind.METADATA_RECORD),
            ReasonCode.OUTSIDE_AGENT_SCOPE,
        ),
    ],
)
def test_abstains_without_an_inventory_or_for_another_kind(
    runs_dir: Path, asked: DraftRequest, reason: ReasonCode
) -> None:
    env, _ = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == reason


def test_no_table_no_data_dictionary(runs_dir: Path) -> None:
    asked = sample("soil-survey.data-dictionary.draft.json")
    assert asked.inventory is not None
    files = [f.model_copy(update={"file_fields": []}) for f in asked.inventory.inventory_files]
    inventory = asked.inventory.model_copy(update={"inventory_files": files})
    env, _ = draft(runs_dir, asked.model_copy(update={"inventory": inventory}))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(DocumentationEditor.spec)
    assert entry["title"] == "Documentation Editor"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["setup.documentation", "preparation.documentation"]
    json.dumps(entry)


def asked_with(name: str, *answers: tuple[str, str]) -> DraftRequest:
    given = [DraftAnswer(answered_question=q, answer_text=a) for q, a in answers]
    return sample(name).model_copy(update={"draft_answers": given})


@pytest.mark.requirement("R5")
def test_every_readme_gap_is_marked_and_asked_once(runs_dir: Path) -> None:
    env, _ = draft(runs_dir, sample("soil-survey.readme.draft.json"))
    document = env.payload_as(Document)
    markers = re.findall(r"<!-- dd:gap (q-[0-9a-f]{16}) -->", document.document_text)
    questions = document.document_questions
    assert markers == [q.question_id for q in questions]
    assert len(markers) == document.document_text.count("_To be written by the researcher:")
    headings = [line[3:] for line in document.document_text.splitlines() if line.startswith("## ")]
    assert [q.gap_section for q in questions] == headings
    assert f"leaves {len(questions)} gaps" in env.outcome.statement


@pytest.mark.requirement("R5")
def test_every_unknown_dictionary_cell_is_asked_once(runs_dir: Path) -> None:
    env, _ = draft(runs_dir, sample("soil-survey.data-dictionary.draft.json"))
    document = env.payload_as(Document)
    rows = list(csv.DictReader(io.StringIO(document.document_text)))
    unknown = [
        (r["file"], r["field"], c)
        for r in rows
        for c in VALUE_COLUMNS
        if r[f"{c}_source"] == Source.UNKNOWN
    ]
    asked = [(q.gap_file, q.gap_field, q.gap_column) for q in document.document_questions]
    assert asked == unknown and unknown
    assert f"asks {len(unknown)} questions" in env.outcome.statement


def test_a_gap_is_asked_under_the_same_identifier_in_every_version(runs_dir: Path) -> None:
    for name in ("soil-survey.readme.draft.json", "soil-survey.data-dictionary.draft.json"):
        first, _ = draft(runs_dir, sample(name))
        again, _ = draft(runs_dir, sample(name))
        ids = [q.question_id for q in first.payload_as(Document).document_questions]
        assert ids == [q.question_id for q in again.payload_as(Document).document_questions]


@pytest.mark.requirement("R5")
def test_an_answer_is_placed_as_given_and_marked_supplied(runs_dir: Path) -> None:
    name = "soil-survey.data-dictionary.draft.json"
    env, _ = draft(runs_dir, sample(name))
    question = next(
        q for q in env.payload_as(Document).document_questions if q.gap_column == "unit"
    )
    answer = "  mg/kg, dry weight "
    env, _ = draft(runs_dir, asked_with(name, (question.question_id, answer)))
    document = env.payload_as(Document)
    row = next(
        r
        for r in csv.DictReader(io.StringIO(document.document_text))
        if (r["file"], r["field"]) == (question.gap_file, question.gap_field)
    )
    assert (row["unit"], row["unit_source"]) == (answer, Source.SUPPLIED)
    assert question.question_id not in {q.question_id for q in document.document_questions}


def test_an_answered_readme_gap_holds_the_answer_and_no_marker(runs_dir: Path) -> None:
    name = "soil-survey.readme.draft.json"
    env, _ = draft(runs_dir, sample(name))
    methods = next(
        q for q in env.payload_as(Document).document_questions if q.gap_section == "Methods"
    )
    answer = "Cores were taken at 0 to 10 cm and air-dried."
    env, _ = draft(runs_dir, asked_with(name, (methods.question_id, answer)))
    document = env.payload_as(Document)
    section = document.document_text.split("## Methods\n\n", 1)[1].split("\n\n## ", 1)[0]
    assert section == answer
    assert methods.question_id not in document.document_text
    assert "1 written from your answers" in env.outcome.statement


def test_a_blank_or_unmatched_answer_changes_nothing(runs_dir: Path) -> None:
    name = "soil-survey.data-dictionary.draft.json"
    plain, _ = draft(runs_dir, sample(name))
    before = plain.payload_as(Document)
    first = before.document_questions[0].question_id
    env, _ = draft(runs_dir, asked_with(name, (first, "  "), ("q-" + "f" * 16, "Stray")))
    after = env.payload_as(Document)
    assert after.document_text == before.document_text
    assert after.document_questions == before.document_questions
