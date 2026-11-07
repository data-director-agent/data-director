"""advisor.documentation through the conductor, on the template path: the Documentation Editor
(docs/specs/drafting.md) drafting the README and the data dictionary with no model configured."""

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
    Derivation,
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
    assert env.grounding_mode == GroundingMode.INPUT_ONLY and grounded
    document = env.payload_as(Document)
    assert document.document_kind == DocumentKind.README
    assert document.document_derivation == Derivation.TEMPLATE
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
    assert "template path" in env.outcome.statement


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
    assert not entry["description"].startswith("Mock.")
    assert entry["grounding_mode"] == GroundingMode.INPUT_ONLY.value
    assert entry["derivations"]["document_text"] == {
        "how": "model",
        "recorded_in": "document_derivation",
    }
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


WITH_RECORD = "soil-survey.readme-with-record.draft.json"


def section_of(text: str, heading: str) -> str:
    return text.split(f"## {heading}\n\n", 1)[1].split("\n\n## ", 1)[0]


def with_record(asked: DraftRequest, **properties: object) -> DraftRequest:
    """`asked` with its metadata record's properties replaced by `properties`."""
    assert asked.metadata_record is not None
    record = asked.metadata_record.model_copy(update={"document_text": json.dumps(properties)})
    return asked.model_copy(update={"metadata_record": record})


@pytest.mark.requirement("R5")
def test_a_readme_takes_what_the_approved_metadata_record_gives(runs_dir: Path) -> None:
    """The record's values are supplied (docs/specs/drafting.md, invariant 2): placed as given."""
    asked = sample(WITH_RECORD)
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    document = env.payload_as(Document)
    text = document.document_text
    assert text.startswith("# Soil chemistry of upland survey sites, 2025\n")

    general = section_of(text, "General information")
    assert "- **Title:** Soil chemistry of upland survey sites, 2025" in general
    assert "- **Creators:** Example, Alex; Sample, Sam" in general
    # The record's funder is a placeholder the metadata mock left: not a value.
    assert "Funding" not in general
    assert "_To be written by the researcher:" in general

    # The abstract says all the Description asks, so no gap is left there.
    assert section_of(text, "Description").startswith("Soil pH, moisture and organic carbon")
    assert "_To be written" not in section_of(text, "Description")
    asked_sections = {q.gap_section for q in document.document_questions}
    assert "Description" not in asked_sections
    assert {"General information", "Access and licence", "How to cite"} <= asked_sections

    access = section_of(text, "Access and licence")
    assert access.startswith(
        "Licence: Creative Commons Attribution 4.0 International "
        "(<https://creativecommons.org/licenses/by/4.0/>)."
    )
    assert "ORDA offers these licences:" in access
    assert section_of(text, "How to cite").startswith(
        "Example, Alex; Sample, Sam. Soil chemistry of upland survey sites, 2025."
    )
    assert "version 2 of the approved metadata record" in env.outcome.statement
    assert "(1 in full)" in env.outcome.statement


def test_a_record_of_placeholders_drafts_as_no_record_does(runs_dir: Path) -> None:
    """An approved record the metadata mock left empty gives nothing: every gap stays asked."""
    plain, _ = draft(runs_dir, sample("soil-survey.readme.draft.json"))
    empty = with_record(
        sample(WITH_RECORD),
        titles=[{"title": None}],
        creators=[{"name": " "}],
        descriptions=[{"description": None, "descriptionType": "Abstract"}],
        rightsList=[{"rights": None}],
    )
    env, _ = draft(runs_dir, empty)
    document = env.payload_as(Document)
    assert document.document_text == plain.payload_as(Document).document_text
    assert document.document_questions == plain.payload_as(Document).document_questions


@pytest.mark.parametrize(
    ("conforms_to", "text", "why"),
    [
        ("http://example.org/other-schema", "{}", "reads only DataCite records"),
        ("http://datacite.org/schema/kernel-4", "not json", "not JSON"),
        ("http://datacite.org/schema/kernel-4", "[]", "not a JSON object"),
    ],
)
def test_a_record_the_mock_cannot_read_is_not_used_and_it_says_so(
    runs_dir: Path, conforms_to: str, text: str, why: str
) -> None:
    asked = sample(WITH_RECORD)
    assert asked.metadata_record is not None
    record = asked.metadata_record.model_copy(
        update={"conforms_to": conforms_to, "document_text": text}
    )
    env, _ = draft(runs_dir, asked.model_copy(update={"metadata_record": record}))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert "The approved metadata record was not used" in env.outcome.statement
    assert why in env.outcome.statement
    assert env.payload_as(Document).document_text.startswith("# README\n")


def test_an_answer_is_kept_beside_what_the_record_gives(runs_dir: Path) -> None:
    asked = sample(WITH_RECORD)
    env, _ = draft(runs_dir, asked)
    cite = next(
        q for q in env.payload_as(Document).document_questions if q.gap_section == "How to cite"
    )
    answer = "Cite the DOI the repository gives on deposit."
    answered = asked.model_copy(
        update={
            "draft_answers": [DraftAnswer(answered_question=cite.question_id, answer_text=answer)]
        }
    )
    env, _ = draft(runs_dir, answered)
    section = section_of(env.payload_as(Document).document_text, "How to cite")
    assert section.endswith(answer)
    assert section.startswith("Example, Alex; Sample, Sam.")


def test_a_citation_has_the_year_when_the_record_gives_one(runs_dir: Path) -> None:
    asked = with_record(
        sample(WITH_RECORD),
        titles=[{"title": "Subtitle", "titleType": "Subtitle"}, {"title": "Soil survey."}],
        creators=[{"familyName": "Example", "givenName": "Alex"}],
        publicationYear="2026",
    )
    env, _ = draft(runs_dir, asked)
    text = env.payload_as(Document).document_text
    assert text.startswith("# Soil survey.\n")
    assert section_of(text, "How to cite").startswith("Example, Alex (2026). Soil survey.\n")
