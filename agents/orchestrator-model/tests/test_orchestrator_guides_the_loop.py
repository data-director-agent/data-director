"""orchestrator.model leads a researcher through the loop in a project, from their files to a
deposit package, on the in-tree agents, with the model scripted (#203,
docs/specs/orchestration.md).

The model keeps no place in the flow: the conductor tells it on every turn, in a note from the
harness, where the project's log says it is. This walks the same loop as orchestrator.stub's
`test_guides_the_loop.py`, so both orchestrators are shown leading it."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_files.agent import FileArchivist
from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_orchestrator_model.agent import ModelOrchestrator
from dd_agent_orchestrator_model.model import ModelTurn, ToolCall
from dd_harness.conductor import Conductor
from dd_harness.deposit import build_package
from dd_harness.projects import APPROVED, Decision, ProjectStore
from dd_harness.requirements import DATACITE, load_requirements
from dd_harness.store import RunStore
from dd_harness.testing import TEST_PRINCIPAL, file_inventory, make_conductor, request
from dd_sdk.contract.models import Envelope, Message, OutcomeStatus

MODEL = "claude-test"


def say(text: str) -> ModelTurn:
    return ModelTurn(
        text=text,
        tool_calls=[],
        stop_reason="end_turn",
        content=[{"type": "text", "text": text}],
        model_id=MODEL,
        input_tokens=100,
        output_tokens=10,
    )


def call(*calls: tuple[str, dict[str, Any]]) -> ModelTurn:
    tool_calls = [
        ToolCall(id=f"toolu_{n}", name=name, input=args) for n, (name, args) in enumerate(calls)
    ]
    return ModelTurn(
        text="",
        tool_calls=tool_calls,
        stop_reason="tool_use",
        content=[
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in tool_calls
        ],
        model_id=MODEL,
        input_tokens=100,
        output_tokens=10,
    )


class ScriptedModel:
    """Plays back the turns queued for each researcher message, and keeps what it was sent."""

    model_id = MODEL

    def __init__(self) -> None:
        self.turns: list[ModelTurn] = []
        self.sent: list[dict[str, Any]] = []

    def turn(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, use_tools: bool
    ) -> ModelTurn:
        self.sent.append({"messages": json.loads(json.dumps(messages)), "tools": tools})
        if not self.turns:
            raise AssertionError("the model was called more often than scripted")
        return self.turns.pop(0)

    def note(self) -> str:
        """The harness's note on the last message the model was sent this turn."""
        content = self.sent[0]["messages"][-1]["content"]
        assert isinstance(content, str) and content.startswith("[From the harness")
        return content

    def tools_serving(self, step_id: str) -> list[str]:
        return [t["name"] for t in self.sent[0]["tools"] if step_id in t["description"]]


class Researcher:
    """One conversation in a project; each `say` is answered by the turns given for it."""

    def __init__(self, conductor: Conductor, model: ScriptedModel, conversation_id: str) -> None:
        self.conductor = conductor
        self.model = model
        self.conversation_id = conversation_id

    def say(self, text: str, *turns: ModelTurn) -> Envelope:
        self.model.turns, self.model.sent = list(turns), []
        req = request("orchestrator.model", Message(message_text=text)).model_copy(
            update={"conversation_id": self.conversation_id}
        )
        env = self.conductor.invoke(req, acting_for=TEST_PRINCIPAL)
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        assert self.model.turns == [], "the model was called less often than scripted"
        return env


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


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


def approve_every_proposed(
    projects: ProjectStore, project: str, edit: Callable[[str, str], str | None] = lambda k, t: None
) -> None:
    """Approve each latest proposed version: as drafted, or as `edit(kind, text)` returns it."""
    for document in projects.documents(project):
        latest: dict[str, Any] = document["versions"][-1]
        if latest["state"] != "proposed":
            continue
        edited = edit(document["document_kind"], latest["text"])
        projects.decide(
            project,
            Decision(
                document["document_id"],
                latest["version"],
                latest["digest"],
                APPROVED,
                reason="Wrote what the draft left for me." if edited is not None else None,
                edited_text=edited,
            ),
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )


def give_the_record_a_title(kind: str, text: str) -> str | None:
    if kind != "metadata_record":
        return None
    record = json.loads(text)
    record["titles"] = [{"title": "Soil cores 2024"}]
    return json.dumps(record, indent=2) + "\n"


def delegated_agents(env: Envelope, status: OutcomeStatus = OutcomeStatus.SUCCEEDED) -> list[str]:
    assert all(d.delegated_status == status for d in env.delegations), env.delegations
    return sorted(d.delegated_agent_id for d in env.delegations)


@pytest.mark.parametrize("entry_point", [2, 3])
def test_the_model_leads_from_the_files_to_a_package(
    tmp_path: Path, projects: ProjectStore, entry_point: int
) -> None:
    model = ScriptedModel()
    conductor = make_conductor(
        tmp_path / "runs",
        ModelOrchestrator(model),
        FileArchivist(),
        MetadataLibrarian(),
        DocumentationEditor(),
    )
    conductor.projects = projects
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.choose_entry(project, entry_point, acted_for=TEST_PRINCIPAL, caused_by="test")
    inventory = file_inventory("a.csv", "b.csv")
    # A table with a field, so that a data dictionary has something to describe.
    inventory["inventory_files"][0]["file_fields"] = [{"name": "depth", "field_type": "number"}]
    projects.add_inventory(project, inventory, acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    researcher = Researcher(conductor, model, conversation)

    # The model is told the entry point and the step to suggest, the first open one from that
    # entry's phase; the files are already described.
    researcher.say("hello", say("Shall we start with your funder's policies?"))
    note = model.note()
    assert f"entry point {entry_point}" in note
    first = "governance.policies" if entry_point == 2 else "repository.mandated"
    assert f"Suggested next: [{first}]" in note
    assert "done: preparation.files." in note

    # The researcher goes their own way, to the metadata; the model follows. Before a repository
    # is chosen the drafter asks for one; once chosen, it drafts.
    draft_record = ("advisor_metadata", {"document_kind": "metadata_record"})
    env = researcher.say(
        "Let's do the description of the dataset",
        call(draft_record),
        say("The Metadata Librarian needs a repository chosen first."),
    )
    assert delegated_agents(env, OutcomeStatus.ABSTAINED) == ["advisor.metadata"]
    choose_a_repository(tmp_path, projects, project)
    env = researcher.say(
        "I've chosen one", call(draft_record), say("Here is a draft record to check.")
    )
    assert delegated_agents(env) == ["advisor.metadata"]
    assert projects.progress(project)["steps"]["preparation.metadata"] == "started"
    approve_every_proposed(projects, project, give_the_record_a_title)
    assert projects.progress(project)["steps"]["preparation.metadata"] == "done"

    env = researcher.say(
        "Now a README and a data dictionary",
        call(
            ("advisor_documentation", {"document_kind": "readme"}),
            ("advisor_documentation", {"document_kind": "data_dictionary"}),
        ),
        say("Here are a README and a data dictionary to check."),
    )
    assert delegated_agents(env) == ["advisor.documentation", "advisor.documentation"]
    approve_every_proposed(projects, project)
    assert projects.progress(project)["steps"]["preparation.documentation"] == "done"

    # The next turn's note shows the work done, in flow order whatever order it was done in.
    researcher.say("what next?", say("Next, your funder's policies."))
    assert (
        "done: repository.recommend, preparation.files, preparation.documentation, "
        "preparation.metadata." in model.note()
    )

    # Finalising the deposit has no agent, so no tool serves it: the model can only name it as
    # having none (invariant 14). The harness validates and builds the package.
    env = researcher.say(
        "Finalise the deposit",
        say("No agent finalises a deposit yet; Data Director builds the package for you."),
    )
    assert env.delegations == []
    assert model.tools_serving("deposit.finalise") == []
    build_package(
        projects,
        RunStore(tmp_path / "runs"),
        project,
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    steps = projects.progress(project)["steps"]
    assert steps["deposit.validate"] == "done"
    assert steps["deposit.finalise"] == "done"

    researcher.say("what next?", say("Your package is built."))
    note = model.note()
    assert "deposit.validate, deposit.finalise" in note.split("done: ")[1]
    assert "Suggested next: [deposit." not in note
