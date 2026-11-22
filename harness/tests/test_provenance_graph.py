"""A project's provenance graph, read from its whole log (docs/specs/provenance.md): every event
type has a mapping, every event appears by its IRI, the graph checks against its shapes and is
the same bytes each time it is built."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import rdflib
from rdflib.namespace import PROV, RDF

from dd_harness.projects import EVENT_TYPES, ProjectStore
from dd_harness.provenance_graph import MAPPINGS, ProvenanceGraph, project_graph, rdf, validate
from dd_harness.store import RunStore
from dd_harness.testing import TEST_PRINCIPAL
from dd_harness.testing.provenance import EventLog, every_event
from dd_sdk.contract.models import new_invocation_id

DD = rdflib.Namespace("https://w3id.org/data-director/")
SCHEMA = rdflib.Namespace("http://schema.org/")
PERSON = rdflib.URIRef(TEST_PRINCIPAL.principal_id)


class Built:
    def __init__(self, tmp: Path) -> None:
        self.project_id = new_invocation_id()
        self.run = new_invocation_id()
        self.events = every_event(self.project_id, self.run)
        self.runs = RunStore(tmp)
        self.graph = project_graph(EventLog(self.events), self.runs, self.project_id)
        self.rdf = rdf(self.graph.jsonld())


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    return Built(tmp_path_factory.mktemp("runs"))


def iri(identifier: str) -> rdflib.URIRef:
    return rdflib.URIRef(f"urn:uuid:{identifier}")


def acts_for(graph: rdflib.Graph, agent: Any, activity: Any) -> set[Any]:
    """Whom `agent` acted for in `activity`, through a qualified delegation."""
    return {
        graph.value(d, PROV.agent)
        for d in graph.objects(agent, PROV.qualifiedDelegation)
        if (d, PROV.hadActivity, activity) in graph
    }


@pytest.mark.requirement("R10.3")
def test_every_event_type_has_a_mapping_and_every_mapping_an_event_type() -> None:
    assert set(MAPPINGS) == EVENT_TYPES
    assert {e["event"] for e in every_event(new_invocation_id(), new_invocation_id())} == (
        EVENT_TYPES
    )


def test_the_log_refuses_an_event_type_it_does_not_know(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    with pytest.raises(ValueError, match="not an event type"):
        store._append(project, "project_painted", TEST_PRINCIPAL, "test", {})


@pytest.mark.requirement("R10.3", "C13.1")
@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
def test_each_event_appears_by_its_iri_attributed_to_whom_it_acted_for(
    built: Built, event_type: str
) -> None:
    graph = built.rdf
    for event in [e for e in built.events if e["event"] == event_type]:
        node = iri(event["event_id"])
        cls = DD[MAPPINGS[event_type].class_of(event).removeprefix("dd:")]
        assert (node, RDF.type, cls) in graph
        if (node, RDF.type, PROV.Generation) in graph:
            # A run's generation: the run's agent acted for the person in that run.
            run = graph.value(node, PROV.activity)
            assert run == iri(built.run)
            agents = list(graph.objects(run, PROV.wasAssociatedWith))
            assert agents and all(PERSON in acts_for(graph, a, run) for a in agents)
            continue
        assert (node, RDF.type, PROV.Activity) in graph
        associated = set(graph.objects(node, PROV.wasAssociatedWith))
        assert associated
        for agent in associated:
            assert agent == PERSON or PERSON in acts_for(graph, agent, node)


@pytest.mark.requirement("R10.3")
def test_a_refused_change_and_a_rejection_are_activities_too(built: Built) -> None:
    graph = built.rdf
    (refused,) = [e for e in built.events if e["event"] == "document_change_refused"]
    node = iri(refused["event_id"])
    assert (node, RDF.type, PROV.Activity) in graph
    assert (node, DD.refusal, rdflib.Literal(refused["refusal"])) in graph
    version = rdflib.URIRef(f"urn:uuid:{refused['document_id']}#v1")
    assert (node, PROV.used, version) in graph
    rejected = [
        e
        for e in built.events
        if e["event"] == "document_version_decided" and e["decision"] == "rejected"
    ]
    assert all((iri(e["event_id"]), PROV.used, version) in graph for e in rejected)


@pytest.mark.requirement("R10.3")
def test_content_is_named_by_digest_and_not_carried(built: Built) -> None:
    text = built.graph.to_bytes().decode("utf-8")
    (answered,) = [e for e in built.events if e["event"] == "document_question_answered"]
    assert answered["answer_text"] not in text
    digest = hashlib.sha256(answered["answer_text"].encode()).hexdigest()
    assert (None, SCHEMA.sha256, rdflib.Literal(digest)) in built.rdf
    notes = [e["note"] for e in built.events if e.get("note")]
    assert notes and not any(n in text for n in notes)


@pytest.mark.requirement("R10.3")
def test_the_graph_conforms_to_the_provenance_shapes(built: Built) -> None:
    assert [r for r in built.graph.validate() if r.severity == "violation"] == []


def _with(graph: ProvenanceGraph, *nodes: Mapping[str, Any]) -> dict[str, Any]:
    document = graph.jsonld()
    return {**document, "@graph": [*document["@graph"], *nodes]}


@pytest.mark.parametrize(
    "broken",
    [
        {"@id": "urn:uuid:x", "@type": "prov:Entity", "schema:text": "What I wrote."},
        {"@id": TEST_PRINCIPAL.principal_id, "@type": "dd:AccountableRole"},
        {"@id": "urn:uuid:doc#v1", "@type": "schema:CreativeWork"},
        {
            "@id": "urn:uuid:doc#v2",
            "@type": "schema:CreativeWork",
            "prov:wasGeneratedBy": [{"@id": "urn:uuid:a"}, {"@id": "urn:uuid:b"}],
        },
    ],
    ids=["text carried", "a person who is a role", "no generation", "two generations"],
)
def test_the_shapes_find_a_graph_that_breaks_the_spec(built: Built, broken: dict[str, Any]) -> None:
    results = validate(_with(built.graph, broken))
    assert any(r.severity == "violation" and r.focus == broken["@id"] for r in results)


@pytest.mark.requirement("R10.3")
def test_the_graph_is_the_same_bytes_each_time_and_changes_nothing(
    tmp_path: Path, built: Built
) -> None:
    before = [dict(e) for e in built.events]
    kept = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    log = EventLog(built.events)
    first = project_graph(log, RunStore(tmp_path), built.project_id).to_bytes()
    again = project_graph(log, RunStore(tmp_path), built.project_id).to_bytes()
    assert first == again
    assert log.events(built.project_id) == before
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == kept


@pytest.mark.filterwarnings("ignore:ConjunctiveGraph is deprecated:DeprecationWarning")
def test_the_graph_reads_as_turtle_too(built: Built) -> None:
    turtle = rdflib.Graph().parse(data=built.graph.turtle(), format="turtle")
    assert len(turtle) == len(built.rdf)
