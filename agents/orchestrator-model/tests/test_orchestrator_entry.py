"""A project's entry point: the model may record the one it worked out from what the researcher
said, with `set_entry_point`, until the researcher chooses one; the conductor records it as the
model's word (docs/specs/orchestration.md, invariant 18; agent.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, asks, call, say
from test_orchestrator_naming import in_project, tool_names, turn

from dd_agent_orchestrator_model.agent import ENTRY_TOOL, ModelOrchestrator, conversation
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.agent import Derived
from dd_sdk.contract.models import Derivation, Envelope, Message, OutcomeStatus, Reply
from dd_sdk.intake import ENTRY

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


ASK_AGAIN = "do not ask where the researcher is, even on the first turn"


def first_turn(tmp_path: Path, entry: int | None) -> tuple[Conductor, ScriptedModel, Envelope]:
    """A project's first turn naming no task, with the entry point the intake recorded, if any."""
    model = ScriptedModel([say("Let us start.")])
    conductor, project, conversation_id = in_project(tmp_path, model)
    if entry is not None:
        projects_of(conductor).answer_intake(
            project, ENTRY, [str(entry)], acted_for=TEST_PRINCIPAL, caused_by="test"
        )
    env = turn(conductor, conversation_id, "Hello")
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return conductor, model, env


def test_a_first_turn_in_a_project_with_an_entry_point_suggests_a_step_and_does_not_ask(
    tmp_path: Path,
) -> None:
    """The intake recorded the entry point, so the note says where the project is and what to
    suggest, and the model is not offered the tool for recording it (invariant 15, #669)."""
    _, model, env = first_turn(tmp_path, entry=2)
    note = model.sent[0]["messages"][-1]["content"]
    assert "the researcher chose entry point 2" in note
    assert "Suggested next: [governance." in note
    assert "ask which entry point applies" not in note
    assert ENTRY_TOOL not in tool_names(model.sent[0])
    assert env.payload_as(Reply).new_project_entry is None


def test_a_first_turn_in_a_project_without_an_entry_point_is_told_to_find_out(
    tmp_path: Path,
) -> None:
    """With no entry point, the harness says nothing of where the project is, so the prompt's
    first-turn rule has the model ask, and it may record what it works out."""
    _, model, _ = first_turn(tmp_path, entry=None)
    note = model.sent[0]["messages"][-1]["content"]
    assert "entry point" not in note
    assert "Suggested next" not in note
    assert ENTRY_TOOL in tool_names(model.sent[0])


def test_the_prompt_says_not_to_ask_again_and_is_the_same_with_or_without_an_entry_point(
    tmp_path: Path,
) -> None:
    """Where the project is goes in the harness's note, never the system prompt, so the prompt
    is the same on every run and caches."""
    assert ASK_AGAIN in SYSTEM_PROMPT
    for entry in (2, None):
        conductor, _, env = first_turn(tmp_path / str(entry), entry)
        kept = conductor.store.get_prompts(env.invocation_id)
        assert [p["system"] for p in kept.values()] == [SYSTEM_PROMPT]
