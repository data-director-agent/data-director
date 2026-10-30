"""advisor.dmp through the conductor: the Data Management Plan Checker mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_dmp
from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.classes import DmpCommitments, DmpDiscrepancies, SharingCommitment
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_dmp.__file__).parent / "schema" / "dmp.yaml"


def sample() -> DmpCommitments:
    return DmpCommitments.model_validate(
        json.loads((SAMPLES / "dmp-commitments.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_flags_missing_unplanned_and_changed_sharing(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, DmpChecker())
    env = conductor.invoke(request("advisor.dmp", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(DmpDiscrepancies)
    assert [(d.output, d.aspect, d.committed, d.planned) for d in payload.discrepancies] == [
        ("Smart-meter readings", "access", "open", "restricted"),
        ("Interview transcripts", "missing", None, None),
        ("Analysis code", "unplanned", None, None),
    ]
    assert all("review" in d.message for d in payload.discrepancies)
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-OUTCOME")
def test_no_commitments_abstains(runs_dir: Path) -> None:
    commitments = DmpCommitments(planned_outputs=[SharingCommitment(output="Analysis code")])
    env = make_conductor(runs_dir, DmpChecker()).invoke(
        request("advisor.dmp", commitments), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_an_aspect_given_on_one_side_only_is_not_a_difference(runs_dir: Path) -> None:
    commitments = DmpCommitments(
        committed_outputs=[SharingCommitment(output="Readings", licence="CC BY 4.0")],
        planned_outputs=[SharingCommitment(output="READINGS", repository="ORDA")],
    )
    env = make_conductor(runs_dir, DmpChecker()).invoke(
        request("advisor.dmp", commitments), acting_for=TEST_PRINCIPAL
    )
    assert env.payload_as(DmpDiscrepancies).discrepancies == []


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(DmpChecker.spec)
    assert entry["title"] == "Data Management Plan Checker"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["governance.dmp"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
