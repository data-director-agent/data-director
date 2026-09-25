"""`AgentSpec`: derivations checked against the payload class and carried through the manifest,
and the contract version a description declares (ADR-0019)."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

import dd_sdk
from dd_sdk.agent import (
    AgentSpec,
    ContractVersionError,
    Derived,
    SpecError,
    describe,
    spec_from_description,
)
from dd_sdk.contract.models import DatasetProfile, Derivation, GroundingMode, Recommendations
from dd_sdk.contract.version import CONTRACT_VERSION, compatible

SPEC = AgentSpec(
    agent_id="test.spec",
    version="0.0.0",
    description="A spec for testing derivations.",
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


# --- The contract version (ADR-0019) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "current", "ok"),
    [
        ("0.6.0", "0.6.0", True),
        ("0.6.3", "0.6.0", True),  # a patch never breaks compatibility
        ("0.5.9", "0.6.0", False),  # before 1.0 a minor version may break it
        ("0.7.0", "0.6.0", False),
        ("1.4.0", "1.2.0", True),  # from 1.0 only the major version counts
        ("2.0.0", "1.2.0", False),
        ("0.6", "0.6.0", False),  # not a version
    ],
)
def test_the_caret_rule_decides_which_contract_versions_are_compatible(
    declared: str, current: str, ok: bool
) -> None:
    assert compatible(declared, current) is ok


def test_the_contract_version_is_the_core_schemas_version() -> None:
    source = Path(dd_sdk.__file__).parent / "schema" / "data_director.yaml"
    assert f"\nversion: {CONTRACT_VERSION}\n" in source.read_text(encoding="utf-8")


def test_a_description_carries_the_contract_version_and_round_trips() -> None:
    entry = describe(SPEC)
    assert entry["contract_version"] == CONTRACT_VERSION
    assert spec_from_description(entry).contract_version == CONTRACT_VERSION


@pytest.mark.parametrize("declared", [None, "99.0.0"])
def test_a_description_under_another_contract_is_a_contract_mismatch(
    declared: str | None,
) -> None:
    entry = describe(SPEC)
    entry["contract_version"] = declared
    entry["accepts"] = ["Horoscope"]  # under another contract the rest need not parse
    with pytest.raises(ContractVersionError, match=re.escape(CONTRACT_VERSION)):
        spec_from_description(entry)
