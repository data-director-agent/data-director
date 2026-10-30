"""advisor.rights through the conductor: the Rights and Licensing Adviser mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_rights
from dd_agent_advisor_rights.agent import (
    MANDATED_NOTE,
    REUSE_QUESTION,
    SENSITIVE_QUESTION,
    THIRD_PARTY_QUESTION,
    RightsAdviser,
)
from dd_agent_advisor_rights.classes import RightsContext, RightsOptions
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_rights.__file__).parent / "schema" / "rights.yaml"


def sample() -> RightsContext:
    return RightsContext.model_validate(
        json.loads((SAMPLES / "rights-context.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_lists_fitting_licences_and_puts_restricted_access_first(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, RightsAdviser())
    env = conductor.invoke(request("advisor.rights", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(RightsOptions)
    assert [lic.spdx_id for lic in payload.licences] == ["CC-BY-4.0", "ODC-By-1.0"]
    assert [a.level for a in payload.access_levels] == [
        "restricted",
        "closed",
        "open",
        "embargoed",
    ]
    assert SENSITIVE_QUESTION in payload.questions
    assert THIRD_PARTY_QUESTION in payload.questions
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


def test_a_mandated_licence_is_the_only_option(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, RightsAdviser()).invoke(
        request("advisor.rights", RightsContext(mandated_licence="cc0-1.0")),
        acting_for=TEST_PRINCIPAL,
    )
    payload = env.payload_as(RightsOptions)
    assert [(lic.spdx_id, lic.note) for lic in payload.licences] == [("CC0-1.0", MANDATED_NOTE)]
    assert payload.access_levels[0].level == "open"


def test_unknown_reuse_offers_every_licence_and_asks(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, RightsAdviser()).invoke(
        request("advisor.rights", RightsContext(sensitive=False)), acting_for=TEST_PRINCIPAL
    )
    payload = env.payload_as(RightsOptions)
    assert len(payload.licences) == 5
    assert REUSE_QUESTION in payload.questions


@pytest.mark.requirement("DD-OUTCOME")
def test_nothing_to_go_on_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, RightsAdviser()).invoke(
        request("advisor.rights", RightsContext()), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(RightsAdviser.spec)
    assert entry["title"] == "Rights and Licensing Adviser"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["deposit.licence", "deposit.access"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
