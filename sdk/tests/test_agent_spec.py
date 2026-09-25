"""`AgentSpec`: derivations checked against the payload class and carried through the manifest,
and the contract version a description declares (ADR-0019)."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Literal

import pytest

import dd_sdk
from dd_sdk.agent import (
    AgentSpec,
    ContractVersionError,
    Derived,
    SpecError,
    describe,
    spec_from_description,
    typed_request,
)
from dd_sdk.contract.classes import ClassSchema, ClassSchemaError, schema_digest
from dd_sdk.contract.models import (
    DatasetProfile,
    Derivation,
    Frozen,
    GroundingMode,
    InvocationRequest,
    OpenInput,
    Recommendations,
)
from dd_sdk.contract.version import CONTRACT_VERSION, compatible

SPEC = AgentSpec(
    agent_id="test.spec",
    version="0.0.0",
    description="A spec for testing derivations.",
    requirement_ids=(),
    action_class="advise",
    accepts=(ClassSchema.of(DatasetProfile),),
    grounding_mode=GroundingMode.RETRIEVAL,
    payload=ClassSchema.of(Recommendations),
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
        dataclasses.replace(SPEC, payload=None)


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


# --- Class schemas carried by the card (ADR-0019) --------------------------------------------


def test_a_description_carries_each_class_schema_pinned_by_its_digest() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    assert set(entry["schemas"]) == {"DatasetProfile", "Recommendations"}
    for name, schema in entry["schemas"].items():
        assert schema["digest"] == schema_digest(schema["json_schema"]), name
    rebuilt = spec_from_description(entry)
    assert rebuilt.accepts == SPEC.accepts and rebuilt.payload == SPEC.payload
    assert rebuilt.payload is not None and rebuilt.payload.model is None  # schema only


def test_a_class_the_workbench_has_never_seen_is_accepted_by_its_schema() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    horoscope = entry["schemas"]["DatasetProfile"]["json_schema"]
    horoscope["title"] = "Horoscope"
    horoscope["properties"]["schema_class"]["enum"] = ["Horoscope"]
    entry["accepts"] = ["Horoscope"]
    entry["schemas"]["Horoscope"] = {"json_schema": horoscope, "digest": schema_digest(horoscope)}
    spec = spec_from_description(entry)
    assert spec.accepts_names() == ("Horoscope",)
    accepted = spec.accepted("Horoscope")
    assert accepted is not None and accepted.errors({"schema_class": "Horoscope"}) == []
    assert accepted.errors({"schema_class": "Horoscope", "stars": 5}) != []  # closed


def test_a_class_schema_that_is_missing_or_altered_is_refused() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    del entry["schemas"]["DatasetProfile"]
    with pytest.raises(SpecError, match="carries no schema"):
        spec_from_description(entry)
    entry = json.loads(json.dumps(describe(SPEC)))
    entry["schemas"]["DatasetProfile"]["json_schema"]["title"] = "Other"
    with pytest.raises(SpecError, match="does not match its digest"):
        spec_from_description(entry)


def test_a_class_schema_that_does_not_designate_its_class_is_refused() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    entry["accepts"] = ["Horoscope"]
    entry["schemas"]["Horoscope"] = entry["schemas"]["DatasetProfile"]  # says DatasetProfile
    with pytest.raises(SpecError, match="does not require schema_class = 'Horoscope'"):
        spec_from_description(entry)


def test_a_payload_class_that_does_not_mix_in_grounded_is_refused() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    entry["payload"] = "DatasetProfile"
    entry["derivations"] = {}
    with pytest.raises(SpecError, match="does not mix in Grounded"):
        spec_from_description(entry)


def test_a_model_that_disagrees_with_its_generated_schema_is_refused() -> None:
    class DatasetProfile(Frozen):  # the generated class's name, most of its fields missing
        schema_class: Literal["DatasetProfile"] = "DatasetProfile"
        title: str | None = None

    DatasetProfile.__module__ = "dd_sdk.contract.models"
    with pytest.raises(ClassSchemaError, match="only in the schema"):
        ClassSchema.of(DatasetProfile)


def test_the_agent_sees_its_own_model_and_the_workbench_the_document() -> None:
    request = InvocationRequest(
        agent_id="test.spec", input=OpenInput(schema_class="DatasetProfile", title="t")
    )
    typed = typed_request(SPEC, request)
    assert isinstance(typed.input, DatasetProfile) and typed.input.title == "t"
    rebuilt = spec_from_description(describe(SPEC))
    assert typed_request(rebuilt, request) is request  # no model on the workbench's side
