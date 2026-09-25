"""hello.world through the conductor: the template agent, and the `none` mode success path.

`stub.abstain` is the workbench's other `none`-mode agent and it never succeeds, so this module
is where mode `none` is exercised with a grounded payload: R1 (no retrieval), R2 and R3 (cites
the input, and only the input), N1 (no chat span).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_hello
from dd_agent_hello.agent import HelloWorld
from dd_agent_hello.classes import Greeting, Salutation
from dd_sdk.agent import describe
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    GroundingMode,
    OutcomeStatus,
    ReasonCode,
    input_source_id,
)
from dd_sdk.evidence import INPUT_CANONICALISATION, input_hash
from dd_sdk.schema import gen
from workbench.testing import TEST_PRINCIPAL, make_conductor, request

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_hello.__file__).parent / "schema" / "hello.yaml"


def sample_salutation() -> Salutation:
    return Salutation.model_validate(
        json.loads((SAMPLES / "hello.salutation.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_greeting_is_grounded_on_the_input_and_passes_the_linter(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, HelloWorld())
    env = conductor.invoke(request("hello.world", sample_salutation()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(Greeting)
    assert payload.greeting_text == "Hello, world!"
    assert payload.greeting_derivation == Derivation.TEMPLATE

    ref = input_source_id(env.invocation_id)
    expected_hash = input_hash(conductor.store.get_request(env.invocation_id)["input"])  # type: ignore[index]
    assert [(g.source_id, g.content_hash) for g in payload.grounded_on] == [(ref, expected_hash)]
    assert [(e.source_id, e.canonicalisation) for e in env.evidence] == [
        (ref, INPUT_CANONICALISATION)
    ]
    assert conductor.grounding_reports[env.invocation_id].passed
    assert env.telemetry.model_id is None  # N1: mode `none` calls no model


@pytest.mark.requirement("DD-OUTCOME")
def test_unknown_language_abstains_rather_than_raising(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, HelloWorld()).invoke(
        request("hello.world", Salutation(greeted_name="world", language="qqq")),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED
    assert env.payload is None and env.evidence == []


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_an_input_class_it_did_not_declare_is_refused(runs_dir: Path) -> None:
    from workbench.testing import claim

    env = make_conductor(runs_dir, HelloWorld()).invoke(
        request("hello.world", claim()), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/input-not-accepted")
    assert env.payload is None


@pytest.mark.requirement("DD-REGISTRY")
def test_the_template_ships_everything_the_manifest_needs() -> None:
    entry = describe(HelloWorld.spec)
    assert entry["agent_id"] == "hello.world"
    assert entry["accepts"] == ["Salutation"]
    assert entry["grounding_mode"] == "none"
    assert entry["payload"] == "Greeting"
    # The viewer badges greeting_text from this, reading greeting_derivation per value.
    assert entry["derivations"] == {
        "greeting_text": {"how": "template", "recorded_in": "greeting_derivation"}
    }
    json.dumps(entry)


def test_spec_declares_what_the_conductor_enforces() -> None:
    spec = HelloWorld.spec
    assert spec.accepts == (ClassSchema.of(Salutation),)
    assert spec.payload == ClassSchema.of(Greeting)
    assert spec.grounding_mode == GroundingMode.NONE
    # A template exercises the harness, not the Blueprint: every id it claims is a DD-* one.
    assert all(r.startswith("DD-") for r in spec.requirement_ids), spec.requirement_ids


def test_its_own_classes_are_generated_from_its_linkml_and_carried_by_its_card() -> None:
    # Recipe step 1: the agent owns its classes (ADR-0019). The generated schemas are current...
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
    # ...and the card carries them, so the workbench needs no copy of its own.
    entry = describe(HelloWorld.spec)
    assert set(entry["schemas"]) == {"Salutation", "Greeting"}
    assert entry["schemas"]["Greeting"]["digest"] == ClassSchema.of(Greeting).digest
