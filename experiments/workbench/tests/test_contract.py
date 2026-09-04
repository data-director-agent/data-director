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
    Claim,
    DatasetProfile,
    Derivation,
    Envelope,
    EvidenceItem,
    FactCheck,
    Finding,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    MetadataRecord,
    Outcome,
    OutcomeStatus,
    ProblemDetails,
    QualityReview,
    ReasonCode,
    Recommendation,
    RecommendationKind,
    Recommendations,
    ResourceRef,
    Severity,
    Telemetry,
    Verdict,
    input_source_id,
    new_invocation_id,
    parse_input,
    to_document,
)
from workbench.evidence import DOCUMENT_CANONICALISATION, INPUT_CANONICALISATION

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


INV = new_invocation_id()
INPUT_HASH = "1" * 64


def _envelope(**overrides: object) -> Envelope:
    base: dict[str, object] = {
        "invocation_id": INV,
        "agent_id": "stub.abstain",
        "agent_version": "0.1.0",
        "completed_at": datetime.now(UTC),
        "grounding_mode": GroundingMode.NONE,
        "outcome": Outcome(
            status=OutcomeStatus.ABSTAINED,
            reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
            statement="Stub agent; abstains unconditionally.",
        ),
        "telemetry": _telemetry(),
    }
    base.update(overrides)
    return Envelope(**base)


# Deliberately unmarked. requires_human_review=true flags every output for review, but C15 also
# asks for quality checks on outputs, which the workbench does not perform; C13 is substantiated
# by the harness tests (stored, traced, attributable), not by a document validating.
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


def _input_ref() -> GroundingRef:
    return GroundingRef(source_id=input_source_id(INV), content_hash=INPUT_HASH)


def _input_evidence() -> EvidenceItem:
    return EvidenceItem(
        source_id=input_source_id(INV),
        canonicalisation=INPUT_CANONICALISATION,
        content_hash=INPUT_HASH,
    )


def _succeeded(**overrides: object) -> Envelope:
    return _envelope(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Done."), **overrides
    )


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD")
def test_each_payload_class_validates_with_grounded_on() -> None:
    ref = GroundingRef(source_id="FAIRsharing.b44s4", content_hash="a" * 64)
    ev = EvidenceItem(
        source_id="FAIRsharing.b44s4", canonicalisation="json-sorted-utf8-v1", content_hash="a" * 64
    )
    recs = Recommendations(
        items=[
            Recommendation(
                kind=RecommendationKind.FIELD_FORMAT,
                target="field:collection_date",
                resource=ResourceRef(fairsharing_id="FAIRsharing.b44s4"),
                rationale="Dates should be written to ISO 8601.",
                rationale_derivation=Derivation.TEMPLATE,
                grounded_on=[ref],
            )
        ],
        grounded_on=[ref],
    )
    validate.validate_envelope(
        _succeeded(
            grounding_mode=GroundingMode.RETRIEVAL, payload=recs, evidence=[ev]
        ).to_document()
    )
    check = FactCheck(
        verdict=Verdict.SUPPORTED,
        rationale="r",
        rationale_derivation=Derivation.TEMPLATE,
        grounded_on=[ref],
    )
    validate.validate_envelope(
        _succeeded(
            grounding_mode=GroundingMode.RETRIEVAL, payload=check, evidence=[ev]
        ).to_document()
    )
    review = QualityReview(
        score=0.5,
        findings=[
            Finding(
                criterion="licence_present",
                severity=Severity.ERROR,
                message="No licence.",
                derivation=Derivation.LEXICAL,
                grounded_on=[_input_ref()],
            )
        ],
        grounded_on=[_input_ref()],
    )
    doc = _succeeded(
        grounding_mode=GroundingMode.INPUT_ONLY, payload=review, evidence=[_input_evidence()]
    ).to_document()
    validate.validate_envelope(doc)
    assert doc["payload"]["schema_class"] == "QualityReview"


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD")
def test_payload_without_grounded_on_or_schema_class_is_rejected() -> None:
    doc = _succeeded(
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=QualityReview(grounded_on=[_input_ref()]),
        evidence=[_input_evidence()],
    ).to_document()
    del doc["payload"]["grounded_on"]
    with pytest.raises(validate.ContractViolation, match="grounded_on"):
        validate.validate_envelope(doc)
    doc = _succeeded(
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=QualityReview(grounded_on=[_input_ref()]),
        evidence=[_input_evidence()],
    ).to_document()
    del doc["payload"]["schema_class"]
    with pytest.raises(validate.ContractViolation, match="schema_class"):
        validate.validate_envelope(doc)


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_envelope_requires_a_grounding_mode() -> None:
    doc = _envelope().to_document()
    del doc["grounding_mode"]
    with pytest.raises(validate.ContractViolation, match="grounding_mode"):
        validate.validate_envelope(doc)


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_input_grounded_success_must_cite_only_the_input() -> None:
    payload = QualityReview(grounded_on=[_input_ref()])
    with pytest.raises(validate.ContractViolation, match="citing the input"):
        validate.validate_envelope(
            _succeeded(grounding_mode=GroundingMode.INPUT_ONLY, payload=payload).to_document()
        )
    foreign = EvidenceItem(
        source_id="S", canonicalisation=DOCUMENT_CANONICALISATION, content_hash="b" * 64
    )
    with pytest.raises(validate.ContractViolation, match="no evidence other than the input"):
        validate.validate_envelope(
            _succeeded(
                grounding_mode=GroundingMode.NONE,
                payload=payload,
                evidence=[_input_evidence(), foreign],
            ).to_document()
        )


@pytest.mark.requirement("DD-GROUNDING-MODE")
def test_retrieval_success_requires_non_empty_grounded_on() -> None:
    with pytest.raises(validate.ContractViolation, match="non-empty grounded_on"):
        validate.validate_envelope(
            _succeeded(
                grounding_mode=GroundingMode.RETRIEVAL, payload=QualityReview()
            ).to_document()
        )


@pytest.mark.requirement("DD-EVIDENCE")
def test_unknown_canonicalisation_is_rejected() -> None:
    env = _envelope(
        evidence=[
            EvidenceItem(source_id="S", canonicalisation="md5-of-vibes", content_hash="a" * 64)
        ]
    )
    with pytest.raises(validate.ContractViolation, match="unknown canonicalisation"):
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


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_every_input_class_validates_and_is_discriminated_by_schema_class() -> None:
    for inp in (
        DatasetProfile(title="t"),
        MetadataRecord(identifier="doi:10.1/x", licence="CC-BY-4.0"),
        Claim(text="A DOI does not change."),
    ):
        req = InvocationRequest(
            agent_id="stub.abstain", policy_bundle_ref="profile:default", input=inp
        )
        doc = to_document(req)
        validate.validate_request(doc)
        assert doc["input"]["schema_class"] == type(inp).__name__
        assert type(parse_input(doc["input"])) is type(inp)


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_input_without_schema_class_is_rejected() -> None:
    """`{}` must not silently parse as a DatasetProfile (every slot of which is optional)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        parse_input({})
    req = to_document(
        InvocationRequest(agent_id="a", policy_bundle_ref="profile:default", input=Claim(text="x"))
    )
    del req["input"]["schema_class"]
    with pytest.raises(validate.ContractViolation):
        validate.validate_request(req)


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
