"""The setup questions' answers reach the model: the conductor fills `Message.project_intake` from
the project log, and a note from the harness gives them, "Not sure" included, which no step state
shows (docs/specs/orchestration.md, invariant 20; notes.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, say
from test_orchestrator_entry import projects_of
from test_orchestrator_naming import in_project, turn

from dd_agent_orchestrator_model.notes import LEAD, intake_note
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import IntakeAnswer, Message, OutcomeStatus
from dd_sdk.intake import ENTRY, NO, NOT_SURE, YES, question

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

DMP = "intake.dmp"
SENSITIVE = "intake.sensitive"


def label(question_id: str, value: str) -> str:
    return next(o.label for o in question(question_id).options if o.value == value)


def first_note(tmp_path: Path, answers: dict[str, str], *, attach: bool = False) -> str:
    """The text the model is sent on a project's first turn, after the intake's answers."""
    model = ScriptedModel([say("Let us start.")])
    conductor, project, conversation_id = in_project(tmp_path, model)
    projects = projects_of(conductor)
    for question_id, value in {ENTRY: "1", **answers}.items():
        projects.answer_intake(
            project, question_id, [value], acted_for=TEST_PRINCIPAL, caused_by="test"
        )
    if attach:
        projects.add_documentation(
            project, "plan.md", "text/markdown", "# Plan", acted_for=TEST_PRINCIPAL, caused_by="t"
        )
    env = turn(conductor, conversation_id, "I've answered the setup questions.")
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    content = model.sent[0]["messages"][-1]["content"]
    assert isinstance(content, str)
    return content


def intake_paragraph(content: str) -> str | None:
    paragraphs = content.split("\n\n")
    return next((p for p in paragraphs if "beside the entry point" in p and LEAD in p), None)


def test_each_answer_reaches_the_model_and_not_sure_too(tmp_path: Path) -> None:
    """A "Not sure", which marks no step, is still given to the model, beside a "No"."""
    note = intake_paragraph(first_note(tmp_path, {DMP: NOT_SURE, SENSITIVE: NO}))
    assert note is not None
    assert question(DMP).prompt in note and question(SENSITIVE).prompt in note
    assert label(DMP, NOT_SURE) in note and label(SENSITIVE, NO) in note


def test_with_only_the_entry_point_answered_there_is_no_intake_note(tmp_path: Path) -> None:
    assert intake_paragraph(first_note(tmp_path, {})) is None


def test_a_plan_the_researcher_has_is_invited_until_a_document_is_attached(
    tmp_path: Path,
) -> None:
    invited = intake_paragraph(first_note(tmp_path / "none", {DMP: YES}))
    attached = intake_paragraph(first_note(tmp_path / "one", {DMP: YES}, attach=True))
    assert invited is not None and attached is not None
    assert "attach" in invited
    assert "attach" not in attached


def test_a_plan_is_offered_a_review_and_no_plan_is_offered_writing(tmp_path: Path) -> None:
    attached = intake_paragraph(first_note(tmp_path / "one", {DMP: YES}, attach=True))
    none = intake_paragraph(first_note(tmp_path / "none", {DMP: NO}))
    assert attached is not None and none is not None
    assert "review" in attached and "write" not in attached
    assert "write" in none and "review" not in none


def test_a_caller_cannot_supply_the_intake() -> None:
    """Outside a project the conductor removes the slot, so a caller's answers never reach the
    note; here the note is built only from what the slot holds."""
    assert intake_note(Message(message_text="Hi")) is None
    given = Message(
        message_text="Hi",
        project_intake=[
            IntakeAnswer(
                intake_question_id=DMP,
                intake_question_prompt=question(DMP).prompt,
                intake_answer_labels=[label(DMP, NO)],
            )
        ],
    )
    note = intake_note(given)
    assert note is not None and note.startswith(LEAD)


def test_the_prompt_says_the_setup_answers_are_given() -> None:
    assert "setup questions" in SYSTEM_PROMPT
