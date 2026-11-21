"""A data dictionary's UCUM unit codes (docs/specs/drafting.md): worked out by rule from the unit
a field is given, marked `inferred`, and asked only when the rule cannot tell."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.dictionary import (
    DICTIONARY_COLUMNS,
    NOT_APPLICABLE,
    Dictionary,
    Source,
    draft_dictionary,
    question_id,
)
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    CurrentVersion,
    Document,
    DocumentVersionRef,
    DraftAnswer,
    DraftRequest,
    FileInventory,
    OutcomeStatus,
    VersionState,
    new_invocation_id,
)

SAMPLE = Path(__file__).with_name("data") / "soil-survey.data-dictionary.draft.json"
FILE, FIELD = "data/readings.csv", "nitrate_mg_kg"


def asked() -> DraftRequest:
    return DraftRequest.model_validate_json(SAMPLE.read_text(encoding="utf-8"))


def inventory() -> FileInventory:
    given = asked().inventory
    assert given is not None
    return given


def target(column: str, file: str = FILE, field: str = FIELD) -> str:
    return question_id({"file": file, "field": field, "column": column})


def row_of(drafted: Dictionary, file: str = FILE, field: str = FIELD) -> dict[str, str]:
    rows = csv.DictReader(io.StringIO(drafted.text))
    return next(r for r in rows if (r["file"], r["field"]) == (file, field))


def asked_columns(drafted: Dictionary, file: str = FILE, field: str = FIELD) -> set[str]:
    return {
        q.gap_column or "" for q in drafted.questions if (q.gap_file, q.gap_field) == (file, field)
    }


def as_current(drafted: Dictionary, edits: dict[str, str]) -> CurrentVersion:
    """`drafted` as the project's current version, with a person's edits to the field's row."""
    rows = list(csv.DictReader(io.StringIO(drafted.text)))
    for row in rows:
        if (row["file"], row["field"]) == (FILE, FIELD):
            row.update(edits)
    out = io.StringIO()
    writer = csv.DictWriter(out, DICTIONARY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return CurrentVersion(
        version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=1),
        document_title="Data dictionary",
        media_type="text/csv",
        document_text=out.getvalue(),
        version_state=VersionState.PROPOSED,
    )


@pytest.mark.requirement("R3.4", "R5")
def test_a_unit_the_researcher_gives_gets_its_ucum_code_by_rule() -> None:
    drafted = draft_dictionary(inventory(), None, {target("unit"): "mg per kg"})
    row = row_of(drafted)
    assert (row["unit"], row["unit_source"]) == ("mg per kg", Source.SUPPLIED)
    assert (row["unit_code"], row["unit_code_source"]) == ("mg/kg", Source.INFERRED)
    assert "unit_code" not in asked_columns(drafted)
    assert drafted.unit_codes and "`mg/kg`" in drafted.unit_codes[0]


def test_a_unit_code_waits_for_its_unit() -> None:
    drafted = draft_dictionary(inventory(), None, {})
    row = row_of(drafted)
    assert (row["unit_code"], row["unit_code_source"]) == ("", Source.UNKNOWN)
    assert "unit" in asked_columns(drafted)
    assert "unit_code" not in asked_columns(drafted)


@pytest.mark.requirement("R3.4")
def test_a_unit_the_rule_cannot_read_asks_for_its_code() -> None:
    drafted = draft_dictionary(inventory(), None, {target("unit"): "mg/kg, dry weight"})
    row = row_of(drafted)
    assert (row["unit_code"], row["unit_code_source"]) == ("", Source.UNKNOWN)
    (question,) = [q for q in drafted.questions if q.gap_column == "unit_code"]
    assert (question.gap_file, question.gap_field) == (FILE, FIELD)
    assert "mg/kg, dry weight" in question.question_prompt
    assert not drafted.unit_codes


def test_a_field_with_no_unit_has_no_unit_code() -> None:
    drafted = draft_dictionary(inventory(), None, {target("unit"): "None"})
    row = row_of(drafted)
    assert (row["unit_code"], row["unit_code_source"]) == (NOT_APPLICABLE, Source.INFERRED)
    assert "unit_code" not in asked_columns(drafted)
    assert not drafted.unit_codes


def test_an_answer_for_the_code_is_supplied() -> None:
    answers = {target("unit"): "mg/kg, dry weight", target("unit_code"): "mg/kg{dry}"}
    row = row_of(draft_dictionary(inventory(), None, answers))
    assert (row["unit_code"], row["unit_code_source"]) == ("mg/kg{dry}", Source.SUPPLIED)


def test_a_code_the_researcher_edited_survives_a_redraft() -> None:
    answers = {target("unit"): "mg/kg"}
    first = draft_dictionary(inventory(), None, answers)
    edited = as_current(first, {"unit_code": "mg/kg{dry}"})
    row = row_of(draft_dictionary(inventory(), edited, answers))
    assert (row["unit_code"], row["unit_code_source"]) == ("mg/kg{dry}", Source.SUPPLIED)


def test_a_changed_unit_gets_a_fresh_code() -> None:
    first = draft_dictionary(inventory(), None, {target("unit"): "mg/kg"})
    current = as_current(first, {})
    row = row_of(draft_dictionary(inventory(), current, {target("unit"): "g/kg"}))
    assert (row["unit_code"], row["unit_code_source"]) == ("g/kg", Source.INFERRED)


def test_the_statement_names_the_codes_for_checking(runs_dir: Path) -> None:
    answers = [DraftAnswer(answered_question=target("unit"), answer_text="milligrams per kilogram")]
    conductor = make_conductor(runs_dir, DocumentationEditor())
    env = conductor.invoke(
        request("advisor.documentation", asked().model_copy(update={"draft_answers": answers})),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert conductor.grounding_reports[env.invocation_id].passed
    assert "`mg/kg` (milligram per kilogram) for `nitrate_mg_kg`" in env.outcome.statement
    rows = csv.DictReader(io.StringIO(env.payload_as(Document).document_text))
    assert all(set(r) == set(DICTIONARY_COLUMNS) for r in rows)
