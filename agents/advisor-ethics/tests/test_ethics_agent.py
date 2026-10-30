"""advisor.ethics through the conductor: the Research Ethics Adviser mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_ethics
from dd_agent_advisor_ethics.agent import UNKNOWN_EMBARGO_QUESTION, EthicsAdviser
from dd_agent_advisor_ethics.classes import SensitivityContext, SensitivityFlags
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_ethics.__file__).parent / "schema" / "ethics.yaml"


def sample() -> SensitivityContext:
    return SensitivityContext.model_validate(
        json.loads((SAMPLES / "ethics-context.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_flags_field_names_and_asks_about_consent(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, EthicsAdviser())
    env = conductor.invoke(request("advisor.ethics", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(SensitivityFlags)
    assert [(f.field, f.category) for f in payload.flags] == [
        ("postcode", "direct identifier"),
        ("date_of_birth", "indirect identifier"),
        ("health_conditions", "special category"),
    ]
    assert any("consent" in q for q in payload.questions)
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-OUTCOME")
def test_nothing_to_go_on_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, EthicsAdviser()).invoke(
        request("advisor.ethics", SensitivityContext(title="Untitled")), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_with_nothing_flagged_it_still_asks_about_an_unknown_embargo(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, EthicsAdviser()).invoke(
        request("advisor.ethics", SensitivityContext(fields=["kwh_daily"])),
        acting_for=TEST_PRINCIPAL,
    )
    payload = env.payload_as(SensitivityFlags)
    assert payload.flags == []
    assert payload.questions == [UNKNOWN_EMBARGO_QUESTION]


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(EthicsAdviser.spec)
    assert entry["title"] == "Research Ethics Adviser"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["governance.sensitive-data-identify", "governance.embargo"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
