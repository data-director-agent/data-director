"""Runs in a project (docs/specs/projects.md, invariants 4, 6, 7, 9 and 10): the conductor takes a
run's project from its conversation, gives a drafter the project's facts, and records its draft as
a proposed version caused by the run."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest
from a2a.helpers import get_data_parts
from requirement_sets import ORDA, override, pinned, standard, write
from starlette.applications import Starlette

from dd_harness.conductor import Conductor, ProjectAssignmentError
from dd_harness.conversations import get_conversation, list_conversations
from dd_harness.identity import OperatorAssertion
from dd_harness.projects import (
    APPROVED,
    DOCUMENT_VERSION_ADDED,
    PROPOSED,
    REJECTED,
    Decision,
    ProjectStore,
    UnknownProjectError,
)
from dd_harness.requirements import load_requirements
from dd_harness.testing import (
    HARNESS_URL,
    STUB_QUESTION,
    TEST_PRINCIPAL,
    AbstainingStub,
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
from dd_sdk.agent import AgentResult, ModelUse, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    ApprovedMetadataRecord,
    CurrentVersion,
    Derivation,
    Document,
    DocumentKind,
    DocumentVersionRef,
    DraftAnswer,
    DraftRequest,
    Envelope,
    FileInventory,
    GroundingMode,
    GroundingRef,
    IdentificationMethod,
    InventoryFile,
    InvocationRequest,
    OpenInput,
    Outcome,
    OutcomeStatus,
    Principal,
    VersionState,
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
    projects.choose_repository(
        project_id,
        ORDA,
        registry=pinned(tmp_path / "re3data"),
        requirements=load_requirements(repositories),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
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


def test_a_run_in_a_project_its_principal_may_not_read_is_refused_and_nothing_is_stored(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """Docs/specs/projects.md, invariant 17: the conductor checks before an invocation."""
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    before = projects.events(project)
    someone = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
    with pytest.raises(UnknownProjectError):
        conductor.invoke(
            in_conversation(request("stub.document", draft_request()), conversation),
            acting_for=someone,
        )
    assert list(conductor.store.iter_envelopes()) == []
    assert projects.events(project) == before


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


@pytest.mark.requirement("R5")
def test_a_drafts_questions_are_kept_and_only_answers_a_person_recorded_are_given(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """Only an answer a person recorded may be placed as supplied (docs/specs/drafting.md,
    invariant 6), so in a project the conductor replaces the answers a caller sent with those
    the project log holds."""
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub(asks=True))
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    made_up = DraftAnswer(answered_question=STUB_QUESTION.question_id, answer_text="Made up")

    def draft() -> tuple[Envelope, dict[str, Any]]:
        env = conductor.invoke(
            in_conversation(
                request("stub.document", draft_request(draft_answers=[made_up])), conversation
            ),
            acting_for=TEST_PRINCIPAL,
        )
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        stored = json.loads((tmp_path / "runs" / env.invocation_id / "request.json").read_text())
        input_doc: dict[str, Any] = stored["input"]
        return env, input_doc

    env, given = draft()
    assert "Answers:" not in env.payload_as(Document).document_text
    assert "draft_answers" not in given
    (document,) = projects.documents(project)
    (version,) = document["versions"]
    assert version["questions"] == [STUB_QUESTION.model_dump(mode="json", exclude_none=True)]

    recorded = DraftAnswer(answered_question=STUB_QUESTION.question_id, answer_text="Soil cores")
    projects.answer(
        project,
        document["document_id"],
        1,
        [recorded],
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    env, given = draft()
    assert "Answers: 1" in env.payload_as(Document).document_text
    assert given["draft_answers"] == [recorded.model_dump(mode="json")]
    # The input hash covers the answers the drafter was given.
    assert env.payload_as(Document).grounded_on[0].content_hash == input_hash(given)


def test_answers_go_only_to_a_drafter_of_the_same_kind(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub(asks=True))
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    readme = conductor.invoke(
        in_conversation(request("stub.document", draft_request()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert readme.project_id == project
    (document,) = projects.documents(project)
    answer = DraftAnswer(answered_question=STUB_QUESTION.question_id, answer_text="Soil cores")
    projects.answer(
        project, document["document_id"], 1, [answer], acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    other = DraftRequest(document_kind=DocumentKind.DATA_DICTIONARY)
    env = conductor.invoke(
        in_conversation(request("stub.document", other), conversation), acting_for=TEST_PRINCIPAL
    )
    assert "Answers:" not in env.payload_as(Document).document_text


def record_in(projects: ProjectStore, project: str, *, approve: bool) -> DocumentVersionRef:
    """A metadata record drafted into the project by the document stub, approved if asked."""
    with_stub = make_conductor(Path(projects.root).parent / "record-runs", DocumentStub())
    env = with_stub.invoke(
        request("stub.document", document_request(DocumentKind.METADATA_RECORD)),
        acting_for=TEST_PRINCIPAL,
    )
    ref = projects.record_draft(project, env)
    if approve:
        (digest,) = [
            d["versions"][-1]["digest"]
            for d in projects.documents(project)
            if d["document_id"] == ref.document_id
        ]
        projects.decide(
            project,
            Decision(ref.document_id, ref.version, digest, APPROVED),
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )
    return ref


@pytest.mark.requirement("R5")
def test_a_draft_is_given_the_metadata_record_a_person_approved_and_no_other(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """The metadata record is supplied content (docs/specs/drafting.md, invariant 2), so a
    drafter is given only a version a person approved, never one a caller sent."""
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    made_up = ApprovedMetadataRecord(
        version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=9),
        media_type="application/json",
        document_text='{"titles": [{"title": "Made up"}]}',
    )

    def draft() -> dict[str, Any]:
        sent = draft_request(metadata_record=made_up)
        env = conductor.invoke(
            in_conversation(request("stub.document", sent), conversation),
            acting_for=TEST_PRINCIPAL,
        )
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        stored = json.loads((tmp_path / "runs" / env.invocation_id / "request.json").read_text())
        assert "record=9" not in env.payload_as(Document).document_text
        input_doc: dict[str, Any] = stored["input"]
        return input_doc

    record_in(projects, project, approve=False)
    assert "metadata_record" not in draft()

    approved = record_in(projects, project, approve=True)
    record_in(projects, project, approve=False)
    given = draft()["metadata_record"]
    assert given == projects.metadata_record(project)
    assert given["version_ref"] == approved.model_dump(mode="json")


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


def stored_input(runs: Path, invocation_id: str) -> dict[str, Any]:
    stored = json.loads((runs / invocation_id / "request.json").read_text())
    found: dict[str, Any] = stored["input"]
    return found


FORGED_SUMMARY = {
    "inventory_digest": "f" * 64,
    "inventory_file_count": 99,
    "inventory_tool": "made-up",
    "inventory_tool_version": "0",
    "inventory_made_at": "2026-01-01T00:00:00Z",
}


def forged_message() -> OpenInput:
    return OpenInput.model_validate(
        {**message().model_dump(mode="json"), "project_inventory": FORGED_SUMMARY}
    )


def test_a_message_in_a_project_is_told_what_its_inventory_is(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    conductor = conductor_over(tmp_path / "runs", projects, AbstainingStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    # What a caller says the project holds is replaced by what it does hold.
    env = conductor.invoke(
        in_conversation(request("stub.abstain", forged_message()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    summary = stored_input(tmp_path / "runs", env.invocation_id)["project_inventory"]
    added = next(e for e in projects.events(project) if e["event"] == "inventory_added")
    assert summary == {
        "inventory_digest": added["digest"],
        "inventory_file_count": 2,
        "inventory_tool": "dd-inventory",
        "inventory_tool_version": "0.1.0",
        "inventory_made_at": "2026-10-30T00:00:00Z",
    }


def test_a_message_is_never_told_of_an_inventory_its_project_does_not_hold(
    tmp_path: Path, projects: ProjectStore
) -> None:
    bare = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conductor = conductor_over(tmp_path / "runs", projects, AbstainingStub())
    in_bare = projects.start_conversation(bare, acted_for=TEST_PRINCIPAL, caused_by="t")
    # In a project without an inventory, in a conversation in no project, and in none at all.
    for conversation in (in_bare, new_invocation_id(), None):
        req = request("stub.abstain", forged_message())
        env = conductor.invoke(
            req.model_copy(update={"conversation_id": conversation}), acting_for=TEST_PRINCIPAL
        )
        assert "project_inventory" not in stored_input(tmp_path / "runs", env.invocation_id)


def test_a_file_inventory_in_a_project_is_the_projects_own(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    seen: list[dict[str, Any]] = []

    def files(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(req.input.model_dump(mode="json", exclude_none=True))
        return review_of_input(req, ctx)

    def orchestrator(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        # An orchestrator told the project holds an inventory sends none of its own.
        bare = OpenInput.model_validate({"schema_class": "FileInventory"})
        return reply_over(ctx, ctx.delegate("fake.none", bare))

    conductor = conductor_over(
        tmp_path / "runs",
        projects,
        ScriptedAgent(GroundingMode.DELEGATION, orchestrator),
        ScriptedAgent(
            GroundingMode.NONE,
            files,
            accepts=(ClassSchema.of(FileInventory),),
        ),
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    parent = conductor.invoke(
        in_conversation(request("fake.delegation", message()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert parent.outcome.status == OutcomeStatus.SUCCEEDED, parent.outcome.statement
    (given,) = seen
    assert [f["file_path"] for f in given["inventory_files"]] == ["a.csv", "b.csv"]
    added = next(e for e in projects.events(project) if e["event"] == "inventory_added")
    assert input_hash(given) == added["digest"]

    # Outside a project, the inventory sent is the one given.
    sent = inventory("caller.csv")
    conductor.invoke(request("fake.none", sent), acting_for=TEST_PRINCIPAL)
    assert seen[-1] == as_doc(sent)


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


def withholding(conductor: Conductor, hosted_models: frozenset[str]) -> Conductor:
    conductor.profile = replace(conductor.profile, hosted_models=hosted_models)
    return conductor


@pytest.mark.requirement("C13.5")
def test_documentation_is_withheld_from_a_hosted_model_by_default(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """Only `inventory` goes to an agent that calls a hosted model unless the profile says
    otherwise (docs/specs/projects.md, invariant 8). The run is refused before anything is sent,
    and the refusal is stored."""
    hosted = DocumentStub("hosted-model", hosting="hosted")
    conductor = conductor_over(tmp_path / "runs", projects, hosted)
    assert conductor.profile.hosted_models == {"inventory"}
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    record_in(projects, project, approve=True)  # a metadata record is documentation
    before = len(projects.documents(project))

    env = conductor.invoke(
        in_conversation(request("stub.document", draft_request()), conversation),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.FAILED
    assert "not run" in (env.outcome.statement or "")
    assert env.problem is not None
    assert env.problem.type == PROBLEM_BASE + "project-content-withheld"
    assert "documentation" in (env.problem.detail or "")
    assert env.payload is None and not env.telemetry.model_calls
    assert (tmp_path / "runs" / env.invocation_id / "envelope.json").is_file()
    assert len(projects.documents(project)) == before


@pytest.mark.requirement("C13.5")
def test_a_hosted_model_is_given_the_inventory(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    hosted = DocumentStub("hosted-model", hosting="hosted")
    conductor = conductor_over(tmp_path / "runs", projects, hosted)
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")

    env = conductor.invoke(
        in_conversation(request("stub.document", draft_request()), conversation),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert "files=2" in env.payload_as(Document).document_text


@pytest.mark.requirement("C13.5")
def test_a_profile_may_let_a_hosted_model_be_given_documentation(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    hosted = DocumentStub("hosted-model", hosting="hosted")
    conductor = withholding(
        conductor_over(tmp_path / "runs", projects, hosted),
        frozenset({"inventory", "documentation"}),
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    record_in(projects, project, approve=True)

    env = conductor.invoke(
        in_conversation(request("stub.document", draft_request()), conversation),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert "metadata_record" in stored_input(tmp_path / "runs", env.invocation_id)


@pytest.mark.requirement("C13.5")
def test_a_profile_may_withhold_even_the_inventory(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    hosted = DocumentStub("hosted-model", hosting="hosted")
    conductor = withholding(conductor_over(tmp_path / "runs", projects, hosted), frozenset())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")

    env = conductor.invoke(
        in_conversation(request("stub.document", draft_request()), conversation),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.problem is not None
    assert env.problem.type == PROBLEM_BASE + "project-content-withheld"


@pytest.mark.requirement("C13.5")
def test_a_local_model_or_none_is_given_everything(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    for stub in (DocumentStub("local-model"), DocumentStub()):
        conductor = withholding(conductor_over(tmp_path / "runs", projects, stub), frozenset())
        conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
        record_in(projects, project, approve=True)
        env = conductor.invoke(
            in_conversation(request("stub.document", draft_request()), conversation),
            acting_for=TEST_PRINCIPAL,
        )
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement


@pytest.mark.requirement("C13.5")
def test_outside_a_project_a_hosted_model_is_given_what_the_caller_sent(tmp_path: Path) -> None:
    """What a caller sends is not the project's, so `hosted_models` does not apply to it."""
    hosted = DocumentStub("hosted-model", hosting="hosted")
    conductor = withholding(make_conductor(tmp_path / "runs", hosted), frozenset())
    made_up = ApprovedMetadataRecord(
        version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=1),
        media_type="application/json",
        document_text="{}",
    )

    env = conductor.invoke(
        request("stub.document", draft_request(metadata_record=made_up)),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement


def test_a_message_in_a_project_is_told_its_entry_point_and_progress(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """The conductor derives where the project is from its log on every turn; whatever a caller
    says of it is replaced (docs/specs/orchestration.md)."""
    projects.choose_entry(project, 2, acted_for=TEST_PRINCIPAL, caused_by="t")
    projects.mark_step(
        project, "governance.embargo", "skipped", acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    conductor = conductor_over(tmp_path / "runs", projects, AbstainingStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    forged = OpenInput.model_validate(
        {
            **message().model_dump(mode="json"),
            "project_entry": 3,
            "project_progress": [{"step_id": "deposit.finalise", "step_state": "done"}],
        }
    )
    env = conductor.invoke(
        in_conversation(request("stub.abstain", forged), conversation), acting_for=TEST_PRINCIPAL
    )
    given = stored_input(tmp_path / "runs", env.invocation_id)
    assert given["project_entry"] == 2
    states = {s["step_id"]: s["step_state"] for s in given["project_progress"]}
    assert states["preparation.files"] == "done"  # the inventory
    assert states["repository.recommend"] == "done"  # ORDA chosen
    assert states["governance.embargo"] == "skipped"
    assert "deposit.finalise" not in states


def test_a_message_outside_a_project_is_told_no_progress(
    tmp_path: Path, projects: ProjectStore
) -> None:
    conductor = conductor_over(tmp_path / "runs", projects, AbstainingStub())
    forged = OpenInput.model_validate(
        {
            **message().model_dump(mode="json"),
            "project_entry": 3,
            "project_progress": [{"step_id": "deposit.finalise", "step_state": "done"}],
        }
    )
    env = conductor.invoke(request("stub.abstain", forged), acting_for=TEST_PRINCIPAL)
    given = stored_input(tmp_path / "runs", env.invocation_id)
    assert "project_entry" not in given and "project_progress" not in given


def drafted(
    conductor: Conductor, conversation: str, kind: DocumentKind = DocumentKind.README, **sent: Any
) -> Envelope:
    asked = DraftRequest(document_kind=kind, **sent)
    env = conductor.invoke(
        in_conversation(request("stub.document", asked), conversation), acting_for=TEST_PRINCIPAL
    )
    return env


def decide_latest(
    projects: ProjectStore,
    project: str,
    verdict: Literal["approved", "rejected"],
    reason: str | None,
) -> None:
    (document,) = projects.documents(project)
    latest = document["versions"][-1]
    projects.decide(
        project,
        Decision(document["document_id"], latest["version"], latest["digest"], verdict, reason),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )


@pytest.mark.requirement("C13.3")
def test_a_redraft_is_the_next_version_of_the_document_and_is_given_the_decision(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """A drafter is given the latest version of the project's document of the kind, with the
    reason a person rejected it, so its redraft is version 2 of that document
    (docs/specs/projects.md, invariant 6; #631)."""
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    first = drafted(conductor, conversation)
    assert "current_version" not in stored_input(tmp_path / "runs", first.invocation_id)
    decide_latest(projects, project, REJECTED, "Too short.")

    second = drafted(conductor, conversation)

    assert second.outcome.status == OutcomeStatus.SUCCEEDED, second.outcome.statement
    given = stored_input(tmp_path / "runs", second.invocation_id)["current_version"]
    (document,) = projects.documents(project)
    assert given == {
        "version_ref": {"document_id": document["document_id"], "version": 1},
        "media_type": document["versions"][0]["media_type"],
        "document_text": document["versions"][0]["text"],
        "version_state": "rejected",
        "decision_reason": "Too short.",
    }
    assert [v["version"] for v in document["versions"]] == [1, 2]
    assert document["versions"][1]["revises"] == given["version_ref"]
    assert document["versions"][1]["state"] == PROPOSED


@pytest.mark.requirement("C13.3")
def test_a_caller_may_not_send_the_version_to_regenerate(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    made_up = CurrentVersion(
        version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=7),
        media_type="text/markdown",
        document_text="# Made up\n",
        version_state=VersionState.APPROVED,
    )

    first = drafted(conductor, conversation, current_version=made_up)
    assert "current_version" not in stored_input(tmp_path / "runs", first.invocation_id)
    second = drafted(conductor, conversation, current_version=made_up)
    given = stored_input(tmp_path / "runs", second.invocation_id)["current_version"]
    assert given["version_ref"]["version"] == 1
    assert given["version_ref"]["document_id"] != made_up.version_ref.document_id


@pytest.mark.requirement("C13.3")
def test_a_redraft_may_name_which_document_of_the_kind_it_continues(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """A project drafted before redrafts kept their document may hold two of one kind; without
    a name the drafter is given the one drafted or revised last."""
    first = record_in(projects, project, approve=False)
    second = record_in(projects, project, approve=False)
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    kind = DocumentKind.METADATA_RECORD

    latest = drafted(conductor, conversation, kind)
    named = drafted(conductor, conversation, kind, redraft_document=first.document_id)

    runs = tmp_path / "runs"
    assert stored_input(runs, latest.invocation_id)["current_version"]["version_ref"] == {
        "document_id": second.document_id,
        "version": 1,
    }
    assert stored_input(runs, named.invocation_id)["current_version"]["version_ref"] == {
        "document_id": first.document_id,
        "version": 1,
    }
    versions = {d["document_id"]: len(d["versions"]) for d in projects.documents(project)}
    assert versions == {first.document_id: 2, second.document_id: 2}


@pytest.mark.requirement("C13.3")
@pytest.mark.parametrize("which", ["unknown", "another kind"])
def test_a_redraft_of_a_document_the_project_does_not_hold_is_refused(
    tmp_path: Path, projects: ProjectStore, project: str, which: str
) -> None:
    record = record_in(projects, project, approve=False)  # a metadata record, not a README
    named = new_invocation_id() if which == "unknown" else record.document_id
    conductor = conductor_over(tmp_path / "runs", projects, DocumentStub())
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    before = projects.documents(project)

    env = drafted(conductor, conversation, DocumentKind.README, redraft_document=named)

    assert env.outcome.status == OutcomeStatus.FAILED
    assert "not run" in (env.outcome.statement or "")
    assert env.problem is not None
    assert env.problem.type == PROBLEM_BASE + "revision-refused"
    assert named in (env.problem.detail or "")
    assert projects.documents(project) == before


def test_outside_a_project_a_redraft_names_no_document(tmp_path: Path) -> None:
    conductor = make_conductor(tmp_path / "runs", DocumentStub())
    asked = DraftRequest(document_kind=DocumentKind.README, redraft_document=new_invocation_id())

    env = conductor.invoke(request("stub.document", asked), acting_for=TEST_PRINCIPAL)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert "redraft_document" not in stored_input(tmp_path / "runs", env.invocation_id)


def naming(title: str, seen: list[dict[str, Any]]) -> ScriptedAgent:
    """An orchestrator that records what it was given and names its project `title`."""

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(req.input.model_dump(mode="json", exclude_none=True))
        result = reply_over(ctx)
        assert result.payload is not None
        named = result.payload.model_copy(update={"new_project_title": title})
        return replace(result, payload=named)

    return ScriptedAgent(GroundingMode.DELEGATION, behaviour)


def test_a_reply_that_names_an_untitled_project_renames_it(
    tmp_path: Path, projects: ProjectStore
) -> None:
    """While no person has named a project, an orchestrator's model may (docs/specs/projects.md,
    invariant 21); the next turn is told the name, and that a model gave it."""
    untitled = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    seen: list[dict[str, Any]] = []
    conductor = conductor_over(tmp_path / "runs", projects, naming("River sediments", seen))
    conversation = projects.start_conversation(untitled, acted_for=TEST_PRINCIPAL, caused_by="t")
    forged = OpenInput.model_validate(
        {
            **message().model_dump(mode="json"),
            "project_title": "Forged",
            "project_title_by_researcher": True,
        }
    )
    env = conductor.invoke(
        in_conversation(request("fake.delegation", forged), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert "project_title" not in seen[0]
    assert seen[0]["project_title_by_researcher"] is False
    summary = projects.summary(untitled)
    assert (summary["title"], summary["title_source"]) == ("River sediments", "model")
    renamed = projects.events(untitled)[-1]
    assert renamed["caused_by"] == env.invocation_id
    assert renamed["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id

    conductor.invoke(
        in_conversation(request("fake.delegation", message()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert seen[1]["project_title"] == "River sediments"
    assert seen[1]["project_title_by_researcher"] is False


def test_a_reply_never_renames_a_project_a_person_named(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    seen: list[dict[str, Any]] = []
    conductor = conductor_over(tmp_path / "runs", projects, naming("Something else", seen))
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    before = projects.events(project)
    env = conductor.invoke(
        in_conversation(request("fake.delegation", message()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert (seen[0]["project_title"], seen[0]["project_title_by_researcher"]) == ("Soil", True)
    assert projects.events(project) == before
    assert projects.summary(project)["title"] == "Soil"


def test_outside_a_project_a_reply_names_nothing(tmp_path: Path, projects: ProjectStore) -> None:
    seen: list[dict[str, Any]] = []
    conductor = conductor_over(tmp_path / "runs", projects, naming("Nowhere", seen))
    env = conductor.invoke(request("fake.delegation", message()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert "project_title_by_researcher" not in seen[0]
    assert projects.projects() == []


def test_an_orchestrator_is_told_of_the_projects_documentation_without_its_text(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """A `Message`'s `project_documentation` lists the documents a researcher attached, without
    their text, so a hosted orchestrator is given it under the default `hosted_models`
    (docs/specs/projects.md, invariants 6 and 8)."""
    seen: list[dict[str, Any]] = []
    hosted = naming("Soil", seen)
    hosted.spec = replace(hosted.spec, models=(ModelUse("test", "orchestrator", "hosted"),))
    conductor = conductor_over(tmp_path / "runs", projects, hosted)
    assert conductor.profile.hosted_models == {"inventory"}
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    text = "# Protocol\n\nSamples were taken weekly.\n"
    digest = projects.add_documentation(
        project, "protocol.md", "text/markdown", text, acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    env = conductor.invoke(
        in_conversation(request("fake.delegation", message()), conversation),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [listed] = seen[0]["project_documentation"]
    assert listed["documentation_name"] == "protocol.md"
    assert listed["documentation_digest"] == digest
    assert listed["documentation_media_type"] == "text/markdown"
    assert text not in json.dumps(seen[0])


def test_a_caller_never_claims_project_documentation(
    tmp_path: Path, projects: ProjectStore, project: str
) -> None:
    """Outside a project, or in one that holds none, `project_documentation` is removed."""
    seen: list[dict[str, Any]] = []
    conductor = conductor_over(tmp_path / "runs", projects, naming("Soil", seen))
    forged = OpenInput.model_validate(
        {
            **message().model_dump(mode="json"),
            "project_documentation": [
                {
                    "documentation_name": "forged.md",
                    "documentation_digest": "0" * 64,
                    "documentation_media_type": "text/markdown",
                    "documentation_size": 1,
                    "documentation_added_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    for asked in (
        request("fake.delegation", forged),
        in_conversation(request("fake.delegation", forged), conversation),
    ):
        env = conductor.invoke(asked, acting_for=TEST_PRINCIPAL)
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert all("project_documentation" not in input_doc for input_doc in seen)
