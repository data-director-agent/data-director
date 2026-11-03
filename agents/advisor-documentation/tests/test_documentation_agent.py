"""advisor.documentation through the conductor: the Documentation Editor mock (ADR-0033) as the
stub drafter of the README and the data dictionary (#200)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from dd_agent_advisor_documentation.agent import DICTIONARY_COLUMNS, DocumentationEditor
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import (
    CurrentVersion,
    Document,
    DocumentKind,
    DocumentVersionRef,
    DraftRequest,
    Envelope,
    GroundingMode,
    OutcomeStatus,
    ReasonCode,
    VersionState,
    new_invocation_id,
)

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"


def sample(name: str) -> DraftRequest:
    return DraftRequest.model_validate_json((SAMPLES / name).read_text(encoding="utf-8"))


def draft(runs_dir: Path, asked: DraftRequest) -> tuple[Envelope, bool]:
    conductor = make_conductor(runs_dir, DocumentationEditor())
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    return env, conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_drafts_a_readme_from_the_inventory_and_marks_the_rest(runs_dir: Path) -> None:
    asked = sample("soil-survey.readme.draft.json")
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE and grounded
    document = env.payload_as(Document)
    assert document.document_kind == DocumentKind.README
    assert document.media_type == "text/markdown"
    assert document.revises is None
    text = document.document_text
    headings = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "General information",
        "Description",
        "Files",
        "Methods",
        "Variables",
        "Access and licence",
        "How to cite",
        "Software requirements",
    ]
    assert text.count("_To be written by the researcher:") == len(headings)
    assert asked.inventory is not None
    for f in asked.inventory.inventory_files:
        assert f"`{f.file_path}`" in text
        for field in f.file_fields:
            assert f"`{field.name}`" in text
    assert asked.requirements is not None and asked.requirements.licences
    assert f"`{asked.requirements.licences[0]}`" in text
    assert env.outcome.statement.startswith("Mock:")


def test_drafts_a_data_dictionary_with_a_row_per_field(runs_dir: Path) -> None:
    asked = sample("soil-survey.data-dictionary.draft.json")
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    document = env.payload_as(Document)
    assert (document.document_kind, document.media_type) == (
        DocumentKind.DATA_DICTIONARY,
        "text/csv",
    )
    rows = list(csv.DictReader(io.StringIO(document.document_text)))
    assert asked.inventory is not None
    expected = [
        (f.file_path, c.name) for f in asked.inventory.inventory_files for c in f.file_fields
    ]
    assert [(r["file"], r["field"]) for r in rows] == expected
    assert tuple(rows[0]) == DICTIONARY_COLUMNS
    assert all(r["unit"] == "" and r["missing_values"] == "" for r in rows)


def test_regenerating_names_the_version_it_replaces(runs_dir: Path) -> None:
    previous = DocumentVersionRef(document_id=new_invocation_id(), version=2)
    asked = sample("soil-survey.readme.draft.json").model_copy(
        update={
            "current_version": CurrentVersion(
                version_ref=previous,
                document_title="README for the soil survey",
                media_type="text/markdown",
                document_text="# README\n",
                version_state=VersionState.REJECTED,
                decision_reason="The files table is missing.",
            )
        }
    )
    env, _ = draft(runs_dir, asked)
    document = env.payload_as(Document)
    assert document.revises == previous
    assert document.document_title == "README for the soil survey"
    assert "replaces version 2" in env.outcome.statement


@pytest.mark.requirement("DD-OUTCOME")
@pytest.mark.parametrize(
    ("asked", "reason"),
    [
        (DraftRequest(document_kind=DocumentKind.README), ReasonCode.INSUFFICIENT_INPUT),
        (
            DraftRequest(document_kind=DocumentKind.METADATA_RECORD),
            ReasonCode.OUTSIDE_AGENT_SCOPE,
        ),
    ],
)
def test_abstains_without_an_inventory_or_for_another_kind(
    runs_dir: Path, asked: DraftRequest, reason: ReasonCode
) -> None:
    env, _ = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == reason


def test_no_table_no_data_dictionary(runs_dir: Path) -> None:
    asked = sample("soil-survey.data-dictionary.draft.json")
    assert asked.inventory is not None
    files = [f.model_copy(update={"file_fields": []}) for f in asked.inventory.inventory_files]
    inventory = asked.inventory.model_copy(update={"inventory_files": files})
    env, _ = draft(runs_dir, asked.model_copy(update={"inventory": inventory}))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(DocumentationEditor.spec)
    assert entry["title"] == "Documentation Editor"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["setup.documentation", "preparation.documentation"]
    json.dumps(entry)
