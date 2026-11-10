"""A project's entry point: the model may record the one it worked out from what the researcher
said, with `set_entry_point`, until the researcher chooses one; the conductor records it as the
model's word (docs/specs/orchestration.md, invariant 18; agent.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, asks, call, say
from test_orchestrator_naming import in_project, tool_names, turn

from dd_agent_orchestrator_model.agent import ENTRY_TOOL, ModelOrchestrator, conversation
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.agent import Derived
from dd_sdk.contract.models import Derivation, Message, OutcomeStatus, Reply

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

COLLECTED = "My survey data are already collected and I need to deposit them for a paper."


def projects_of(conductor: object) -> ProjectStore:
    projects = getattr(conductor, "projects", None)
    assert isinstance(projects, ProjectStore)
    return projects


def test_the_entry_point_the_model_worked_out_is_recorded_and_the_journey_matches(
    tmp_path: Path,
) -> None:
    """The reply says the researcher starts at governance; the project's journey says so too,
    and suggests a governance step rather than one for before data collection."""
    model = ScriptedModel(
        [
            call((ENTRY_TOOL, {"entry": 2})),
            say("Your data are already collected, so we start at governance."),
        ]
    )
    conductor, project, conversation_id = in_project(tmp_path, model)
    env = turn(conductor, conversation_id, COLLECTED)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert ENTRY_TOOL in tool_names(model.sent[0])
    # Before it is recorded, the note suggests no step.
    assert "Suggested next" not in model.sent[0]["messages"][-1]["content"]
    [result] = model.sent[1]["messages"][-1]["content"]
    assert result["is_error"] is False
    assert env.payload_as(Reply).new_project_entry == 2
    where = projects_of(conductor).progress(project)
    assert (where["entry"], where["entry_source"]) == (2, "model")
    assert where["suggested"].startswith("governance.")
    assert ModelOrchestrator.spec.derivations["new_project_entry"] == Derived(Derivation.MODEL)

    # The next turn is told the model recorded it, and may still correct it.
    turn(conductor, conversation_id, "What next?")
    note = model.sent[-1]["messages"][-1]["content"]
    assert "you recorded entry point 2" in note
    assert "Suggested next: [governance." in note
    assert ENTRY_TOOL in tool_names(model.sent[-1])


def test_an_entry_point_beside_choices_is_kept_and_the_choices_end_the_turn(
    tmp_path: Path,
) -> None:
    choices = {
        "question_key": "q",
        "question_kind": "choice",
        "question_prompt": "Do you have a Data Management Plan?",
        "question_options": [
            {"option_value": "yes", "option_label": "Yes"},
            {"option_value": "no", "option_label": "No"},
        ],
    }
    model = ScriptedModel(
        [
            asks(
                "One question first.",
                (ENTRY_TOOL, {"entry": 2}),
                ("ask_questions", {"questions": [choices]}),
            )
        ]
    )
    conductor, _, conversation_id = in_project(tmp_path, model)
    reply = turn(conductor, conversation_id, COLLECTED).payload_as(Reply)
    assert len(model.sent) == 1
    assert reply.new_project_entry == 2 and reply.reply_questions is not None


def test_once_the_researcher_chose_the_tool_is_not_offered_and_a_call_is_refused(
    tmp_path: Path,
) -> None:
    model = ScriptedModel([call((ENTRY_TOOL, {"entry": 1})), say("Hello.")])
    conductor, project, conversation_id = in_project(tmp_path, model)
    projects = projects_of(conductor)
    projects.choose_entry(project, 3, acted_for=TEST_PRINCIPAL, caused_by="test")
    env = turn(conductor, conversation_id)
    assert ENTRY_TOOL not in tool_names(model.sent[0])
    assert "the researcher chose entry point 3" in model.sent[0]["messages"][-1]["content"]
    [result] = model.sent[1]["messages"][-1]["content"]
    assert result["is_error"] is True
    assert env.payload_as(Reply).new_project_entry is None
    assert projects.progress(project)["entry"] == 3


def test_an_entry_point_that_is_not_the_flows_is_refused(tmp_path: Path) -> None:
    for given in (4, "2", True, None):
        model = ScriptedModel([call((ENTRY_TOOL, {"entry": given})), say("Hello.")])
        conductor, project, conversation_id = in_project(tmp_path / str(given), model)
        env = turn(conductor, conversation_id)
        [result] = model.sent[1]["messages"][-1]["content"]
        assert result["is_error"] is True
        assert env.payload_as(Reply).new_project_entry is None
        assert projects_of(conductor).progress(project)["entry"] is None


def test_outside_a_project_there_is_no_entry_point_to_record(tmp_path: Path) -> None:
    model = ScriptedModel([say("Hello.")])
    conductor, _, _ = in_project(tmp_path, model)
    turn(conductor, None)
    assert ENTRY_TOOL not in tool_names(model.sent[0])


def test_with_no_entry_point_the_note_suggests_no_step_and_says_to_find_out() -> None:
    message = Message(message_text="now", project_title_by_researcher=False, project_progress=[])
    (sent,) = conversation(message, history_turns=0)
    assert "no entry point has been recorded" in sent["content"]
    assert ENTRY_TOOL in sent["content"]
    assert "Suggested next" not in sent["content"]
