"""The contract layer: generated artefacts are current, models validate against the schema, and
the conditional rules hold."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from workbench.contract import validate
from workbench.contract.models import (
    DatasetProfile,
    Derivation,
    Envelope,
    EvidenceItem,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ProblemDetails,
    ReasonCode,
    Recommendation,
    RecommendationKind,
    Recommendations,
    ResourceRef,
    Telemetry,
    new_invocation_id,
    to_document,
)

ROOT = Path(__file__).resolve().parents[1]


def test_generated_schemas_are_current() -> None:
    """Byte-compare schema/generated/ against a fresh generation."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_schema

    for path, content in gen_schema.generate().items():
        current = path.read_text(encoding="utf-8")
        if path.suffix == ".ttl":
            # rdflib does not serialise blank nodes in a stable order, so the SHACL file is
            # compared as a graph rather than as bytes.
            assert _isomorphic(current, content), f"{path.name} is stale; run scripts/gen_schema.py"
        else:
            assert current == content, f"{path.name} is stale; run scripts/gen_schema.py"


def _isomorphic(left: str, right: str) -> bool:
    from rdflib import Graph
    from rdflib.compare import to_isomorphic

    same: bool = to_isomorphic(Graph().parse(data=left, format="turtle")) == to_isomorphic(
        Graph().parse(data=right, format="turtle")
    )
    return same


def test_generated_schema_pins_human_review() -> None:
    schema = json.loads((ROOT / "schema" / "generated" / "envelope.schema.json").read_text())
    assert schema["properties"]["requires_human_review"]["const"] is True


def _telemetry() -> Telemetry:
    return Telemetry(trace_id="0" * 32)


def _envelope(**overrides: object) -> Envelope:
    base: dict[str, object] = {
        "invocation_id": new_invocation_id(),
        "agent_id": "stub.abstain",
        "agent_version": "0.1.0",
        "completed_at": datetime.now(UTC),
        "outcome": Outcome(
            status=OutcomeStatus.ABSTAINED,
            reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
            statement="Stub agent; abstains unconditionally.",
        ),
        "telemetry": _telemetry(),
    }
    base.update(overrides)
    return Envelope(**base)


@pytest.mark.requirement("C13", "C15")
def test_abstained_envelope_validates() -> None:
    validate.validate_envelope(_envelope().to_document())


def test_uuid7_identifier_is_generated_and_matches_pattern() -> None:
    doc = _envelope().to_document()
    assert doc["invocation_id"][14] == "7"
    validate.validate_envelope(doc)


def test_energy_slots_present_and_not_measured() -> None:
    doc = _envelope().to_document()
    assert doc["telemetry"]["energy_estimate_j"] is None
    assert doc["telemetry"]["energy_method"] == "not_measured"


def test_succeeded_envelope_with_payload_validates() -> None:
    payload = Recommendations(
        items=[
            Recommendation(
                kind=RecommendationKind.FIELD_FORMAT,
                target="field:collection_date",
                resource=ResourceRef(fairsharing_id="FAIRsharing.b44s4"),
                rationale="Dates should be written to ISO 8601.",
                rationale_derivation=Derivation.TEMPLATE,
                evidence_hashes=["a" * 64],
            )
        ]
    )
    env = _envelope(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="One recommendation."),
        payload=payload,
        evidence=[
            EvidenceItem(
                source_id="FAIRsharing.b44s4",
                canonicalisation="json-sorted-utf8-v1",
                content_hash="a" * 64,
            )
        ],
    )
    validate.validate_envelope(env.to_document())


def test_succeeded_without_payload_is_rejected() -> None:
    env = _envelope(outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="x"))
    with pytest.raises(validate.ContractViolation, match="requires payload"):
        validate.validate_envelope(env.to_document())


def test_abstained_without_reason_code_is_rejected() -> None:
    env = _envelope(outcome=Outcome(status=OutcomeStatus.ABSTAINED, statement="x"))
    with pytest.raises(validate.ContractViolation, match="reason_code"):
        validate.validate_envelope(env.to_document())


def test_failed_requires_problem_details() -> None:
    env = _envelope(outcome=Outcome(status=OutcomeStatus.FAILED, statement="x"))
    with pytest.raises(validate.ContractViolation, match="RFC 9457"):
        validate.validate_envelope(env.to_document())
    ok = _envelope(
        outcome=Outcome(status=OutcomeStatus.FAILED, statement="x"),
        problem=ProblemDetails(
            type="https://w3id.org/data-director/problems/agent-error", title="boom"
        ),
    )
    validate.validate_envelope(ok.to_document())


def test_referred_requires_referred_to() -> None:
    env = _envelope(
        outcome=Outcome(
            status=OutcomeStatus.REFERRED,
            reason_code=ReasonCode.POLICY_REQUIRES_APPROVAL,
            statement="x",
        )
    )
    with pytest.raises(validate.ContractViolation, match="referred_to"):
        validate.validate_envelope(env.to_document())


def test_human_review_cannot_be_false() -> None:
    doc = _envelope().to_document()
    doc["requires_human_review"] = False
    with pytest.raises(validate.ContractViolation, match="requires_human_review"):
        validate.validate_envelope(doc)


def test_request_validates_and_rejects_bad_id() -> None:
    req = InvocationRequest(
        agent_id="stub.abstain", policy_bundle_ref="profile:default", input=DatasetProfile()
    )
    validate.validate_request(to_document(req))
    doc = to_document(req)
    doc["invocation_id"] = "not-a-uuid"
    with pytest.raises(validate.ContractViolation):
        validate.validate_request(doc)


def test_linkml_source_is_valid_yaml_for_the_generator() -> None:
    """gen-json-schema exits 0 on the source. Cheap guard against a broken edit."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "linkml.generators.jsonschemagen",
            "--top-class",
            "Envelope",
            str(ROOT / "schema" / "data_director.yaml"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
