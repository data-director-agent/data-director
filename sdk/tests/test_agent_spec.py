"""`AgentSpec`: derivations checked against the payload class and carried through the manifest,
and the contract version a description declares (docs/specs/contract.md)."""

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
    ModelUse,
    RunContext,
    Setting,
    SpecError,
    describe,
    setting,
    spec_from_description,
    typed_request,
)
from dd_sdk.contract.classes import ClassSchema, ClassSchemaError, schema_digest
from dd_sdk.contract.models import (
    Derivation,
    Frozen,
    GroundingMode,
    InvocationRequest,
    Message,
    OpenInput,
)
from dd_sdk.contract.version import CONTRACT_VERSION, compatible
from dd_sdk.skills import SkillUse
from dd_sdk.tools import ToolUse

# The SDK knows no agent's classes, so this module brings its own, as an agent would
# (docs/specs/contract.md): an input class and a payload class with nested items and an optional
# nested object, written as `dd-gen-schema` would write them.
DERIVATION = {"enum": [d.value for d in Derivation], "type": "string"}
GROUNDING_REF = {
    "additionalProperties": False,
    "properties": {"source_id": {"type": "string"}, "content_hash": {"type": "string"}},
    "required": ["source_id", "content_hash"],
    "type": "object",
}
SURVEY = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": False,
    "properties": {
        "schema_class": {"enum": ["Survey"], "type": "string"},
        "title": {"type": ["string", "null"]},
    },
    "required": ["schema_class"],
    "title": "Survey",
    "type": "object",
}
FINDINGS = {
    "$defs": {
        "Derivation": DERIVATION,
        "GroundingRef": GROUNDING_REF,
        "Item": {
            "additionalProperties": False,
            "properties": {
                "kind": {"type": "string"},
                "rationale": {"type": "string"},
                "rationale_derivation": {"$ref": "#/$defs/Derivation"},
                "classification_derivation": {
                    "anyOf": [{"$ref": "#/$defs/Derivation"}, {"type": "null"}]
                },
                "target": {"type": "string"},
            },
            "required": ["kind", "rationale", "rationale_derivation", "target"],
            "title": "Item",
            "type": "object",
        },
        "Searched": {
            "additionalProperties": False,
            "properties": {"snapshot_ref": {"type": ["string", "null"]}},
            "title": "Searched",
            "type": "object",
        },
    },
    "$schema": "http://json-schema.org/draft-07/schema#",
    "additionalProperties": False,
    "properties": {
        "schema_class": {"enum": ["Findings"], "type": "string"},
        "items": {"items": {"$ref": "#/$defs/Item"}, "type": ["array", "null"]},
        "searched": {"anyOf": [{"$ref": "#/$defs/Searched"}, {"type": "null"}]},
        "grounded_on": {"items": {"$ref": "#/$defs/GroundingRef"}, "type": "array"},
    },
    "required": ["schema_class", "grounded_on"],
    "title": "Findings",
    "type": "object",
}


class Survey(Frozen):
    schema_class: Literal["Survey"] = "Survey"
    title: str | None = None


SURVEY_CLASS = ClassSchema("Survey", SURVEY, schema_digest(SURVEY), Survey)
FINDINGS_CLASS = ClassSchema("Findings", FINDINGS, schema_digest(FINDINGS))

SPEC = AgentSpec(
    agent_id="test.spec",
    version="0.0.0",
    description="A spec for testing derivations.",
    action_class="advise",
    accepts=(SURVEY_CLASS,),
    grounding_mode=GroundingMode.RETRIEVAL,
    payload=FINDINGS_CLASS,
    derivations={
        "items.kind": Derived(Derivation.LEXICAL, recorded_in="classification_derivation"),
        "items.rationale": Derived(Derivation.MODEL, recorded_in="rationale_derivation"),
        "searched.snapshot_ref": Derived(Derivation.REGISTRY),
    },
    skills=(SkillUse("licence-choice", "v1.0.0", "0123456789abcdef" * 4),),
    tools=(ToolUse("spdx", ("get_licence", "search_licences")),),
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


def test_the_models_an_agent_sends_data_to_round_trip_through_the_manifest() -> None:
    spec = dataclasses.replace(SPEC, models=(ModelUse("anthropic", "claude-x", "hosted"),))
    entry = describe(spec)
    assert entry["models"] == [{"provider": "anthropic", "model": "claude-x", "hosting": "hosted"}]
    assert spec_from_description(entry).models == spec.models


def test_a_model_the_agent_relies_on_for_tool_calls_is_declared_so() -> None:
    uses = (
        ModelUse("anthropic", "claude-x", "hosted", tools=True),
        ModelUse("anthropic", "claude-y", "hosted"),
    )
    entry = describe(dataclasses.replace(SPEC, models=uses))
    assert entry["models"][0]["tools"] is True
    assert "tools" not in entry["models"][1]
    assert spec_from_description(entry).models == uses


def test_a_model_whose_tools_is_not_a_boolean_is_refused() -> None:
    entry = describe(SPEC)
    entry["models"] = [
        {"provider": "anthropic", "model": "claude-x", "hosting": "hosted", "tools": "yes"}
    ]
    with pytest.raises(SpecError):
        spec_from_description(entry)


def test_a_description_without_models_declares_none() -> None:
    entry = describe(SPEC)
    assert entry["models"] == []
    del entry["models"]
    assert spec_from_description(entry).models == ()


def test_the_steps_an_agent_serves_round_trip_through_the_manifest() -> None:
    spec = dataclasses.replace(SPEC, serves=("governance.policies", "deposit.validate"))
    entry = describe(spec)
    assert entry["serves"] == ["governance.policies", "deposit.validate"]
    assert spec_from_description(entry).serves == ("governance.policies", "deposit.validate")


def test_a_description_without_serves_serves_nothing() -> None:
    entry = describe(SPEC)
    del entry["serves"]
    assert spec_from_description(entry).serves == ()


def test_the_persona_title_round_trips_through_the_manifest() -> None:
    spec = dataclasses.replace(SPEC, title="Metadata Librarian")
    entry = describe(spec)
    assert entry["title"] == "Metadata Librarian"
    assert spec_from_description(entry).title == "Metadata Librarian"


@pytest.mark.parametrize("icon", ["📚", "🧑🏽‍🔬", "⚖️"])
def test_the_persona_icon_round_trips_through_the_manifest(icon: str) -> None:
    entry = json.loads(json.dumps(describe(dataclasses.replace(SPEC, icon=icon))))
    assert entry["icon"] == icon
    assert spec_from_description(entry).icon == icon


def test_a_description_without_an_icon_has_none() -> None:
    entry = describe(SPEC)
    del entry["icon"]
    assert spec_from_description(entry).icon == ""


@pytest.mark.parametrize("icon", ["book", "📚 📚", "📚📚📚📚📚📚📚📚📚", "1"])
def test_an_icon_that_is_not_one_emoji_is_refused(icon: str) -> None:
    with pytest.raises(SpecError, match="icon"):
        dataclasses.replace(SPEC, icon=icon)


def test_a_description_whose_icon_is_not_a_string_is_refused() -> None:
    entry = {**describe(SPEC), "icon": 7}
    with pytest.raises(SpecError, match="icon"):
        spec_from_description(entry)


def test_the_settings_an_agent_offers_round_trip_through_the_manifest() -> None:
    offered = {"depth": Setting(("shallow", "deep"), "deep", "How far it looks.")}
    entry = json.loads(json.dumps(describe(dataclasses.replace(SPEC, settings=offered))))
    assert entry["settings"]["depth"]["default"] == "deep"
    assert spec_from_description(entry).settings == offered


def test_a_description_without_settings_offers_none() -> None:
    entry = describe(SPEC)
    del entry["settings"]
    assert spec_from_description(entry).settings == {}


@pytest.mark.parametrize(
    "offered",
    [
        Setting(("shallow", "deep"), "sideways"),
        Setting((), ""),
        Setting(("deep", "deep"), "deep"),
    ],
)
def test_a_setting_whose_default_is_not_a_choice_is_refused(offered: Setting) -> None:
    with pytest.raises(SpecError):
        dataclasses.replace(SPEC, settings={"depth": offered})


def test_an_agent_reads_the_setting_sent_or_its_default() -> None:
    spec = dataclasses.replace(SPEC, settings={"depth": Setting(("shallow", "deep"), "shallow")})
    tracer = object()

    def ctx(sent: dict[str, str]) -> RunContext:
        return RunContext(tracer=tracer, input_ref="", input_hash="", settings=sent)  # type: ignore[arg-type]

    assert setting(ctx({"depth": "deep"}), spec, "depth") == "deep"
    assert setting(ctx({}), spec, "depth") == "shallow"
    with pytest.raises(KeyError):
        setting(ctx({}), spec, "breadth")


def test_a_description_without_a_title_has_none() -> None:
    entry = describe(SPEC)
    del entry["title"]
    assert spec_from_description(entry).title == ""


@pytest.mark.parametrize("serves", [("R3",), ("R13",), ("C1",), ("R3.1",), ("governance.unknown",)])
def test_serving_anything_but_a_step_is_refused(serves: tuple[str, ...]) -> None:
    with pytest.raises(SpecError, match="not process flow steps"):
        dataclasses.replace(SPEC, serves=serves)
    entry = describe(SPEC)
    entry["serves"] = list(serves)
    with pytest.raises(SpecError, match="not process flow steps"):
        spec_from_description(entry)


def test_serving_a_step_that_is_out_of_scope_for_now_is_refused() -> None:
    with pytest.raises(SpecError, match="out of scope for now"):
        dataclasses.replace(SPEC, serves=("setup.dmp-create",))
    entry = describe(SPEC)
    entry["serves"] = ["post.dmp-update"]
    with pytest.raises(SpecError, match="out of scope for now"):
        spec_from_description(entry)


def test_a_model_hosted_somewhere_unknown_is_refused() -> None:
    entry = describe(SPEC)
    entry["models"] = [{"provider": "p", "model": "m", "hosting": "elsewhere"}]
    with pytest.raises(SpecError, match="malformed models"):
        spec_from_description(entry)


def test_derivations_without_a_payload_are_refused() -> None:
    with pytest.raises(SpecError, match="declares no payload"):
        dataclasses.replace(SPEC, payload=None)


def test_a_derivation_outside_the_contract_enum_is_refused_from_a_card() -> None:
    entry = describe(SPEC)
    entry["derivations"] = {"items.rationale": {"how": "verified", "recorded_in": None}}
    with pytest.raises(SpecError, match="malformed derivations"):
        spec_from_description(entry)


# --- The contract version (docs/specs/contract.md) ------------------------------------------------


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


# --- Class schemas carried by the card (docs/specs/contract.md) -----------------------------------


def test_a_description_carries_each_class_schema_pinned_by_its_digest() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    assert set(entry["schemas"]) == {"Survey", "Findings"}
    for name, schema in entry["schemas"].items():
        assert schema["digest"] == schema_digest(schema["json_schema"]), name
    rebuilt = spec_from_description(entry)
    assert rebuilt.accepts == SPEC.accepts and rebuilt.payload == SPEC.payload
    assert rebuilt.payload is not None and rebuilt.payload.model is None  # schema only


def test_a_class_the_workbench_has_never_seen_is_accepted_by_its_schema() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    horoscope = entry["schemas"]["Survey"]["json_schema"]
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
    del entry["schemas"]["Survey"]
    with pytest.raises(SpecError, match="carries no schema"):
        spec_from_description(entry)
    entry = json.loads(json.dumps(describe(SPEC)))
    entry["schemas"]["Survey"]["json_schema"]["title"] = "Other"
    with pytest.raises(SpecError, match="does not match its digest"):
        spec_from_description(entry)


def test_a_class_schema_that_does_not_designate_its_class_is_refused() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    entry["accepts"] = ["Horoscope"]
    entry["schemas"]["Horoscope"] = entry["schemas"]["Survey"]  # says Survey
    with pytest.raises(SpecError, match="does not require schema_class = 'Horoscope'"):
        spec_from_description(entry)


def test_a_payload_class_that_does_not_mix_in_grounded_is_refused() -> None:
    entry = json.loads(json.dumps(describe(SPEC)))
    entry["payload"] = "Survey"
    entry["derivations"] = {}
    with pytest.raises(SpecError, match="does not mix in Grounded"):
        spec_from_description(entry)


def test_a_model_that_disagrees_with_its_generated_schema_is_refused() -> None:
    class Message(Frozen):  # the core class's name, its history missing
        schema_class: Literal["Message"] = "Message"
        message_text: str

    Message.__module__ = "dd_sdk.contract.models"  # so its schema is read from the SDK
    with pytest.raises(ClassSchemaError, match="only in the schema"):
        ClassSchema.of(Message)


def test_a_core_class_reads_its_generated_schema_from_the_sdk() -> None:
    message = ClassSchema.of(Message)
    assert message.name == "Message" and message.model is Message
    assert message.errors({"schema_class": "Message", "message_text": "hello"}) == []


def test_the_agent_sees_its_own_model_and_the_workbench_the_document() -> None:
    request = InvocationRequest(
        agent_id="test.spec", input=OpenInput(schema_class="Survey", title="t")
    )
    typed = typed_request(SPEC, request)
    assert isinstance(typed.input, Survey) and typed.input.title == "t"
    rebuilt = spec_from_description(describe(SPEC))
    assert typed_request(rebuilt, request) is request  # no model on the workbench's side


def test_serving_a_step_a_person_decides_is_refused() -> None:
    with pytest.raises(SpecError, match="a person decides"):
        dataclasses.replace(SPEC, serves=("governance.sensitive-data-handle",))
