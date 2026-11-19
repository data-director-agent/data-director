"""Property tests for the contract validators (docs/specs/contract.md).

A document that breaks the contract is reported as a `ContractViolation` listing what is wrong,
whatever its shape; the validators never fail with an exception of their own, such as a
`TypeError` on a field of the wrong type.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from dd_sdk.contract import validate
from dd_sdk.contract.models import (
    Envelope,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    Outcome,
    OutcomeStatus,
    Principal,
    Reply,
    Telemetry,
    input_source_id,
    new_invocation_id,
)
from dd_sdk.contract.version import CONTRACT_VERSION
from dd_sdk.evidence import CANONICALISATIONS, INPUT_CANONICALISATION

json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=12),
    lambda inner: (
        st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=8), inner, max_size=3)
    ),
    max_leaves=8,
)
hashes = st.sampled_from(["1" * 64, "a" * 64]) | json_values

# Values near what each envelope field holds, so that generated documents reach the conditional
# rules past the first check, mixed with arbitrary JSON in every position.
outcomes = st.fixed_dictionaries(
    {},
    optional={
        "status": st.sampled_from([s.value for s in OutcomeStatus]) | json_values,
        "reason_code": json_values,
        "referred_to": json_values,
        "statement": st.text(max_size=12),
    },
)
evidence_items = st.fixed_dictionaries(
    {},
    optional={
        "source_id": st.sampled_from(["input:x", "invocation:y", "S"]) | json_values,
        "canonicalisation": st.sampled_from(sorted(CANONICALISATIONS)) | json_values,
        "content_hash": hashes,
    },
)
payloads = st.fixed_dictionaries(
    {},
    optional={
        "schema_class": json_values,
        "grounded_on": st.lists(json_values, max_size=2) | json_values,
    },
)
delegations = st.fixed_dictionaries(
    {}, optional={"delegated_invocation_id": json_values, "content_hash": hashes}
)
envelope_fields: dict[str, st.SearchStrategy[Any]] = {
    "outcome": outcomes,
    "grounding_mode": st.sampled_from([m.value for m in GroundingMode]),
    "payload": payloads,
    "payload_schema": st.just("c" * 64),
    "problem": st.dictionaries(st.text(max_size=8), json_values, max_size=2),
    "evidence": st.lists(evidence_items | json_values, max_size=3),
    "delegations": st.lists(delegations | json_values, max_size=2),
}
envelope_like = st.fixed_dictionaries(
    {}, optional={key: values | json_values for key, values in envelope_fields.items()}
)
anything = st.dictionaries(st.text(max_size=12), json_values, max_size=6)


def _valid_envelope() -> dict[str, Any]:
    """A succeeded `input_only` envelope that passes every rule."""
    invocation_id = new_invocation_id()
    source_id = input_source_id(invocation_id)
    return Envelope(
        invocation_id=invocation_id,
        agent_id="stub.echo",
        agent_version="0.1.0",
        completed_at=datetime.now(UTC),
        grounding_mode=GroundingMode.INPUT_ONLY,
        policy_bundle_ref="profile:default@v2",
        policy_digest="0" * 64,
        acting_for=Principal(
            principal_id="https://orcid.org/0000-0002-1825-0097", name="Josiah Carberry"
        ),
        contract_version=CONTRACT_VERSION,
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Done."),
        payload=Reply(
            reply_text="r",
            reply_derivation="template",
            grounded_on=[GroundingRef(source_id=source_id, content_hash="1" * 64)],
        ),
        payload_schema="c" * 64,
        evidence=[
            EvidenceItem(
                source_id=source_id,
                canonicalisation=INPUT_CANONICALISATION,
                content_hash="1" * 64,
            )
        ],
        telemetry=Telemetry(),
    ).to_document()


VALID = _valid_envelope()


def _reported(check: Any, document: dict[str, Any]) -> list[str]:
    """What `check` finds wrong with `document`: nothing, or a violation's messages."""
    try:
        check(document)
    except validate.ContractViolation as violation:
        assert violation.messages, "a violation lists what is wrong"
        assert all(isinstance(m, str) for m in violation.messages)
        return violation.messages
    return []


def test_the_valid_envelope_validates() -> None:
    assert _reported(validate.validate_envelope, VALID) == []


@given(document=anything | envelope_like)
def test_the_envelope_rules_report_any_document_without_raising(document: dict[str, Any]) -> None:
    errors = validate.conditional_errors(document)
    assert isinstance(errors, list) and all(isinstance(e, str) for e in errors)
    _reported(validate.validate_envelope, document)


@given(changes=envelope_like)
def test_a_valid_envelope_with_any_field_changed_is_reported_without_raising(
    changes: dict[str, Any],
) -> None:
    document = {**VALID, **changes}
    validate.conditional_errors(document)
    _reported(validate.validate_envelope, document)


@given(document=anything)
def test_the_request_rules_report_any_document_without_raising(document: dict[str, Any]) -> None:
    _reported(validate.validate_request, document)
