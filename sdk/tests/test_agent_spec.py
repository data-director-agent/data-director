"""`AgentSpec.derivations`: checked against the payload class, carried through the manifest."""

from __future__ import annotations

import dataclasses
import json

import pytest

from dd_sdk.agent import AgentSpec, Derived, SpecError, describe, spec_from_description
from dd_sdk.contract.models import DatasetProfile, Derivation, GroundingMode, Recommendations

SPEC = AgentSpec(
    agent_id="test.spec",
    version="0.0.0",
    description="A spec for testing derivations.",
    requirement_ids=(),
    action_class="advise",
    accepts=(DatasetProfile,),
    grounding_mode=GroundingMode.RETRIEVAL,
    payload_type=Recommendations,
    derivations={
        "items.kind": Derived(Derivation.LEXICAL, recorded_in="classification_derivation"),
        "items.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
        "searched.snapshot_ref": Derived(Derivation.REGISTRY),
    },
)


def test_derivations_round_trip_through_the_manifest() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    assert entry["derivations"]["items.rationale"] == {
        "how": "model",
        "recorded_in": "rationale_derivation",
    }
    assert spec_from_description(entry).derivations == SPEC.derivations


@pytest.mark.parametrize(
    ("path", "derived", "complaint"),
    [
        ("items.nope", Derived(Derivation.MODEL), "has no field 'nope'"),
        ("nope.kind", Derived(Derivation.MODEL), "has no nested field 'nope'"),
        ("items.kind", Derived(Derivation.LEXICAL, recorded_in="target"), "not a Derivation"),
        ("items.kind", Derived(Derivation.LEXICAL, recorded_in="missing"), "not a Derivation"),
    ],
)
def test_a_derivation_the_payload_class_does_not_support_is_refused(
    path: str, derived: Derived, complaint: str
) -> None:
    with pytest.raises(SpecError, match=complaint):
        dataclasses.replace(SPEC, derivations={path: derived})


def test_derivations_without_a_payload_are_refused() -> None:
    with pytest.raises(SpecError, match="declares no payload"):
        dataclasses.replace(SPEC, payload_type=None)


def test_a_derivation_outside_the_contract_enum_is_refused_from_a_card() -> None:
    entry = describe(SPEC)
    entry["derivations"] = {"items.rationale": {"how": "verified", "recorded_in": None}}
    with pytest.raises(SpecError, match="malformed derivations"):
        spec_from_description(entry)
