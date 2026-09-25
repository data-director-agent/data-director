"""The contract layer: generated artefacts are current, models validate against the schema, and
the conditional rules hold."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dd_sdk.contract import validate
from dd_sdk.contract.models import (
    Claim,
    ConversationTurn,
    DatasetProfile,
    Delegation,
    Derivation,
    Envelope,
    EvidenceItem,
    FactCheck,
    Finding,
    Greeting,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Message,
    MetadataRecord,
    Outcome,
    OutcomeStatus,
    Principal,
    PrincipalKind,
    ProblemDetails,
    QualityReview,
    ReasonCode,
    Recommendation,
    RecommendationKind,
    Recommendations,
    Reply,
    Salutation,
    Severity,
    Telemetry,
    TurnRole,
    Verdict,
    input_source_id,
    invocation_source_id,
    new_invocation_id,
    parse_input,
    to_document,
)
from dd_sdk.evidence import (
    CANONICALISATIONS,
    DOCUMENT_CANONICALISATION,
    ENVELOPE_CANONICALISATION,
    INPUT_CANONICALISATION,
    content_hash,
    envelope_hash,
    project,
    verify,
)
from dd_sdk.schema import gen

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "src" / "dd_sdk" / "schema"


def test_generated_schemas_are_current() -> None:
    """Byte-compare schema/generated/ against a fresh generation, and find no file left over."""
    outputs = gen.generate()
    for path, content in outputs.items():
        assert path.exists(), f"{path.name} is missing; run `uv run dd-gen-schema`"
        current = path.read_text(encoding="utf-8")
        if path.suffix == ".ttl":
            # rdflib does not serialise blank nodes in a stable order, so the SHACL file is
            # compared as a graph rather than as bytes.
            assert _isomorphic(current, content), (
                f"{path.name} is stale; run `uv run dd-gen-schema`"
            )
        else:
            assert current == content, f"{path.name} is stale; run `uv run dd-gen-schema`"
    stale = set((SCHEMA / "generated").iterdir()) - set(outputs)
    assert not stale, f"{sorted(p.name for p in stale)} are no longer generated; delete them"


def test_a_class_schema_is_closed_self_contained_and_says_it_is_generated() -> None:
    schema = json.loads((SCHEMA / "generated" / "Reply.schema.json").read_text(encoding="utf-8"))
    assert schema["$comment"].endswith("Do not edit.")
    assert schema["title"] == "Reply" and schema["additionalProperties"] is False
    assert set(schema["$defs"]) == {"Derivation", "GroundingRef"}  # only what Reply reaches
    assert schema["properties"]["schema_class"]["enum"] == ["Reply"]
    assert {"schema_class", "grounded_on"} <= set(schema["required"])


def test_generated_properties_keep_the_linkml_slot_order() -> None:
    """The viewer shows fields in schema order, so the generator's alphabetical order is undone."""
    schema = json.loads((SCHEMA / "generated" / "envelope.schema.json").read_text(encoding="utf-8"))
    assert list(schema["properties"])[:3] == ["invocation_id", "agent_id", "agent_version"]
    assert list(schema["$defs"]["Recommendation"]["properties"]) == [
        "kind",
        "target",
        "score",
        "rationale",
        "rationale_derivation",
        "classification_derivation",
        "grounded_on",
    ]


def _isomorphic(left: str, right: str) -> bool:
    from rdflib import Graph
    from rdflib.compare import to_isomorphic

    same: bool = to_isomorphic(Graph().parse(data=left, format="turtle")) == to_isomorphic(
        Graph().parse(data=right, format="turtle")
    )
    return same


def test_generated_schema_pins_human_review() -> None:
    schema = json.loads((SCHEMA / "generated" / "envelope.schema.json").read_text())
    assert schema["properties"]["requires_human_review"]["const"] is True


def _telemetry() -> Telemetry:
    return Telemetry(trace_id="0" * 32)


INV = new_invocation_id()
# The ORCID documentation's example researcher.
PRINCIPAL = Principal(principal_id="https://orcid.org/0000-0002-1825-0097", name="Josiah Carberry")
INPUT_HASH = "1" * 64


def _envelope(**overrides: object) -> Envelope:
    base: dict[str, object] = {
        "invocation_id": INV,
        "agent_id": "stub.abstain",
        "agent_version": "0.1.0",
        "completed_at": datetime.now(UTC),
        "grounding_mode": GroundingMode.NONE,
        "policy_bundle_ref": "profile:default@v2",
        "policy_digest": "0" * 64,
        "acting_for": PRINCIPAL,
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
# asks for quality checks on outputs, which the workbench does not perform; C13.1 is substantiated
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

    greeting = Greeting(
        greeting_text="Hello, world!",
        greeting_derivation=Derivation.TEMPLATE,
        grounded_on=[_input_ref()],
    )
    doc = _succeeded(
        grounding_mode=GroundingMode.NONE, payload=greeting, evidence=[_input_evidence()]
    ).to_document()
    validate.validate_envelope(doc)
    assert doc["payload"]["schema_class"] == "Greeting"


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


@pytest.mark.requirement("DD-ACTS-FOR")
def test_an_envelope_names_the_human_it_acted_for() -> None:
    doc = _envelope().to_document()
    assert doc["acting_for"] == {
        "principal_id": "https://orcid.org/0000-0002-1825-0097",
        "name": "Josiah Carberry",
        "principal_kind": "person",
        "assurance": "asserted",
    }
    validate.validate_envelope(doc)
    del doc["acting_for"]
    with pytest.raises(validate.ContractViolation, match="acting_for"):
        validate.validate_envelope(doc)


@pytest.mark.requirement("DD-ACTS-FOR")
@pytest.mark.parametrize(
    ("principal_id", "name"),
    [("0000-0002-1825-0097", "Josiah Carberry"), ("https://orcid.org/x y", "J"), ("urn:x", "")],
)
def test_a_principal_needs_an_absolute_iri_and_a_name(principal_id: str, name: str) -> None:
    with pytest.raises(ValueError):
        Principal(principal_id=principal_id, name=name)
    doc = _envelope().to_document()
    doc["acting_for"] = {**doc["acting_for"], "principal_id": principal_id, "name": name}
    with pytest.raises(validate.ContractViolation):
        validate.validate_envelope(doc)


def test_an_accountable_role_is_a_principal() -> None:
    role = Principal(
        principal_id="urn:example:role:data-steward",
        name="Data steward, Research Data Service",
        principal_kind=PrincipalKind.ACCOUNTABLE_ROLE,
    )
    validate.validate_envelope(_envelope(acting_for=role).to_document())


@pytest.mark.requirement("DD-ACTS-FOR")
def test_a_request_cannot_say_whom_it_acts_for() -> None:
    doc = to_document(InvocationRequest(agent_id="stub.abstain", input=DatasetProfile()))
    doc["acting_for"] = to_document(PRINCIPAL)
    # The model refuses it, and every transport parses the request with the model before the
    # conductor sees it. TODO: the generated request schema's root is open, so a consumer that
    # validates with the JSON Schema alone would not refuse it.
    with pytest.raises(ValueError, match="acting_for"):
        InvocationRequest.model_validate(doc)


def test_request_validates_and_rejects_bad_id() -> None:
    req = InvocationRequest(agent_id="stub.abstain", input=DatasetProfile())
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
        Salutation(greeted_name="world"),
        Message(message_text="hello"),
    ):
        req = InvocationRequest(agent_id="stub.abstain", input=inp)
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
    req = to_document(InvocationRequest(agent_id="a", input=Claim(text="x")))
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
            str(SCHEMA / "data_director.yaml"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --- Conversation and delegation (ADR-0012) ---------------------------------------------------


def _delegation(child: str, content_hash: str = "c" * 64) -> Delegation:
    return Delegation(
        delegated_invocation_id=child,
        delegated_agent_id="hello.world",
        delegated_agent_version="0.1.0",
        delegated_status=OutcomeStatus.SUCCEEDED,
        content_hash=content_hash,
    )


def _envelope_evidence(child: str, content_hash: str = "c" * 64) -> EvidenceItem:
    return EvidenceItem(
        source_id=invocation_source_id(child),
        canonicalisation=ENVELOPE_CANONICALISATION,
        content_hash=content_hash,
    )


@pytest.mark.requirement("DD-CONVERSATION")
def test_message_and_reply_validate_and_are_discriminated() -> None:
    conv = new_invocation_id()
    message = Message(
        message_text="hello Joe",
        history=[
            ConversationTurn(role=TurnRole.USER, turn_text="hi"),
            ConversationTurn(
                role=TurnRole.AGENT,
                turn_text="Hello!",
                turn_agent_id="director.stub",
                turn_agent_version="0.1.0",
                turn_invocation_id=new_invocation_id(),
            ),
        ],
    )
    req = InvocationRequest(
        agent_id="director.stub",
        conversation_id=conv,
        input=message,
    )
    doc = to_document(req)
    validate.validate_request(doc)
    assert doc["conversation_id"] == conv
    assert type(parse_input(doc["input"])) is Message

    child = new_invocation_id()
    reply = Reply(
        reply_text="Routed.",
        reply_derivation=Derivation.TEMPLATE,
        grounded_on=[
            _input_ref(),
            GroundingRef(source_id=f"invocation:{child}", content_hash="c" * 64),
        ],
    )
    env = _succeeded(
        grounding_mode=GroundingMode.DELEGATION,
        payload=reply,
        evidence=[_input_evidence(), _envelope_evidence(child)],
        conversation_id=conv,
        delegations=[_delegation(child)],
    ).to_document()
    validate.validate_envelope(env)
    assert env["payload"]["schema_class"] == "Reply"
    assert env["delegations"][0]["delegated_invocation_id"] == child


@pytest.mark.requirement("DD-CONVERSATION")
def test_bad_conversation_id_is_rejected() -> None:
    doc = to_document(InvocationRequest(agent_id="a", input=Message(message_text="x")))
    doc["conversation_id"] = "not-a-uuid"
    with pytest.raises(validate.ContractViolation, match="conversation_id"):
        validate.validate_request(doc)


def test_envelope_without_delegations_omits_the_key() -> None:
    assert "delegations" not in _envelope().to_document()


@pytest.mark.requirement("DD-DELEGATION")
def test_delegation_evidence_must_be_the_input_or_a_recorded_delegation() -> None:
    child = new_invocation_id()
    reply = Reply(reply_text="r", reply_derivation=Derivation.TEMPLATE, grounded_on=[_input_ref()])
    with pytest.raises(validate.ContractViolation, match="citing the input"):
        validate.validate_envelope(
            _succeeded(
                grounding_mode=GroundingMode.DELEGATION,
                payload=reply,
                evidence=[_envelope_evidence(child)],
                delegations=[_delegation(child)],
            ).to_document()
        )
    with pytest.raises(validate.ContractViolation, match="neither the input nor a recorded"):
        validate.validate_envelope(
            _succeeded(
                grounding_mode=GroundingMode.DELEGATION,
                payload=reply,
                evidence=[_input_evidence(), _envelope_evidence(child, "d" * 64)],
                delegations=[_delegation(child)],
            ).to_document()
        )


@pytest.mark.requirement("DD-EVIDENCE")
@pytest.mark.parametrize("name", sorted(CANONICALISATIONS))
def test_evidence_content_reproduces_its_hash(name: str) -> None:
    """ADR-0015: the projection is what is hashed, and survives the envelope round trip."""
    record = {"fairsharing_id": "FAIRsharing.b44s4", "name": "ISO 8601", "subjects": ["b", "a"]}
    digest = content_hash(record, name)
    content = project(record, name)
    assert project(content, name) == content
    env = _envelope(
        evidence=[
            EvidenceItem(
                source_id="FAIRsharing.b44s4",
                canonicalisation=name,
                content_hash=digest,
                content=content,
            )
        ]
    )
    doc = env.to_document()
    validate.validate_envelope(doc)
    stored = json.loads(json.dumps(doc))["evidence"][0]
    assert verify(stored["content"], name, stored["content_hash"])
    assert not verify({**stored["content"], "name": "ISO 8602"}, name, stored["content_hash"])


@pytest.mark.requirement("DD-EVIDENCE")
def test_envelope_hash_is_reproducible_from_the_stored_document() -> None:
    doc = _envelope().to_document()
    stored = json.loads(json.dumps(doc, indent=2))  # the store's formatting does not matter
    assert envelope_hash(stored) == envelope_hash(doc)
    assert ENVELOPE_CANONICALISATION in CANONICALISATIONS
