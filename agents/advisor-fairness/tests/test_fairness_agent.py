"""advisor.fairness through the conductor: the FAIR Assessor mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_fairness
from dd_agent_advisor_fairness.agent import FairAssessor
from dd_agent_advisor_fairness.classes import FairnessReport, PublishedRecord
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_fairness.__file__).parent / "schema" / "fairness.yaml"


def sample() -> PublishedRecord:
    return PublishedRecord.model_validate(
        json.loads((SAMPLES / "published-record.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_checks_the_record_and_suggests_retrofits(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, FairAssessor())
    env = conductor.invoke(request("advisor.fairness", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(FairnessReport)
    unmet = [(c.principle, c.check) for c in payload.checks if not c.met]
    assert unmet == [
        ("F1", "identifier-is-doi"),
        ("I3", "related-identifiers-present"),
        ("R1.2", "creators-identified"),
    ]
    assert all(c.recommendation for c in payload.checks if not c.met)
    assert all(c.recommendation is None for c in payload.checks if c.met)
    assert any("not a FAIRness evaluation" in item for item in payload.limitations)
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-OUTCOME")
def test_neither_identifier_nor_title_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, FairAssessor()).invoke(
        request("advisor.fairness", PublishedRecord(keywords=["energy"])),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(FairAssessor.spec)
    assert entry["title"] == "FAIR Assessor"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["post.fairness", "post.retrofit"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
