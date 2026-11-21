"""A column that several files share, by name, type and format, is asked about once, and the
answer fills its cell in each of them (docs/specs/drafting.md, invariant 5; #1317). A study of
many runs, each writing the same tables, is asked as many questions as one with two runs."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_documentation_agent import draft, write_csv

from dd_agent_advisor_documentation.dictionary import (
    DICTIONARY_COLUMNS,
    Source,
    _question_id,
)
from dd_sdk.contract.models import (
    CurrentVersion,
    Document,
    DocumentKind,
    DocumentQuestion,
    DocumentVersionRef,
    DraftAnswer,
    DraftRequest,
    FileInventory,
    InventoryFile,
    OutcomeStatus,
    TableField,
    VersionState,
    new_invocation_id,
)

# Each run of a simulation writes the same two tables.
TABLES = {
    "forces.csv": [("step", "integer"), ("Cd", "number"), ("Cl", "number")],
    "residuals.csv": [("step", "integer"), ("residual", "number")],
}


def inventory(runs: int, *extra: InventoryFile) -> FileInventory:
    files = [
        InventoryFile(
            file_path=f"study/run_{n:03}/results/{table}",
            file_size=100,
            file_sha256="0" * 64,
            file_media_type="text/csv",
            file_identified_by="extension",
            file_fields=[TableField(name=name, field_type=kind) for name, kind in fields],
        )
        for n in range(1, runs + 1)
        for table, fields in TABLES.items()
    ]
    return FileInventory(
        inventory_files=[*files, *extra],
        inventory_tool="dd-inventory",
        inventory_tool_version="1",
        inventory_made_at=datetime(2026, 11, 21, tzinfo=UTC),
    )


def asked(
    files: FileInventory, *answers: tuple[str, str], earlier: str | None = None
) -> DraftRequest:
    current = (
        None
        if earlier is None
        else CurrentVersion(
            version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=1),
            document_title="Data dictionary",
            media_type="text/csv",
            document_text=earlier,
            version_state=VersionState.PROPOSED,
        )
    )
    return DraftRequest(
        document_kind=DocumentKind.DATA_DICTIONARY,
        inventory=files,
        current_version=current,
        draft_answers=[DraftAnswer(answered_question=q, answer_text=a) for q, a in answers],
    )


def drafted(runs_dir: Path, request: DraftRequest) -> tuple[Document, list[dict[str, str]]]:
    env, _ = draft(runs_dir, request)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    document = env.payload_as(Document)
    return document, list(csv.DictReader(io.StringIO(document.document_text)))


def asking(document: Document, field: str, column: str) -> DocumentQuestion:
    return next(
        q for q in document.document_questions if (q.gap_field, q.gap_column) == (field, column)
    )


@pytest.mark.requirement("R5")
def test_the_questions_scale_with_the_columns_not_the_files(runs_dir: Path) -> None:
    few, few_rows = drafted(runs_dir, asked(inventory(2)))
    many, many_rows = drafted(runs_dir, asked(inventory(14)))
    # The draft still has a row for each field of each file.
    assert len(many_rows) == 7 * len(few_rows) == sum(14 * len(f) for f in TABLES.values())

    def targets(document: Document) -> list[tuple[str, str | None, str | None]]:
        return [(q.question_id, q.gap_field, q.gap_column) for q in document.document_questions]

    assert targets(many) == targets(few)
    # Each question names every file whose cell its answer fills: each file with that field.
    for q in many.document_questions:
        assert q.gap_files == [r["file"] for r in many_rows if r["field"] == q.gap_field]


def test_a_column_of_another_type_is_asked_on_its_own(runs_dir: Path) -> None:
    """`step` counted in one file and timed in another is two columns, so two questions."""
    timed = InventoryFile(
        file_path="study/timing.csv",
        file_size=10,
        file_sha256="0" * 64,
        file_media_type="text/csv",
        file_identified_by="extension",
        file_fields=[TableField(name="step", field_type="datetime", field_format="%H:%M")],
    )
    document, _ = drafted(runs_dir, asked(inventory(3, timed)))
    steps = [
        q for q in document.document_questions if (q.gap_field, q.gap_column) == ("step", "unit")
    ]
    assert len(steps) == 2
    assert {tuple(q.gap_files or [q.gap_file]) == ("study/timing.csv",) for q in steps} == {
        True,
        False,
    }


@pytest.mark.requirement("R5")
def test_one_answer_fills_the_column_in_every_file(runs_dir: Path) -> None:
    files = inventory(4)
    first, _ = drafted(runs_dir, asked(files))
    question = asking(first, "Cd", "unit")
    document, rows = drafted(runs_dir, asked(files, (question.question_id, "dimensionless")))
    cd = [r for r in rows if r["field"] == "Cd"]
    assert {r["file"] for r in cd} == set(question.gap_files or [])
    assert {(r["unit"], r["unit_source"]) for r in cd} == {("dimensionless", Source.SUPPLIED)}
    assert question.question_id not in {q.question_id for q in document.document_questions}


def test_a_shared_question_keeps_its_identifier_when_a_file_is_left_out(runs_dir: Path) -> None:
    """Unticking a run folder changes which files share a column, not the column."""
    all_runs, _ = drafted(runs_dir, asked(inventory(5)))
    fewer, _ = drafted(runs_dir, asked(inventory(3)))
    assert asking(all_runs, "Cd", "unit").question_id == asking(fewer, "Cd", "unit").question_id


@pytest.mark.requirement("R5")
def test_an_edit_of_one_files_row_overrides_the_shared_answer(runs_dir: Path) -> None:
    files = inventory(3)
    first, rows = drafted(runs_dir, asked(files))
    shared = asking(first, "Cd", "unit").question_id
    edited = next(i for i, r in enumerate(rows) if r["field"] == "Cd")
    rows[edited] |= {"unit": "1"}  # the researcher's edit of one file's row
    _, again = drafted(
        runs_dir,
        asked(files, (shared, "dimensionless"), earlier=write_csv(rows, DICTIONARY_COLUMNS)),
    )
    cd = {r["file"]: (r["unit"], r["unit_source"]) for r in again if r["field"] == "Cd"}
    assert cd.pop(rows[edited]["file"]) == ("1", Source.SUPPLIED)
    assert set(cd.values()) == {("dimensionless", Source.SUPPLIED)}


def test_an_answer_to_one_files_cell_still_fills_that_cell_alone(runs_dir: Path) -> None:
    """An answer recorded to one file's cell, as drafts asked before columns were shared, stands
    for that file; the others are still asked, together."""
    files = inventory(3)
    path = files.inventory_files[0].file_path
    own = _question_id({"file": path, "field": "Cd", "column": "unit"})
    document, rows = drafted(runs_dir, asked(files, (own, "dimensionless")))
    cd = {r["file"]: (r["unit"], r["unit_source"]) for r in rows if r["field"] == "Cd"}
    assert cd.pop(path) == ("dimensionless", Source.SUPPLIED)
    assert set(cd.values()) == {("", Source.UNKNOWN)}
    question = asking(document, "Cd", "unit")
    assert question.gap_files is not None and set(question.gap_files) == set(cd)
