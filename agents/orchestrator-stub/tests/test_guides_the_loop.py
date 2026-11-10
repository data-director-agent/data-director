"""orchestrator.stub leads a researcher through the loop in a project, from their files to a
deposit package, on the in-tree agents (#203, docs/specs/orchestration.md).

Where the project is comes from its log on every turn; the stub keeps no place of its own. Its
suggestion is never a gate: a step chosen out of order is done, and the suggestion follows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_files.agent import FileArchivist
from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_orchestrator_stub.agent import NEXT_STEP_KEY, DirectorStub
from dd_harness.conductor import Conductor
from dd_harness.deposit import PackageRefusedError, build_package
from dd_harness.projects import APPROVED, Decision, ProjectStore
from dd_harness.requirements import DATACITE, load_requirements
from dd_harness.sources import RecordsFile, Sources
from dd_harness.store import RunStore
from dd_harness.testing import TEST_PRINCIPAL, file_inventory, make_conductor, request
from dd_sdk.contract.models import (
    ConversationTurn,
    Envelope,
    Message,
    OutcomeStatus,
    QuestionAnswer,
    Reply,
    ReplyAnswers,
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
            # The stub reads a step by its question's key, whether or not the last reply asked.
            answer = ReplyAnswers(
                answer_to=self.last.invocation_id,
                given_answers=[QuestionAnswer(answered_key=NEXT_STEP_KEY, answer_values=[choose])],
            )
        message = Message(message_text=text, history=list(self.history), reply_answers=answer)
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
        questions = self.reply(self.last).reply_questions or []
        return [o.option_value for q in questions for o in q.question_options or []]


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
    record: dict[str, Any] = {
        "re3data_id": "r3d100000001",
        "name": "A repository",
        "metadata_standards": ["DataCite Metadata Schema"],
    }
    registry = Sources(
        by_snapshot_ref={
            "re3data:export:2026-11": RecordsFile(records={record["re3data_id"]: record})
        }
    )
    projects.choose_repository(
        project,
        "r3d100000001",
        registry=registry,
        requirements=load_requirements(tmp_path / "repositories"),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )


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


def approve_the_record_with_a_title(projects: ProjectStore, project: str, title: str) -> None:
    """The researcher edits the latest metadata record to give it a title, and approves it."""
    (document,) = [
        d for d in projects.documents(project) if d["document_kind"] == "metadata_record"
    ]
    latest: dict[str, Any] = document["versions"][-1]
    record = json.loads(latest["text"])
    record["titles"] = [{"title": title}]
    projects.decide(
        project,
        Decision(
            document["document_id"],
            latest["version"],
            latest["digest"],
            APPROVED,
            reason="Gave the dataset its title.",
            edited_text=json.dumps(record, indent=2) + "\n",
        ),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )


def delegated_agents(env: Envelope, status: OutcomeStatus = OutcomeStatus.SUCCEEDED) -> set[str]:
    assert all(d.delegated_status == status for d in env.delegations)
    return {d.delegated_agent_id for d in env.delegations}


@pytest.mark.parametrize("entry_point", [2, 3])
def test_the_stub_leads_from_the_files_to_a_package(
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

    # Finalising the deposit has no agent: the stub names it as having none and does not do it
    # (invariant 14). The harness validates the project and builds the package, as
    # `dd-harness project package` does, and the log shows both steps done.
    env = researcher.say("Finalise the deposit", choose="deposit.finalise")
    assert env.delegations == []
    assert "no agent yet" in Researcher.reply(env).reply_text
    assert "deposit.finalise" not in projects.progress(project)["steps"]
    runs = RunStore(tmp_path / "runs")
    # The record was approved as the mock drafted it, with its title left for the researcher to
    # write, so the package is refused and says why; the validation shows its step begun.
    with pytest.raises(PackageRefusedError, match="no titles"):
        build_package(projects, runs, project, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert projects.progress(project)["steps"]["deposit.validate"] == "started"

    # Going back is always open: the researcher has the record drafted again, writes its title,
    # and the package is built.
    env = researcher.say("Fill in the description of your dataset", choose="preparation.metadata")
    assert delegated_agents(env) == {"advisor.metadata"}
    # The redraft is the next version of the one metadata record, not a second record (#631).
    (record,) = [d for d in projects.documents(project) if d["document_kind"] == "metadata_record"]
    assert [v["state"] for v in record["versions"]] == ["approved", "proposed"]
    assert record["versions"][1]["revises"] == {"document_id": record["document_id"], "version": 1}
    approve_the_record_with_a_title(projects, project, "Soil cores 2024")
    build_package(projects, runs, project, acted_for=TEST_PRINCIPAL, caused_by="test")
    steps = projects.progress(project)["steps"]
    assert steps["deposit.validate"] == "done"
    assert steps["deposit.finalise"] == "done"
    researcher.say("what next?")
    assert {"deposit.validate", "deposit.finalise"}.isdisjoint(researcher.offered())


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
