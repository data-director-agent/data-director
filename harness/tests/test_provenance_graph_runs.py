"""Runs in a project's provenance graph (docs/specs/provenance.md, Runs and what happens within
them), and the disclosure as a part of that graph (invariant 10)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import rdflib
from rdflib.namespace import PROV, RDF

from dd_harness.conductor import Conductor
from dd_harness.disclosure import disclose
from dd_harness.projects import Decision, ProjectStore, text_digest
from dd_harness.provenance_graph import project_graph, rdf
from dd_harness.testing import (
    RESTRICTIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    DocumentStub,
    ScriptedAgent,
    document_request,
    make_conductor,
    message,
    record,
    reply_over,
    request,
    review_of_input,
)
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    DocumentKind,
    Envelope,
    GroundingMode,
    InvocationRequest,
    OutcomeStatus,
    Principal,
)

MODEL = "test-model-2026-11-01"
DECIDER = Principal(principal_id="https://orcid.org/0000-0002-1825-0097", name="Josiah Carberry")
DD = rdflib.Namespace("https://w3id.org/data-director/")
AGENTS = "https://w3id.org/data-director/agents/"


def uuid(identifier: str) -> rdflib.URIRef:
    return rdflib.URIRef(f"urn:uuid:{identifier}")


def delegating(target: str) -> ScriptedAgent:
    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        return reply_over(ctx, ctx.delegate(target, record()))

    return ScriptedAgent(GroundingMode.DELEGATION, behaviour)


class Project:
    """A project with a conversation in which an orchestrator delegated, and a README drafted,
    rejected, asked to be revised, drafted again revising it, and approved."""

    def __init__(self, tmp: Path) -> None:
        self.store = ProjectStore(tmp / "projects")
        self.conductor = make_conductor(
            tmp / "runs",
            DocumentStub(MODEL),
            delegating("fake.none"),
            ScriptedAgent(GroundingMode.NONE, review_of_input),
            crate=True,
        )
        self.id = self.store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
        conversation = self.store.start_conversation(
            self.id, acted_for=TEST_PRINCIPAL, caused_by="test"
        )
        self.parent = self.conductor.invoke(
            request("fake.delegation", message()).model_copy(
                update={"conversation_id": conversation}
            ),
            acting_for=TEST_PRINCIPAL,
        )
        assert self.parent.outcome.status == OutcomeStatus.SUCCEEDED, self.parent.outcome.statement
        self.first = self.draft()
        ref = self.store.record_draft(self.id, self.first)
        self.decide(ref.version, verdict="rejected", reason="Name the licence.")
        self.store.request_revision(
            self.id,
            ref.document_id,
            ref.version,
            self.digest(ref.version),
            "Name the licence.",
            acted_for=DECIDER,
            caused_by="test",
        )
        second = self.draft()
        payload = {**second.to_document()["payload"], "revises": ref.model_dump(mode="json")}
        self.second = Envelope.model_validate({**second.to_document(), "payload": payload})
        self.document_id = ref.document_id
        self.store.record_draft(self.id, self.second)
        self.decide(2, verdict="approved")

    def draft(self) -> Envelope:
        envelope = self.conductor.invoke(
            request("stub.document", document_request(DocumentKind.README)),
            acting_for=TEST_PRINCIPAL,
        )
        assert envelope.outcome.status == OutcomeStatus.SUCCEEDED, envelope.outcome.statement
        return envelope

    def digest(self, version: int) -> str:
        (document,) = self.store.documents(self.id)
        (shown,) = [v for v in document["versions"] if v["version"] == version]
        return text_digest(shown["text"])

    def decide(self, version: int, **given: Any) -> None:
        (document,) = self.store.documents(self.id)
        self.store.decide(
            self.id,
            Decision(
                document_id=document["document_id"],
                version=version,
                digest=self.digest(version),
                **given,
            ),
            acted_for=DECIDER,
            caused_by="test",
        )

    def graph(self) -> rdflib.Graph:
        return rdf(project_graph(self.store, self.conductor.store, self.id).jsonld())


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    return Project(tmp_path_factory.mktemp("project"))


def acts_for(graph: rdflib.Graph, agent: Any, activity: Any) -> set[Any]:
    return {
        graph.value(d, PROV.agent)
        for d in graph.objects(agent, PROV.qualifiedDelegation)
        if (d, PROV.hadActivity, activity) in graph
    }


@pytest.mark.requirement("R10.3", "C13.1", "C13.4")
def test_a_run_is_its_agent_acting_for_the_person_and_informed_by_its_model_calls(
    project: Project,
) -> None:
    graph = project.graph()
    run = uuid(project.first.invocation_id)
    agent = rdflib.URIRef(AGENTS + "stub.document")
    assert (run, RDF.type, DD.Invocation) in graph
    assert (run, PROV.wasAssociatedWith, agent) in graph
    assert (agent, RDF.type, PROV.SoftwareAgent) in graph
    assert acts_for(graph, agent, run) == {rdflib.URIRef(TEST_PRINCIPAL.principal_id)}
    calls = set(graph.objects(run, PROV.wasInformedBy))
    assert calls and all((c, RDF.type, PROV.Activity) in graph for c in calls)
    (call,) = [c for c in calls if (c, PROV.used, None) in graph]
    assert str(graph.value(call, PROV.wasAssociatedWith)).endswith(f"/{MODEL}")
    assert (run, PROV.has_provenance, None) in graph


@pytest.mark.requirement("R10.3", "DD-DELEGATION")
def test_a_delegated_child_is_a_run_the_parent_was_informed_by(project: Project) -> None:
    graph = project.graph()
    parent = uuid(project.parent.invocation_id)
    (delegation,) = project.parent.delegations
    child = uuid(delegation.delegated_invocation_id)
    assert (parent, PROV.wasInformedBy, child) in graph
    assert (child, DD.parentInvocation, parent) in graph
    agent = graph.value(child, PROV.wasAssociatedWith)
    assert acts_for(graph, agent, child) == {rdflib.URIRef(TEST_PRINCIPAL.principal_id)}


@pytest.mark.requirement("R10.3", "C13.3")
def test_two_versions_a_rejection_and_a_revision_are_each_recorded(project: Project) -> None:
    graph = project.graph()
    v1 = rdflib.URIRef(f"urn:uuid:{project.document_id}#v1")
    v2 = rdflib.URIRef(f"urn:uuid:{project.document_id}#v2")
    assert (v1, PROV.wasGeneratedBy, uuid(project.first.invocation_id)) in graph
    assert (v2, PROV.wasGeneratedBy, uuid(project.second.invocation_id)) in graph
    assert (v2, PROV.wasRevisionOf, v1) in graph
    decisions = {
        str(graph.value(a, DD.decision)): a for a in graph.subjects(RDF.type, DD.VersionDecision)
    }
    assert set(decisions) == {"rejected", "approved"}
    assert (decisions["rejected"], PROV.used, v1) in graph
    assert (decisions["approved"], PROV.used, v2) in graph
    (asked,) = graph.subjects(RDF.type, DD.RevisionRequest)
    assert (asked, PROV.used, v1) in graph
    assert (asked, PROV.wasAssociatedWith, rdflib.URIRef(DECIDER.principal_id)) in graph
    for version in (v1, v2):
        (generation,) = graph.objects(version, PROV.qualifiedGeneration)
        assert (generation, RDF.type, DD.VersionDrafting) in graph


@pytest.mark.requirement("R10.3")
def test_the_project_graph_conforms_to_its_shapes(project: Project) -> None:
    built = project_graph(project.store, project.conductor.store, project.id)
    assert [r for r in built.validate() if r.severity == "violation"] == []


@pytest.mark.requirement("R10.2", "R10.3")
def test_the_disclosure_graph_is_part_of_the_project_graph(project: Project) -> None:
    disclosed = rdf(disclose(project.store, project.conductor.store, project.id).prov_jsonld())
    whole = project.graph()
    assert len(disclosed) and all(triple in whole for triple in disclosed)
    v2 = rdflib.URIRef(f"urn:uuid:{project.document_id}#v2")
    assert (None, PROV.used, v2) in disclosed  # the approval
    # Only what the approved version came from: not the orchestrator's run.
    assert (uuid(project.parent.invocation_id), None, None) not in disclosed


@pytest.mark.requirement("R10.3", "C13.2")
def test_a_run_the_policy_gate_referred_is_informed_by_the_gate(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    conductor: Conductor = make_conductor(tmp_path / "runs", AbstainingStub(), profile=RESTRICTIVE)
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = store.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="test")
    referred = conductor.invoke(
        request("stub.abstain", message()).model_copy(update={"conversation_id": conversation}),
        acting_for=TEST_PRINCIPAL,
    )
    assert referred.outcome.status == OutcomeStatus.REFERRED
    graph = rdf(project_graph(store, conductor.store, project).jsonld())
    run = uuid(referred.invocation_id)
    gate = rdflib.URIRef(f"{run}#policy-gate")
    assert (run, PROV.wasInformedBy, gate) in graph
    assert (gate, DD.decision, rdflib.Literal("referred")) in graph
    assert (run, DD.outcome, rdflib.Literal("referred")) in graph
