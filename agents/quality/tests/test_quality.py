"""quality.reviewer through the conductor: an input_only agent that is not R3-shaped."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_agent_quality.agent import QualityReviewer
from dd_sdk.contract.models import (
    GroundingMode,
    MetadataRecord,
    OutcomeStatus,
    QualityReview,
    ReasonCode,
    Severity,
    input_source_id,
)
from dd_sdk.evidence import INPUT_CANONICALISATION, input_hash
from workbench.testing import PERMISSIVE, make_conductor, request

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"


def sample_record() -> MetadataRecord:
    return MetadataRecord.model_validate(
        json.loads((SAMPLES / "orda-record.metadata.json").read_text())
    )


@pytest.mark.requirement("R4.1", "DD-GROUNDING-MODE", "C14.1")
def test_review_is_grounded_on_the_input_and_passes_the_linter(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, QualityReviewer())
    env = conductor.invoke(request("quality.reviewer", sample_record()))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.INPUT_ONLY
    assert isinstance(env.payload, QualityReview)
    ref = input_source_id(env.invocation_id)
    expected_hash = input_hash(conductor.store.get_request(env.invocation_id)["input"])  # type: ignore[index]
    assert [(g.source_id, g.content_hash) for g in env.payload.grounded_on] == [
        (ref, expected_hash)
    ]
    assert all(f.grounded_on == env.payload.grounded_on for f in env.payload.findings)
    assert [(e.source_id, e.canonicalisation) for e in env.evidence] == [
        (ref, INPUT_CANONICALISATION)
    ]
    assert conductor.grounding_reports[env.invocation_id].passed
    # The sample lacks a licence; that is the one unmet criterion, and it is an error.
    unmet = [f for f in env.payload.findings if f.severity != Severity.INFO]
    assert [(f.criterion, f.severity) for f in unmet] == [("licence_present", Severity.ERROR)]
    assert env.payload.score is not None and 0 < env.payload.score < 1
    assert all(f.message for f in env.payload.findings)  # C14: every finding is explained
    assert env.telemetry.model_id is None  # no model was called


@pytest.mark.requirement("R4.1")
def test_complete_record_scores_one_and_every_finding_is_informational(runs_dir: Path) -> None:
    record = sample_record().model_copy(update={"licence": "CC-BY-4.0"})
    env = make_conductor(runs_dir, QualityReviewer()).invoke(request("quality.reviewer", record))
    assert isinstance(env.payload, QualityReview)
    assert env.payload.score == 1.0
    assert {f.severity for f in env.payload.findings} == {Severity.INFO}


@pytest.mark.requirement("DD-OUTCOME")
def test_empty_record_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, QualityReviewer()).invoke(
        request("quality.reviewer", MetadataRecord(), bundle=PERMISSIVE)
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT
    assert env.payload is None and env.evidence == []


def test_spec_declares_what_the_conductor_enforces() -> None:
    spec = QualityReviewer.spec
    assert spec.accepts == (MetadataRecord,)
    assert spec.payload_type is QualityReview
    assert spec.grounding_mode == GroundingMode.INPUT_ONLY
    assert spec.derivations["findings.message"].recorded_in == "derivation"
