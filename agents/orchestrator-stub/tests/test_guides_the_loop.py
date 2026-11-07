"""orchestrator.stub leads a researcher through the loop in a project, from their files to
approved documents, on the in-tree agents (#203, docs/specs/orchestration.md).

Where the project is comes from its log on every turn; the stub keeps no place of its own. Its
suggestion is never a gate: a step chosen out of order is done, and the suggestion follows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_files.agent import FileArchivist
from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_orchestrator_stub.agent import DirectorStub
from dd_harness.conductor import Conductor
from dd_harness.projects import APPROVED, Decision, ProjectStore
from dd_harness.requirements import DATACITE, load_requirements
from dd_harness.testing import TEST_PRINCIPAL, file_inventory, make_conductor, request
from dd_sdk.contract.models import (
    ChoiceAnswer,
    ConversationTurn,
    Envelope,
    Message,
    OutcomeStatus,
    Reply,
    TurnRole,
)


class Researcher:
    """One conversation in a project, turn by turn, as the app would send it."""

    def __init__(self, conductor: Conductor, conversation_id: str) -> None:
        self.conductor = conductor
        self.conversation_id = conversation_id
        self.history: list[ConversationTurn] = []
        self.last: Envelope | None = None

    def say(self, text: str, choose: str | None = None) -> Envelope:
        answer = None
        if choose is not None:
            assert self.last is not None
            answer = ChoiceAnswer(answer_to=self.last.invocation_id, answer_values=[choose])
        message = Message(message_text=text, history=list(self.history), choice_answer=answer)
        req = request("orchestrator.stub", message).model_copy(
            update={"conversation_id": self.conversation_id}
        )
        env = self.conductor.invoke(req, acting_for=TEST_PRINCIPAL)
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        reply = self.reply(env)
        self.history += [
            ConversationTurn(role=TurnRole.USER, turn_text=text),
            ConversationTurn(
                role=TurnRole.AGENT,
                turn_text=reply.reply_text,
                turn_agent_id=env.agent_id,
                turn_agent_version=env.agent_version,
                turn_invocation_id=env.invocation_id,
            ),
        ]
        self.last = env
        return env

    @staticmethod
    def reply(env: Envelope) -> Reply:
        return env.payload_as(Reply)

    def offered(self) -> list[str]:
        assert self.last is not None
        question = self.reply(self.last).reply_question
        return [o.option_value for o in question.question_options] if question else []


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def conductor_over(tmp_path: Path, projects: ProjectStore) -> Conductor:
    conductor = make_conductor(
        tmp_path / "runs",
        DirectorStub(),
        FileArchivist(),
        MetadataLibrarian(),
        DocumentationEditor(),
    )
    conductor.projects = projects
    return conductor


def choose_a_repository(tmp_path: Path, projects: ProjectStore, project: str) -> None:
    """The researcher picks a repository whose only requirements are DataCite's title."""
    standard = {
        "schema_class": "RequirementSet",
        "requirement_set_id": "datacite-4",
        "version": 1,
        "title": "DataCite Metadata Schema 4",
        "conforms_to": DATACITE,
        "re3data_names": ["DataCite Metadata Schema"],
        "fields": [{"property": "titles", "schema_org": "name", "obligation": "required"}],
        "required_documents": ["metadata_record"],
    }
    path = tmp_path / "repositories" / "standards" / "datacite-4.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(standard), "utf-8")
    resolved = load_requirements(tmp_path / "repositories").resolve(
        "r3d100000001", "A repository", ["DataCite Metadata Schema"]
    )
    projects.choose_repository(project, resolved, acted_for=TEST_PRINCIPAL, caused_by="test")


def approve_every_proposed(projects: ProjectStore, project: str) -> None:
    for document in projects.documents(project):
        latest: dict[str, Any] = document["versions"][-1]
        if latest["state"] == "proposed":
            projects.decide(
                project,
                Decision(document["document_id"], latest["version"], latest["digest"], APPROVED),
                acted_for=TEST_PRINCIPAL,
                caused_by="test",
            )


def delegated_agents(env: Envelope, status: OutcomeStatus = OutcomeStatus.SUCCEEDED) -> set[str]:
    assert all(d.delegated_status == status for d in env.delegations)
    return {d.delegated_agent_id for d in env.delegations}


@pytest.mark.parametrize("entry_point", [2, 3])
def test_the_stub_leads_from_the_files_to_approved_documents(
    tmp_path: Path, projects: ProjectStore, entry_point: int
) -> None:
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.choose_entry(project, entry_point, acted_for=TEST_PRINCIPAL, caused_by="test")
    inventory = file_inventory("a.csv", "b.csv")
    inventory["inventory_files"][0]["file_fields"] = [{"name": "depth", "field_type": "number"}]
    projects.add_inventory(project, inventory, acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    researcher = Researcher(conductor_over(tmp_path, projects), conversation)

    # A first turn in a project with an entry point is answered with where it is, not a question
    # about the entry point; the suggestion is the first open step from that entry's phase.
    researcher.say("hello")
    offered = researcher.offered()
    assert offered[0] == ("governance.policies" if entry_point == 2 else "repository.mandated")
    assert "preparation.files" not in offered  # the inventory already shows it done

    # The researcher goes their own way: straight to the metadata, which the suggestion did not
    # name. Nothing refuses it; the drafter asks for a repository first, and once one is chosen,
    # drafts.
    env = researcher.say("Fill in the description of your dataset", choose="preparation.metadata")
    assert delegated_agents(env, OutcomeStatus.ABSTAINED) == {"advisor.metadata"}
    choose_a_repository(tmp_path, projects, project)
    env = researcher.say("Fill in the description of your dataset", choose="preparation.metadata")
    assert delegated_agents(env) == {"advisor.metadata"}
    assert projects.progress(project)["steps"]["preparation.metadata"] == "started"
    approve_every_proposed(projects, project)
    assert projects.progress(project)["steps"]["preparation.metadata"] == "done"

    env = researcher.say("Write a README and a data dictionary", choose="preparation.documentation")
    assert delegated_agents(env) == {"advisor.documentation"}
    assert len(env.delegations) == 2
    approve_every_proposed(projects, project)
    assert projects.progress(project)["steps"]["preparation.documentation"] == "done"

    # Steps nothing in the log records are marked by the researcher, done or skipped; the
    # suggestion moves past them.
    researcher.say("what next?")
    first = researcher.offered()[0]
    projects.mark_step(project, first, "skipped", acted_for=TEST_PRINCIPAL, caused_by="test")
    researcher.say("what next?")
    assert researcher.offered()[0] != first
    for done in ("preparation.files", "preparation.metadata", "preparation.documentation"):
        assert done not in researcher.offered()


def test_a_step_with_no_agent_is_named_and_not_done_by_the_stub(
    tmp_path: Path, projects: ProjectStore
) -> None:
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.choose_entry(project, 3, acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    researcher = Researcher(conductor_over(tmp_path, projects), conversation)
    researcher.say("what next?")
    env = researcher.say("Upload your files", choose="deposit.upload")
    assert env.delegations == []
    assert "no agent yet" in Researcher.reply(env).reply_text
    assert "deposit.upload" not in projects.progress(project)["steps"]


def test_outside_a_project_the_stub_still_asks_where_the_researcher_is(
    tmp_path: Path, projects: ProjectStore
) -> None:
    researcher = Researcher(conductor_over(tmp_path, projects), conversation_id=None)  # type: ignore[arg-type]
    researcher.say("hello")
    assert researcher.offered() == ["1", "2", "3"]
