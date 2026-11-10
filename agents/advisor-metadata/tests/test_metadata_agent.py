"""advisor.metadata through the conductor: the Metadata Librarian mock
(docs/specs/agents.md) as the stub drafter of the metadata record (#200)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_metadata.agent import DATACITE, MetadataLibrarian
from dd_harness import orcid
from dd_harness.testing import SAMPLE_ID, TEST_PRINCIPAL, make_conductor, request, sample_record
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
    ResearcherRecord,
    VersionState,
    new_invocation_id,
)

SAMPLES = Path(__file__).resolve().parents[3] / "workbench" / "samples"


def sample() -> DraftRequest:
    path = SAMPLES / "soil-survey.metadata-record.draft.json"
    return DraftRequest.model_validate_json(path.read_text(encoding="utf-8"))


def draft(runs_dir: Path, asked: DraftRequest) -> tuple[Envelope, bool]:
    conductor = make_conductor(runs_dir, MetadataLibrarian())
    env = conductor.invoke(request("advisor.metadata", asked), acting_for=TEST_PRINCIPAL)
    return env, conductor.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_drafts_a_datacite_record_with_every_property_the_repository_asks_for(
    runs_dir: Path,
) -> None:
    asked = sample()
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.NONE and grounded
    document = env.payload_as(Document)
    assert document.document_kind == DocumentKind.METADATA_RECORD
    assert (document.media_type, document.conforms_to) == ("application/json", DATACITE)
    record: dict[str, Any] = json.loads(document.document_text)

    assert asked.requirements is not None
    for field in asked.requirements.fields:
        assert field.property.split(".")[0] in record, field.property
    # The mock fills only what holds for any deposit and what the inventory states.
    assert record["types"] == {"resourceTypeGeneral": "Dataset"}
    assert record["titles"] == [{"title": None}]
    assert {"subject": None, "subjectScheme": "ANZSRC Fields of Research"} in record["subjects"]
    assert {"subject": None} in record["subjects"]
    assert record["descriptions"] == [{"description": None, "descriptionType": "Abstract"}]
    assert asked.inventory is not None
    files = asked.inventory.inventory_files
    assert record["sizes"] == [f"{len(files)} files", f"{sum(f.file_size for f in files)} bytes"]
    assert record["formats"] == sorted({f.file_media_type for f in files if f.file_media_type})
    assert record["schemaVersion"] == DATACITE
    assert "ORDA" in (document.document_title or "")


def test_regenerating_names_the_version_it_replaces(runs_dir: Path) -> None:
    previous = DocumentVersionRef(document_id=new_invocation_id(), version=1)
    asked = sample().model_copy(
        update={
            "current_version": CurrentVersion(
                version_ref=previous,
                media_type="application/json",
                document_text="{}",
                version_state=VersionState.PROPOSED,
            )
        }
    )
    env, _ = draft(runs_dir, asked)
    assert env.payload_as(Document).revises == previous


def test_fills_creators_subjects_and_funding_from_what_researchers_kept(runs_dir: Path) -> None:
    """What a researcher kept from their public ORCID record is placed where the repository asks
    for it (docs/specs/projects.md); a researcher who kept no name is a creator to name."""
    kept = orcid.normalise(
        sample_record(),
        principal_id=f"https://sandbox.orcid.org/{SAMPLE_ID}",
        retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
        source="https://pub.sandbox.orcid.org/v3.0/record",
    )
    nameless = {
        "orcid_id": "https://orcid.org/0000-0002-1694-233X",
        "record_retrieved_at": "2026-11-10T00:00:00Z",
        "record_source": "https://pub.orcid.org/v3.0/record",
    }
    researchers = [ResearcherRecord.model_validate(r) for r in (kept, nameless)]
    env, grounded = draft(runs_dir, sample().model_copy(update={"researchers": researchers}))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    record = json.loads(env.payload_as(Document).document_text)

    first, second = record["creators"]
    assert first["name"] == "Josiah Carberry"
    assert first["nameIdentifiers"][0]["nameIdentifier"] == kept["orcid_id"]
    [employer] = first["affiliation"]  # the current employer, not the degree
    assert employer["affiliationIdentifier"] == "https://ror.org/05gq02987"
    assert (
        second["name"] is None and second["nameIdentifiers"][0]["nameIdentifierScheme"] == "ORCID"
    )
    assert {"subject": "psychoceramics"} in record["subjects"]
    assert {"subject": None, "subjectScheme": "ANZSRC Fields of Research"} in record["subjects"]
    [funding] = record["fundingReferences"]
    assert funding["funderIdentifierType"] == "Crossref Funder ID"
    assert funding["awardNumber"] == "NSF-1234567"


@pytest.mark.requirement("DD-OUTCOME")
def test_abstains_without_a_repository_or_for_another_kind_or_standard(runs_dir: Path) -> None:
    asked = sample()
    assert asked.requirements is not None
    other = asked.requirements.model_copy(update={"conforms_to": "http://example.org/ddi"})
    cases = [
        (asked.model_copy(update={"requirements": None}), ReasonCode.INSUFFICIENT_INPUT),
        (
            asked.model_copy(update={"document_kind": DocumentKind.README}),
            ReasonCode.OUTSIDE_AGENT_SCOPE,
        ),
        (asked.model_copy(update={"requirements": other}), ReasonCode.CAPABILITY_NOT_IMPLEMENTED),
    ]
    for case, reason in cases:
        env, _ = draft(runs_dir, case)
        assert env.outcome.status == OutcomeStatus.ABSTAINED
        assert env.outcome.reason_code == reason


def test_the_card_names_the_persona_and_its_steps() -> None:
    entry = describe(MetadataLibrarian.spec)
    assert entry["title"] == "Metadata Librarian"
    assert entry["description"].startswith("Mock.")
    assert entry["serves"] == ["preparation.metadata-standard", "preparation.metadata"]
    json.dumps(entry)
