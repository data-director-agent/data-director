"""The values that mean a value is missing are a list, kept in the form of a Frictionless Table
Schema field's `missingValues` (values.py, dictionary.py, docs/specs/drafting.md)."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pytest

from dd_agent_advisor_documentation.dictionary import (
    DICTIONARY_COLUMNS,
    Source,
    draft_dictionary,
)
from dd_agent_advisor_documentation.values import missing_values_cell
from dd_sdk.contract.inventory import (
    DisclosureCheck,
    FieldSummary,
    FileInventory,
    InventoryFile,
    MissingCodeCount,
    TableField,
)
from dd_sdk.contract.models import (
    CurrentVersion,
    DocumentVersionRef,
    VersionState,
    new_invocation_id,
)
from dd_sdk.contract.questions import AnswerKind


@pytest.mark.parametrize(
    ("text", "cell"),
    [
        ('["-99","NA"]', '["-99","NA"]'),
        ('[ "-99", "NA", "NA" ]', '["-99","NA"]'),  # a JSON array, laid out another way
        ('[""]', '[""]'),  # only an empty cell is missing: the standard's default
        ('["a, b"]', '["a, b"]'),  # a value holding the separator
        ("-99\nNA", '["-99","NA"]'),
        ("-99, NA", '["-99","NA"]'),  # a cell written before the list form
        ("-99; NA ;", '["-99","NA"]'),
        ("85.0, -999", '["85.0","-999"]'),  # a full stop inside a number is not a sentence
        ("none", '["none"]'),  # no word is read for its meaning
    ],
)
def test_a_list_is_kept_in_the_standard_form(text: str, cell: str) -> None:
    assert missing_values_cell(text) == cell
    assert json.loads(cell) == json.loads(missing_values_cell(cell))  # and stays so


@pytest.mark.parametrize("text", ["", "  ", ",", " ; \n "])
def test_text_with_no_value_leaves_the_gap_open(text: str) -> None:
    assert missing_values_cell(text) == ""


@pytest.mark.parametrize(
    "text",
    [
        "-999 (sensor not responding), -9999 (whole-logger fault)",
        "Negative one is used when the sensor failed. Otherwise none.",
        "code: -99",
    ],
)
def test_a_note_about_the_values_is_the_researchers_own_words(text: str) -> None:
    assert missing_values_cell(text) == text


def inventory(*codes: str) -> FileInventory:
    summary = (
        FieldSummary(
            summary_missing_codes=[
                MissingCodeCount(missing_code=c, missing_code_count=30) for c in codes
            ]
        )
        if codes
        else None
    )
    check = (
        DisclosureCheck(
            check_tool="acro",
            check_tool_version="1.1.0",
            check_threshold=10,
            check_rounding_base=5,
            check_suppressed=0,
        )
        if codes
        else None
    )
    field = TableField(name="pH", field_summary=summary, field_disclosure_check=check)
    table = InventoryFile(
        file_path="a.csv",
        file_size=10,
        file_sha256="0" * 64,
        file_media_type="text/csv",
        file_identified_by="extension",
        file_fields=[field],
    )
    return FileInventory(
        inventory_files=[table],
        inventory_tool="dd-inventory",
        inventory_tool_version="1",
        inventory_made_at=datetime(2026, 11, 21, tzinfo=UTC),
    )


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_the_question_says_it_is_answered_with_a_list() -> None:
    drafted = draft_dictionary(inventory(), None, {})
    (question,) = [q for q in drafted.questions if q.gap_column == "missing_values"]
    assert question.answer_kind == AnswerKind.LIST
    assert question.question_help
    assert all(q.answer_kind is None for q in drafted.questions if q is not question)


def test_an_answer_is_placed_in_the_standard_form_as_supplied() -> None:
    first = draft_dictionary(inventory(), None, {})
    (question,) = [q for q in first.questions if q.gap_column == "missing_values"]
    again = draft_dictionary(inventory(), None, {question.question_id: "-99, NA"})
    (row,) = rows(again.text)
    assert (row["missing_values"], row["missing_values_source"]) == (
        '["-99","NA"]',
        Source.SUPPLIED,
    )
    assert question.question_id not in {q.question_id for q in again.questions}


def test_an_answer_with_no_value_leaves_the_question_open() -> None:
    first = draft_dictionary(inventory(), None, {})
    (question,) = [q for q in first.questions if q.gap_column == "missing_values"]
    again = draft_dictionary(inventory(), None, {question.question_id: " , "})
    assert rows(again.text)[0]["missing_values_source"] == Source.UNKNOWN
    assert question.question_id in {q.question_id for q in again.questions}


def test_a_cell_in_the_old_form_is_still_the_inventorys_not_the_researchers() -> None:
    old = io.StringIO()
    writer = csv.writer(old, lineterminator="\n")
    writer.writerow(DICTIONARY_COLUMNS)
    writer.writerow(["a.csv", "pH", "", "", "", "", "", "", "", "", "-99, NA", "inferred"])
    current = CurrentVersion(
        version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=1),
        media_type="text/csv",
        document_text=old.getvalue(),
        version_state=VersionState.PROPOSED,
    )
    drafted = draft_dictionary(inventory("-99", "NA"), current, {})
    (row,) = rows(drafted.text)
    assert (row["missing_values"], row["missing_values_source"]) == (
        '["-99","NA"]',
        Source.INFERRED,
    )
