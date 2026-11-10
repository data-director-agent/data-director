"""A project's name: the model may name a project no person has named, with `name_project`, and
the conductor records it as the project's title (docs/specs/projects.md, agent.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_orchestrator import ScriptedModel, asks, call, say

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model.agent import NAME_TOOL, ModelOrchestrator, conversation
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import Derived
from dd_sdk.contract.models import Derivation, Envelope, Message, OutcomeStatus, Reply

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

NAME = "River sediment cores, Humber estuary 2025"


def in_project(tmp_path: Path, model: Any, title: str | None = None) -> tuple[Conductor, str, str]:
    """A conductor over a project store, a project and a conversation in it."""
    conductor = make_conductor(tmp_path / "runs", ModelOrchestrator(model), HelloWorld())
    projects = ProjectStore(tmp_path / "projects")
    conductor.projects = projects
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title=title)
    started = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="test")
    return conductor, project, started


def turn(conductor: Conductor, conversation_id: str | None, text: str = "Hello") -> Envelope:
    req = request("orchestrator.model", Message(message_text=text))
    return conductor.invoke(
        req.model_copy(update={"conversation_id": conversation_id}), acting_for=TEST_PRINCIPAL
    )


def tool_names(sent: dict[str, Any]) -> set[str]:
    return {t["name"] for t in sent["tools"]}


def test_the_model_names_an_unnamed_project_and_carries_on(tmp_path: Path) -> None:
    model = ScriptedModel(
        [
            call((NAME_TOOL, {"name": f' "{NAME}." '})),
            say("Thanks. Which repository are you thinking of?"),
        ]
    )
    conductor, project, conversation_id = in_project(tmp_path, model)
    env = turn(conductor, conversation_id, "I have sediment cores from the Humber, 2025.")

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert NAME_TOOL in tool_names(model.sent[0])
    # The first message says the project has no name; the tool is answered and the turn goes on.
    assert "no name yet" in model.sent[0]["messages"][-1]["content"]
    [result] = model.sent[1]["messages"][-1]["content"]
    assert result["is_error"] is False
    reply = env.payload_as(Reply)
    assert reply.new_project_title == NAME
    assert reply.reply_text.startswith("Thanks.")
    assert conductor.projects is not None
    summary = conductor.projects.summary(project)
    assert (summary["title"], summary["title_source"]) == (NAME, "model")
    assert ModelOrchestrator.spec.derivations["new_project_title"] == Derived(Derivation.MODEL)


def test_a_name_beside_choices_is_kept_and_the_choices_end_the_turn(tmp_path: Path) -> None:
    choices = {
        "question_key": "q",
        "question_kind": "choice",
        "question_prompt": "Does the dataset involve people?",
        "question_options": [
            {"option_value": "yes", "option_label": "Yes"},
            {"option_value": "no", "option_label": "No"},
        ],
    }
    model = ScriptedModel(
        [
            asks(
                "One question first.",
                (NAME_TOOL, {"name": NAME}),
                ("ask_questions", {"questions": [choices]}),
            )
        ]
    )
    conductor, _, conversation_id = in_project(tmp_path, model)
    reply = turn(conductor, conversation_id).payload_as(Reply)
    assert len(model.sent) == 1
    assert reply.new_project_title == NAME and reply.reply_questions is not None


def test_a_project_a_person_named_is_not_offered_the_tool(tmp_path: Path) -> None:
    model = ScriptedModel([say("Hello.")])
    conductor, _, conversation_id = in_project(tmp_path, model, title="Soil survey")
    turn(conductor, conversation_id)
    assert NAME_TOOL not in tool_names(model.sent[0])
    assert (
        'The researcher named the project "Soil survey"' in model.sent[0]["messages"][-1]["content"]
    )


def test_outside_a_project_there_is_nothing_to_name(tmp_path: Path) -> None:
    model = ScriptedModel([say("Hello.")])
    conductor, _, _ = in_project(tmp_path, model)
    turn(conductor, None)
    assert NAME_TOOL not in tool_names(model.sent[0])
    assert model.sent[0]["messages"][-1]["content"] == "Hello"


def test_a_name_called_when_not_offered_or_empty_is_refused(tmp_path: Path) -> None:
    model = ScriptedModel([call((NAME_TOOL, {"name": "  "})), say("Hello.")])
    conductor, project, conversation_id = in_project(tmp_path, model)
    env = turn(conductor, conversation_id)
    [result] = model.sent[1]["messages"][-1]["content"]
    assert result["is_error"] is True
    assert env.payload_as(Reply).new_project_title is None
    assert conductor.projects is not None
    assert conductor.projects.summary(project)["title"] is None

    model = ScriptedModel([call((NAME_TOOL, {"name": NAME})), say("Hello.")])
    conductor, project, conversation_id = in_project(tmp_path / "named", model, title="Mine")
    env = turn(conductor, conversation_id)
    [result] = model.sent[1]["messages"][-1]["content"]
    assert result["is_error"] is True
    assert env.payload_as(Reply).new_project_title is None
    assert conductor.projects is not None
    assert conductor.projects.summary(project)["title"] == "Mine"


def test_the_model_is_told_a_name_it_gave_and_may_correct_it() -> None:
    message = Message(message_text="now", project_title=NAME, project_title_by_researcher=False)
    (sent,) = conversation(message, history_turns=0)
    note = sent["content"].split("\n\n")[0]
    assert note.startswith("[From the harness, not the researcher]")
    assert f'You named the project "{NAME}"' in note and NAME_TOOL in note
