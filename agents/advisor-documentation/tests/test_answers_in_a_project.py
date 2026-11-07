"""The researcher completes a data dictionary by answering its questions (docs/specs/drafting.md,
invariant 6): advisor.documentation drafts within a project, a person's answers are recorded in
the project log, and the next draft, given them by the conductor, marks them `supplied`."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from dd_agent_advisor_documentation.agent import VALUE_COLUMNS, DocumentationEditor, Source
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    Document,
    DocumentKind,
    DraftAnswer,
    DraftRequest,
    OutcomeStatus,
)

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def conductor(runs_dir: Path, projects: ProjectStore) -> Conductor:
    conductor = make_conductor(runs_dir, DocumentationEditor())
    conductor.projects = projects
    return conductor


def rows_of(document: Document) -> dict[tuple[str, str], dict[str, str]]:
    return {(r["file"], r["field"]): r for r in csv.DictReader(io.StringIO(document.document_text))}


@pytest.mark.requirement("R5")
def test_a_researcher_completes_a_data_dictionary_by_answering_its_questions(
    conductor: Conductor, projects: ProjectStore
) -> None:
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    inventory = json.loads((SAMPLES / "soil-survey.inventory.json").read_text(encoding="utf-8"))
    projects.add_inventory(project, inventory, acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")

    def draft() -> Document:
        asked = request(
            "advisor.documentation", DraftRequest(document_kind=DocumentKind.DATA_DICTIONARY)
        ).model_copy(update={"conversation_id": conversation})
        env = conductor.invoke(asked, acting_for=TEST_PRINCIPAL)
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        return env.payload_as(Document)

    first = draft()
    (document,) = projects.documents(project)
    # One field's unknown definition, unit and missing-value codes, as the researcher answers them.
    field = (first.document_questions[0].gap_file, first.document_questions[0].gap_field)
    questions = [q for q in first.document_questions if (q.gap_file, q.gap_field) == field]
    assert {q.gap_column for q in questions} <= set(VALUE_COLUMNS) and len(questions) > 1
    answers = [
        DraftAnswer(answered_question=q.question_id, answer_text=f"Answer for {q.gap_column}")
        for q in questions
    ]
    projects.answer(
        project, document["document_id"], 1, answers, acted_for=TEST_PRINCIPAL, caused_by="test"
    )

    for _ in range(2):  # The answers stand for every later draft, not only the next.
        again = draft()
        row = rows_of(again)[(field[0] or "", field[1] or "")]
        for q in questions:
            column = q.gap_column or ""
            assert (row[column], row[f"{column}_source"]) == (
                f"Answer for {column}",
                Source.SUPPLIED,
            )
        still = {q.question_id for q in again.document_questions}
        assert still.isdisjoint(a.answered_question for a in answers)
        assert len(again.document_questions) == len(first.document_questions) - len(answers)
