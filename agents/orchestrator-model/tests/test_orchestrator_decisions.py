"""What the researcher chose and people decided reaches the model (docs/specs/orchestration.md,
#1168): a note from the harness, written from the `Message`'s `project_repository` and
`project_decisions`, opens the current message, so the model does not say that a repository the
researcher chose has not been chosen."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, say
from test_orchestrator_naming import in_project, turn

from dd_agent_orchestrator_model.agent import conversation
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_harness.projects import FactVerdict
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import (
    ChosenRepository,
    DocumentationSummary,
    Message,
    OutcomeStatus,
    ProjectFact,
)

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

ZENODO = ChosenRepository(chosen_repository_name="Zenodo", chosen_re3data_id="r3d100010468")
LICENCE = {"fact_kind": "licence", "fact_subject": "licence", "licence_id": "CC-BY-4.0"}
WHY = "The funder's policy asks for an open licence."
FACTS = [
    {**LICENCE, "proposed_because": WHY},
    {"fact_kind": "funder", "fact_subject": "funder", "fact_funder_name": "EPSRC"},
    {
        "fact_kind": "required_repository",
        "fact_subject": "required_repository",
        "fact_repository_name": "ORDA",
        "fact_re3data_id": "r3d100012124",
        "fact_required_by": ["University of Sheffield"],
    },
    {
        "fact_kind": "file_inclusion",
        "fact_subject": "data/Thumbs.db",
        "fact_file_path": "data/Thumbs.db",
        "file_decision": "exclude",
    },
    {
        "fact_kind": "sensitivity",
        "fact_subject": "site_gps",
        "sensitive_subject": "site_gps",
        "sensitivity_decision": "generalise",
        "location_precision": "region",
    },
    {
        "fact_kind": "sharing_commitment",
        "fact_subject": "XRD patterns",
        "commitment_repository": "Zenodo",
        "commitment_quote": "XRD patterns will be shared on Zenodo.",
        "commitment_document": "c" * 64,
    },
]


def current(message: Message) -> str:
    """The text of the current message, as the model is sent it."""
    content = conversation(message, 20)[-1]["content"]
    assert isinstance(content, str)
    return content


def test_the_chosen_repository_and_each_decision_open_the_message() -> None:
    message = Message(
        message_text="Which repository are we using?",
        project_title_by_researcher=True,
        project_title="Perovskite films",
        project_repository=ZENODO,
        project_decisions=[ProjectFact.model_validate(f) for f in FACTS],
    )

    text = current(message)

    assert text.endswith(message.message_text)
    for value in (
        ZENODO.chosen_repository_name,
        ZENODO.chosen_re3data_id,
        LICENCE["licence_id"],
        "EPSRC",
        "r3d100012124",
        "data/Thumbs.db",
        "site_gps",
        "XRD patterns",
    ):
        assert value in text, value
    # Only structured values: never anyone's words about why.
    assert WHY not in text


def test_with_nothing_chosen_or_decided_there_is_no_note() -> None:
    """No note says that nothing is decided: a profile may have kept the decisions from the
    model, so their absence is not evidence that none was made."""
    bare = Message(message_text="Hello", project_title_by_researcher=True, project_title="P")
    with_repository = bare.model_copy(update={"project_repository": ZENODO})
    assert current(with_repository) != current(bare)
    assert current(bare).count("[From the harness") == 1  # the name note only


def test_the_prompt_treats_a_noted_decision_as_decided() -> None:
    assert "repository chosen for deposit" in SYSTEM_PROMPT


def test_a_decision_in_the_project_reaches_the_model_on_a_later_turn(tmp_path: Path) -> None:
    """The note is read from the project record, so a decision made after the conversation
    started reaches the next turn."""
    model = ScriptedModel([say("Noted."), say("You chose CC-BY-4.0.")])
    conductor, project, conversation_id = in_project(tmp_path, model, title="Perovskite films")
    assert turn(conductor, conversation_id).outcome.status == OutcomeStatus.SUCCEEDED
    assert LICENCE["licence_id"] not in model.sent[0]["messages"][-1]["content"]

    assert conductor.projects is not None
    conductor.projects.decide_fact(
        project, FactVerdict.CHANGED, fact=LICENCE, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    env = turn(conductor, conversation_id, "Which licence did we pick?")

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert LICENCE["licence_id"] in model.sent[1]["messages"][-1]["content"]


PLAN = DocumentationSummary(
    documentation_name="DMP.docx",
    documentation_digest="d" * 64,
    documentation_media_type="text/markdown",
    documentation_size=100,
    documentation_added_at=datetime(2026, 11, 19, tzinfo=UTC),
)


def test_an_attached_plan_not_yet_read_is_said_to_be_unread() -> None:
    """#1233: a plan attached but not read must not leave a generalist shortlist unexplained."""
    message = Message(
        message_text="Where should I deposit?",
        project_title_by_researcher=True,
        project_title="P",
        project_documentation=[PLAN],
    )
    text = current(message)
    assert '"DMP.docx"' in text
    assert "no attached plan has been read for a repository" in text
    assert "Data Management Plan check" in text


def test_once_a_commitment_is_confirmed_the_plan_is_not_said_to_be_unread() -> None:
    message = Message(
        message_text="Where should I deposit?",
        project_title_by_researcher=True,
        project_title="P",
        project_documentation=[PLAN],
        project_decisions=[ProjectFact.model_validate(FACTS[-1])],
    )
    text = current(message)
    assert '"DMP.docx"' in text
    assert "not been read" not in text


def test_without_documents_there_is_no_documents_note() -> None:
    bare = Message(message_text="Hello", project_title_by_researcher=True, project_title="P")
    assert "attached to the project" not in current(bare)


def test_the_prompt_says_an_unread_plan_is_unread() -> None:
    assert "the plan has not been read for a repository" in SYSTEM_PROMPT
    assert "described as the plan's" in SYSTEM_PROMPT
