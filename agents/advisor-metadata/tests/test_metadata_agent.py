"""advisor.metadata through the conductor: the Metadata Librarian mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_metadata
from dd_agent_advisor_metadata.agent import FILLED, NEEDS_RESEARCHER, MetadataLibrarian
from dd_agent_advisor_metadata.classes import MetadataDraft, MetadataDraftRequest
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_metadata.__file__).parent / "schema" / "metadata.yaml"


def sample() -> MetadataDraftRequest:
    return MetadataDraftRequest.model_validate(
        json.loads((SAMPLES / "metadata-draft-request.json").read_text(encoding="utf-8"))
    )


def draft(runs_dir: Path, request_input: MetadataDraftRequest) -> MetadataDraft:
    env = make_conductor(runs_dir, MetadataLibrarian()).invoke(
        request("advisor.metadata", request_input), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(MetadataDraft)


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_drafts_datacite_and_leaves_the_rest_to_the_researcher(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, MetadataLibrarian())
    env = conductor.invoke(request("advisor.metadata", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(MetadataDraft)
    assert payload.standard == "DataCite"
    assert payload.standard_reason.startswith("Requested")
    assert [(f.name, f.value, f.status) for f in payload.fields] == [
        ("Identifier", None, NEEDS_RESEARCHER),
        ("Creator", "Smith, Alex; University of Sheffield", FILLED),
        ("Title", "Household energy use in Sheffield, 2025", FILLED),
        ("Publisher", None, NEEDS_RESEARCHER),
        ("PublicationYear", "2026", FILLED),
        ("ResourceType", None, NEEDS_RESEARCHER),
        ("Subject", "energy use; smart meters; households", FILLED),
        (
            "Description",
            "Daily smart-meter readings and survey responses from 40 households in Sheffield.",
            FILLED,
        ),
    ]
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-OUTCOME")
def test_no_title_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, MetadataLibrarian()).invoke(
        request("advisor.metadata", MetadataDraftRequest(creators=["Smith, Alex"])),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_a_named_standard_is_used_and_nothing_is_invented(runs_dir: Path) -> None:
    payload = draft(
        runs_dir, MetadataDraftRequest(title="Soil cores", target_standard="dublin-core")
    )
    assert payload.standard == "Dublin Core"
    filled = [f.name for f in payload.fields if f.status == FILLED]
    assert filled == ["title"]
    assert all(f.value is None for f in payload.fields if f.status == NEEDS_RESEARCHER)


def test_an_unknown_standard_falls_back_to_datacite_and_says_so(runs_dir: Path) -> None:
    payload = draft(runs_dir, MetadataDraftRequest(title="Soil cores", target_standard="EML"))
    assert payload.standard == "DataCite"
    assert "'EML'" in payload.standard_reason


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(MetadataLibrarian.spec)
    assert entry["title"] == "Metadata Librarian"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["preparation.metadata-standard", "preparation.metadata"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
