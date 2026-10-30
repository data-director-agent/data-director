"""advisor.documentation through the conductor: the Documentation Editor mock (ADR-0033)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dd_agent_advisor_documentation
from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.classes import (
    DocumentationDraft,
    DocumentationRequest,
    DraftStatus,
)
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"
SCHEMA = Path(dd_agent_advisor_documentation.__file__).parent / "schema" / "documentation.yaml"


def sample() -> DocumentationRequest:
    return DocumentationRequest.model_validate(
        json.loads((SAMPLES / "documentation-request.json").read_text(encoding="utf-8"))
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_drafts_what_it_was_given_and_leaves_the_rest(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, DocumentationEditor())
    env = conductor.invoke(request("advisor.documentation", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE
    payload = env.payload_as(DocumentationDraft)
    assert [(s.heading, s.draft_status) for s in payload.readme_sections] == [
        ("Title", DraftStatus.DRAFTED),
        ("Description", DraftStatus.DRAFTED),
        ("Creators", DraftStatus.DRAFTED),
        ("Files", DraftStatus.DRAFTED),
        ("Methods", DraftStatus.NEEDS_RESEARCHER),
        ("Variables", DraftStatus.DRAFTED),
        ("Licence", DraftStatus.NEEDS_RESEARCHER),
        ("How to cite", DraftStatus.NEEDS_RESEARCHER),
    ]
    files = payload.readme_sections[3].text
    assert files == "- survey_responses.csv\n- meter_readings.csv\n- interview_guide.pdf"
    assert payload.readme_sections[4].text is None
    assert [e.field for e in payload.dictionary] == sample().fields
    assert all(
        e.definition is None
        and e.unit is None
        and e.missing_values is None
        and e.draft_status == DraftStatus.NEEDS_RESEARCHER
        for e in payload.dictionary
    )
    assert payload.limitations
    assert conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-OUTCOME")
def test_no_files_or_fields_abstains(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, DocumentationEditor()).invoke(
        request("advisor.documentation", DocumentationRequest(title="Untitled")),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_a_section_with_empty_input_is_left_for_the_researcher(runs_dir: Path) -> None:
    env = make_conductor(runs_dir, DocumentationEditor()).invoke(
        request("advisor.documentation", DocumentationRequest(title="Readings", files=["a.csv"])),
        acting_for=TEST_PRINCIPAL,
    )
    payload = env.payload_as(DocumentationDraft)
    sections = {s.heading: s for s in payload.readme_sections}
    assert sections["Description"].draft_status == DraftStatus.NEEDS_RESEARCHER
    assert sections["Variables"].draft_status == DraftStatus.NEEDS_RESEARCHER
    assert payload.dictionary == []


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(DocumentationEditor.spec)
    assert entry["title"] == "Documentation Editor"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["setup.documentation", "preparation.documentation"]
    json.dumps(entry)


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
