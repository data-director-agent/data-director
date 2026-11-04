"""Runs in a project (docs/specs/projects.md, invariants 4, 6, 7, 9 and 10): the conductor takes a
run's project from its conversation, gives a drafter the project's facts, and records its draft as
a proposed version caused by the run."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from a2a.helpers import get_data_parts
from requirement_sets import override, standard, write
from starlette.applications import Starlette

from dd_harness.conductor import Conductor, ProjectAssignmentError
from dd_harness.conversations import get_conversation, list_conversations
from dd_harness.identity import OperatorAssertion
from dd_harness.projects import DOCUMENT_VERSION_ADDED, PROPOSED, ProjectStore
from dd_harness.requirements import load_requirements
from dd_harness.testing import (
    HARNESS_URL,
    TEST_PRINCIPAL,
    DocumentStub,
    ScriptedAgent,
    document_request,
    make_conductor,
    message,
    reply_over,
    request,
    review_of_input,
    send_to_harness,
)
from dd_harness.transport.a2a import a2a_routes
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DocumentVersionRef,
    DraftRequest,
    FileInventory,
    GroundingMode,
    GroundingRef,
    IdentificationMethod,
    InventoryFile,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    new_invocation_id,
)
from dd_sdk.contract.problem import PROBLEM_BASE
from dd_sdk.evidence import input_hash

pytestmark = pytest.mark.requirement("C13.3")


def inventory(*paths: str) -> FileInventory:
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 10, 30, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path=path,
                file_size=10,
                file_sha256="a" * 64,
                file_media_type="text/csv",
                file_pronom_ids=["x-fmt/18"],
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for path in paths
        ],
    )


def as_doc(inv: FileInventory) -> dict[str, Any]:
    return inv.model_dump(mode="json", exclude_none=True)


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def project(projects: ProjectStore, tmp_path: Path) -> str:
    """A project with a two-file inventory and ORDA chosen."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    projects.add_inventory(
        project_id, as_doc(inventory("a.csv", "b.csv")), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    repositories = write(
        tmp_path / "repositories", ("standards", standard()), ("overrides", override())
    )
    orda = load_requirements(repositories).resolve("r3d100012124", "ORDA", ["Dublin Core"])
    projects.choose_repository(project_id, orda, acted_for=TEST_PRINCIPAL, caused_by="test")
    return project_id


def conductor_over(runs: Path, projects: ProjectStore, *agents: Any) -> Conductor:
    conductor = make_conductor(runs, *agents)
    conductor.projects = projects
    return conductor


def in_conversation(req: InvocationRequest, conversation_id: str) -> InvocationRequest:
    return req.model_copy(update={"conversation_id": conversation_id})


def draft_request(**facts: Any) -> DraftRequest:
    return DraftRequest(document_kind=DocumentKind.README, **facts)


def test_a_draft_in_a_project_is_given_its_facts_and_kept_as_a_proposed_version(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    # What a caller, or a model, sends is replaced by what the project holds.
    sent = draft_request(inventory=inventory("made-up.csv"))
    env = conductor.invoke(
        in_conversation(request("stub.document", sent), conversation), acting_for=TEST_PRINCIPAL
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.project_id == project
    assert "Given: files=2, repository=ORDA" in env.payload_as(Document).document_text
    # The stored request is what the agent was given, and its input hash covers the facts.
    stored = json.loads((tmp_path / "runs" / env.invocation_id / "request.json").read_text())
    assert stored["project_id"] == project
    added = next(e for e in projects.events(project) if e["event"] == "inventory_added")
    assert input_hash(stored["input"]["inventory"]) == added["digest"]
    assert stored["input"]["requirements"] == projects.requirements(project)

    (document,) = projects.documents(project)
    (version,) = document["versions"]
    assert version["state"] == PROPOSED
    assert version["drafted_by"]["invocation_id"] == env.invocation_id
    event = projects.events(project)[-1]
    assert event["event"] == DOCUMENT_VERSION_ADDED
    assert event["caused_by"] == env.invocation_id
    assert event["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id

    # The conversation says which project it is in.
    assert get_conversation(conductor.store, conversation)["project_id"] == project  # type: ignore[index]
    assert list_conversations(conductor.store)[0]["project_id"] == project


def test_a_fact_the_project_does_not_have_is_removed_and_the_drafter_is_told_none(
    tmp_path: Path, projects: ProjectStore
) -> None:
    bare = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(bare, acted_for=TEST_PRINCIPAL, caused_by="t")
    sent = draft_request(inventory=inventory("made-up.csv"))
    env = conductor.invoke(
        in_conversation(request("stub.document", sent), conversation), acting_for=TEST_PRINCIPAL
    )
    assert "Given: files=None, repository=None" in env.payload_as(Document).document_text
    stored = json.loads((tmp_path / "runs" / env.invocation_id / "request.json").read_text())
    assert "inventory" not in stored["input"]


def test_outside_a_project_nothing_is_filled_or_recorded(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    # A conversation started in no project, and a run in no conversation.
    for conversation in (new_invocation_id(), None):
        sent = draft_request(inventory=inventory("caller.csv"))
        req = request("stub.document", sent).model_copy(update={"conversation_id": conversation})
        env = conductor.invoke(req, acting_for=TEST_PRINCIPAL)
        assert env.project_id is None
        assert "Given: files=1, repository=None" in env.payload_as(Document).document_text
    assert projects.documents(project) == []


def test_a_caller_may_not_name_a_project(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    forged = request("stub.document", draft_request()).model_copy(update={"project_id": project})
    with pytest.raises(ProjectAssignmentError, match="set by the conductor"):
        conductor.invoke(forged, acting_for=TEST_PRINCIPAL)

    # Nor over A2A: the request is refused before anything runs.
    _card, routes = a2a_routes(conductor, OperatorAssertion(TEST_PRINCIPAL), HARNESS_URL)
    task = send_to_harness(Starlette(routes=routes), HARNESS_URL, forged)
    assert "project_id" in str(get_data_parts(task.status.message.parts)[0]["error"])
    assert list(conductor.store.iter_envelopes()) == []
    assert projects.documents(project) == []


def test_the_agent_is_never_told_its_project(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    seen: list[InvocationRequest] = []

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(req)
        return review_of_input(req, ctx)

    conductor = conductor_over(
        tmp_path / "runs", projects, ScriptedAgent(GroundingMode.NONE, behaviour)
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    env = conductor.invoke(
        in_conversation(request("fake.none"), conversation), acting_for=TEST_PRINCIPAL
    )
    assert env.project_id == project
    assert seen[0].project_id is None
    # A result that is not a Document is advice: nothing is added to the project.
    assert projects.documents(project) == []


def test_a_delegated_childs_draft_is_kept_in_its_parents_project(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        return reply_over(ctx, ctx.delegate("stub.document", draft_request()))

    conductor = conductor_over(
        tmp_path / "runs",
        projects,
        ScriptedAgent(GroundingMode.DELEGATION, behaviour),
        DocumentStub(),
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    parent = conductor.invoke(
        in_conversation(request("fake.delegation", message()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert parent.outcome.status == OutcomeStatus.SUCCEEDED, parent.outcome.statement
    (delegation,) = parent.delegations
    child = conductor.store.get(delegation.delegated_invocation_id)
    assert child is not None
    assert child["project_id"] == project
    assert "Given: files=2, repository=ORDA" in child["payload"]["document_text"]
    (document,) = projects.documents(project)
    assert document["versions"][0]["drafted_by"]["invocation_id"] == child["invocation_id"]
    assert projects.events(project)[-1]["caused_by"] == child["invocation_id"]


def test_a_failed_draft_is_not_kept(tmp_path: Path, projects: ProjectStore, project: str) -> None:
    def fails(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        raise RuntimeError("no model")

    stub = DocumentStub()
    conductor = conductor_over(tmp_path / "runs", projects, stub)
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    stub.run = fails  # type: ignore[method-assign, assignment]
    env = conductor.invoke(
        in_conversation(request("stub.document", draft_request()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert projects.documents(project) == []


def test_a_draft_that_revises_no_version_of_the_project_fails_the_run(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    def revises_elsewhere(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Drafted."),
            payload=Document(
                document_kind=DocumentKind.README,
                media_type="text/markdown",
                document_text="# Elsewhere\n",
                document_derivation=Derivation.TEMPLATE,
                grounded_on=[GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)],
                revises=DocumentVersionRef(document_id=new_invocation_id(), version=1),
            ),
            evidence=review_of_input(req, ctx).evidence,
        )

    stub = DocumentStub()
    stub.run = revises_elsewhere  # type: ignore[method-assign, assignment]
    conductor = conductor_over(tmp_path / "runs", projects, stub)
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    env = conductor.invoke(
        in_conversation(request("stub.document", document_request()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None
    assert env.problem.type == PROBLEM_BASE + "revision-refused"
    assert env.payload is None
    # The failed run is the record, and the project is unchanged.
    stored = conductor.store.get(env.invocation_id)
    assert stored is not None
    assert stored["outcome"]["status"] == "failed"
    assert projects.documents(project) == []
