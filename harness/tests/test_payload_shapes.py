"""The shape check: a payload against the SHACL shapes its class brings on the card, reported
beside the run and in its crate, never deciding the outcome (docs/specs/contract.md)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rdflib import Graph, Literal
from rdflib.namespace import RDF
from rdflib.plugins.parsers.jsonld import to_rdf

from dd_harness import shacl
from dd_harness import testing as fakes
from dd_harness.shacl import SH
from dd_harness.storage import VALIDATION
from dd_harness.testing import TEST_PRINCIPAL, ScriptedAgent, make_conductor, request
from dd_harness.testing.classes import ProbeReview
from dd_sdk.contract.classes import ClassSchema, ClassSchemaError, Shapes
from dd_sdk.contract.models import GroundingMode, OutcomeStatus

REVIEW = ClassSchema.of(ProbeReview)

# A constraint the class's JSON Schema does not make: the score is at most a half. A payload with
# score 1.0 passes the schema and breaks these shapes.
STRICTER = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
<https://w3id.org/data-director/harness/doubles/ProbeReview>
    sh:property [ sh:path <https://w3id.org/data-director/harness/doubles/score> ;
                  sh:maxInclusive 0.5 ] .
"""


def _report(path: Path) -> Graph:
    graph = Graph()
    to_rdf(json.loads(path.read_text(encoding="utf-8")), graph)
    return graph


def _conforms(report: Graph) -> bool:
    (node,) = report.subjects(RDF.type, SH.ValidationReport)
    return report.value(node, SH.conforms) == Literal(True)


def test_every_in_tree_payload_class_brings_shapes() -> None:
    for spec in fakes.SPECS.values():
        assert spec.payload is not None and spec.payload.shapes is not None


def test_shapes_travel_on_the_card_pinned_by_their_digest() -> None:
    entry = REVIEW.describe()
    rebuilt = ClassSchema.from_description(REVIEW.name, entry)
    assert rebuilt.shapes == REVIEW.shapes
    tampered = {**entry, "shapes": {**entry["shapes"], "shacl": entry["shapes"]["shacl"] + " "}}
    with pytest.raises(ClassSchemaError):
        ClassSchema.from_description(REVIEW.name, tampered)


def test_a_card_without_shapes_is_still_read() -> None:
    entry = REVIEW.describe()
    del entry["shapes"]
    assert ClassSchema.from_description(REVIEW.name, entry).shapes is None


def test_a_conforming_payload_is_reported_beside_the_run_and_in_its_crate(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input)
    conductor = make_conductor(runs_dir, agent, crate=True)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    run_dir = runs_dir / env.invocation_id
    assert _conforms(_report(run_dir / VALIDATION))
    assert (run_dir / "crate" / VALIDATION).exists()
    meta = json.loads((run_dir / "crate" / "ro-crate-metadata.json").read_text())
    graph = {e["@id"]: e for e in meta["@graph"]}
    results = graph["#" + env.invocation_id]["result"]
    assert {"@id": VALIDATION} in (results if isinstance(results, list) else [results])


def test_a_payload_that_breaks_its_shapes_keeps_its_outcome(runs_dir: Path) -> None:
    assert REVIEW.shapes is not None
    stricter = replace(
        REVIEW, shapes=Shapes.of(REVIEW.shapes.shacl + STRICTER, REVIEW.shapes.context)
    )
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input, payload=stricter)
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and env.payload is not None
    report = _report(runs_dir / env.invocation_id / VALIDATION)
    assert not _conforms(report)
    paths = {report.value(r, SH.resultPath) for r in report.subjects(RDF.type, SH.ValidationResult)}
    assert any(str(p).endswith("/score") for p in paths)


def test_a_class_without_shapes_gets_no_report(runs_dir: Path) -> None:
    agent = ScriptedAgent(
        GroundingMode.NONE, fakes.review_of_input, payload=replace(REVIEW, shapes=None)
    )
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert not (runs_dir / env.invocation_id / VALIDATION).exists()


def test_a_withheld_payload_is_not_checked(runs_dir: Path) -> None:
    # A none-mode agent that calls a model is withheld by the linter (N1).
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input, steps=[fakes.Chat()])
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.payload is None
    assert not (runs_dir / env.invocation_id / VALIDATION).exists()


def test_nested_objects_are_typed_so_their_shapes_apply() -> None:
    payload = {
        "schema_class": "ProbeReview",
        "score": 1.0,
        "grounded_on": [{"source_id": "input:x", "content_hash": "not a sha256"}],
    }
    found = shacl.validate_payload("0", payload, REVIEW, datetime.now(UTC))
    assert not found.conforms
    assert any(r.path is not None and r.path.endswith("/content_hash") for r in found.results)


def test_a_payload_that_cannot_be_read_is_reported_not_raised() -> None:
    assert REVIEW.shapes is not None
    broken = replace(REVIEW, shapes=Shapes.of("this is not turtle", REVIEW.shapes.context))
    found = shacl.validate_payload("0", {"schema_class": "ProbeReview"}, broken, datetime.now(UTC))
    assert not found.conforms
    assert {r.component for r in found.results} == {shacl.UNCHECKED}
