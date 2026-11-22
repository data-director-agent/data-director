"""A project's provenance graph: its whole history as one PROV-O graph, read from the project log
and the run store (docs/specs/provenance.md).

`project_graph` reads every event of the project's log and every run of its conversations, and
of the runs its events name, and writes neither (invariant 1). Built twice from the same record,
the graph gives the same bytes. The disclosure's graph is the part of it reachable from each
document's latest approved version (invariant 10; `dd_harness.disclosure`).

The graph is checked as RDF against the SHACL shapes kept beside this module (invariant 9).
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from typing import Any

from rdflib import Graph as RDFGraph

from dd_harness.document_origin import DIGITAL_SOURCE_TYPE, origin, version_chain
from dd_harness.provenance_graph.events import MAPPINGS, map_event, runs_named
from dd_harness.provenance_graph.events.base import Context
from dd_harness.provenance_graph.nodes import CONTEXT, Graph, uuid_iri, version_id
from dd_harness.provenance_graph.runs import add_run, named_run
from dd_harness.shacl import Result, run
from dd_harness.storage import ProjectRecord, RunStorage

__all__ = ["CONTEXT", "MAPPINGS", "ProvenanceGraph", "project_graph", "shapes"]


@dataclass(frozen=True)
class ProvenanceGraph:
    project_id: str
    graph: Graph = field(repr=False)
    # The approval of each version approved, by (document id, version).
    approvals: Mapping[tuple[str, int], str] = field(repr=False)

    def jsonld(self) -> dict[str, Any]:
        """The graph in JSON-LD, compacted with one fixed context, its nodes sorted by IRI."""
        return self.graph.jsonld()

    def to_bytes(self) -> bytes:
        """The graph's JSON-LD as bytes: keys sorted, no whitespace, so the same record gives
        the same bytes."""
        return _dumps(self.jsonld())

    def turtle(self) -> str:
        return rdf(self.jsonld()).serialize(format="turtle")

    def subgraph(self, seeds: Iterable[str]) -> dict[str, Any]:
        """The part of the graph reachable from `seeds`, in JSON-LD. A run reached takes with it
        the delegation through which its agent acted, and no other run's; a child run does not
        take its parent."""
        return self.graph.jsonld(keep=_reach(self.graph.nodes, seeds))

    def validate(self) -> list[Result]:
        """The graph's results against the provenance shapes."""
        return validate(self.jsonld())


def project_graph(projects: ProjectRecord, runs: RunStorage, project_id: str) -> ProvenanceGraph:
    """The provenance graph of a project, read from its log and the run store."""
    events = projects.events(project_id)
    ctx = Context(graph=Graph(), project=uuid_iri(project_id))
    stored: dict[str, Mapping[str, Any]] = {}
    for event in events:
        if event["event"] == "conversation_started":
            for turn in runs.iter_envelopes(conversation_id=event["conversation_id"]):
                stored[turn["invocation_id"]] = turn
    named = runs_named(events)
    for invocation_id in sorted(set(named) - set(stored)):
        if (found := runs.get(invocation_id)) is not None:
            stored[invocation_id] = found
    for invocation_id, kept in sorted(stored.items()):
        ctx.agents[invocation_id] = kept["agent_id"]
        add_run(ctx.graph, runs, kept)
    for invocation_id, (naming, agent_id) in sorted(named.items()):
        if invocation_id not in stored:
            named_run(ctx.graph, invocation_id, naming.get("acted_for"), agent_id)
            if agent_id:
                ctx.agents[invocation_id] = agent_id
    for event in events:
        map_event(ctx, event)
    _sources(ctx)
    return ProvenanceGraph(project_id, ctx.graph, dict(ctx.approvals))


def _sources(ctx: Context) -> None:
    """The digital source type of each document's latest approved version (docs/specs/
    disclosure.md), read as the disclosure reads it."""
    by_document: dict[str, list[Mapping[str, Any]]] = {}
    for (document_id, _), event in sorted(ctx.versions.items()):
        by_document.setdefault(document_id, []).append(event)
    for document_id, versions in by_document.items():
        approved = [v for v in versions if (document_id, v["version"]) in ctx.approvals]
        if not approved:
            continue
        chain = version_chain(document_id, versions, approved[-1])
        source = DIGITAL_SOURCE_TYPE[origin(chain)]
        if source:
            ctx.graph.put(
                version_id(document_id, approved[-1]["version"]),
                schema__digitalSourceType={"@id": source},
            )


def _reach(nodes: Mapping[str, Mapping[str, list[Any]]], seeds: Iterable[str]) -> set[str]:
    skip = {"prov:qualifiedDelegation", "dd:parentInvocation"}
    found: set[str] = set()
    stack = list(seeds)
    while stack:
        iri = stack.pop()
        if iri in found or iri not in nodes:
            continue
        found.add(iri)
        node = nodes[iri]
        if "dd:Invocation" in node.get("@type", []):
            stack.append(f"{iri}#delegation")
        for term, values in node.items():
            if term not in skip:
                stack.extend(v["@id"] for v in values if isinstance(v, dict) and "@id" in v)
    return found


def _dumps(document: Mapping[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def rdf(document: Mapping[str, Any]) -> RDFGraph:
    """A JSON-LD document as RDF."""
    with warnings.catch_warnings():
        # rdflib's JSON-LD parser builds a ConjunctiveGraph internally, whatever graph it is given.
        warnings.filterwarnings("ignore", "ConjunctiveGraph is deprecated", DeprecationWarning)
        return RDFGraph().parse(data=_dumps(document), format="json-ld")


@cache
def shapes() -> RDFGraph:
    """The SHACL shapes a provenance graph is checked against (invariant 9)."""
    text = files("dd_harness.provenance_graph").joinpath("shapes.ttl").read_text("utf-8")
    return RDFGraph().parse(data=text, format="turtle")


def validate(document: Mapping[str, Any]) -> list[Result]:
    """The results of a provenance graph, in JSON-LD, against the shapes: of this graph, or of
    one a package carries."""
    return run(rdf(document), shapes())
