"""advisor.metadata drafts a record in Dublin Core, as OAI-DC XML, from its registered definition
alone (docs/specs/metadata-standards.md; #1360)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_advisor_metadata.evals.drafting import load_cases
from dd_harness import orcid
from dd_harness.testing import SAMPLE_ID, TEST_PRINCIPAL, make_conductor, request, sample_record
from dd_metadata_records import discover
from dd_sdk.contract.models import (
    Document,
    DraftAnswer,
    DraftRequest,
    Envelope,
    OutcomeStatus,
    RequirementField,
    ResearcherRecord,
)

OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC = "{http://purl.org/dc/elements/1.1/}"
FIELDS = [
    ("title", "schema:name", "required"),
    ("creator", "schema:creator", "required"),
    ("subject", "schema:keywords", "recommended"),
    ("type", "schema:additionalType", "recommended"),
    ("rights", "schema:license", "recommended"),
]


def asked_for(**update: Any) -> DraftRequest:
    base = DraftRequest.model_validate(load_cases()[0]["input"])
    assert base.requirements is not None
    requirements = base.requirements.model_copy(
        update={
            "conforms_to": OAI_DC,
            "fields": [
                RequirementField(property=prop, term=term, obligation=obligation)
                for prop, term, obligation in FIELDS
            ],
        }
    )
    return base.model_copy(update={"requirements": requirements, **update})


def draft(runs_dir: Path, asked: DraftRequest) -> Envelope:
    conductor = make_conductor(runs_dir, MetadataLibrarian())
    return conductor.invoke(request("advisor.metadata", asked), acting_for=TEST_PRINCIPAL)


def elements(document: Document) -> dict[str, list[str | None]]:
    root = ElementTree.fromstring(document.document_text)
    found: dict[str, list[str | None]] = {}
    for child in root:
        found.setdefault(child.tag.removeprefix(DC), []).append(child.text)
    return found


def test_a_record_is_drafted_in_oai_dc_with_a_question_for_each_gap(runs_dir: Path) -> None:
    env = draft(runs_dir, asked_for())
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    document = env.payload_as(Document)
    assert (document.conforms_to, document.media_type) == (OAI_DC, "application/xml")
    written = elements(document)
    assert written["title"] == [":unav"] and written["creator"] == [":unav"]
    assert written["type"] == ["Dataset"]
    assert {q.gap_property for q in document.document_questions} >= {"title", "creator", "rights"}
    # The record reads back through Dublin Core's definition, its gaps as no value.
    standard = discover().by_uri(OAI_DC)
    assert standard is not None
    read = standard.read(document.document_text, "application/xml")
    assert read.values("title") == [] and read.values("type") == ["Dataset"]


def test_an_answer_and_a_researcher_are_placed_in_dublin_cores_elements(runs_dir: Path) -> None:
    first = draft(runs_dir, asked_for()).payload_as(Document)
    title = next(q for q in first.document_questions if q.gap_property == "title")
    kept = orcid.normalise(
        sample_record(),
        principal_id=f"https://sandbox.orcid.org/{SAMPLE_ID}",
        retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
        source="https://pub.sandbox.orcid.org/v3.0/record",
    )
    researcher = ResearcherRecord.model_validate(kept)
    answer = DraftAnswer(answered_question=title.question_id, answer_text="Hope Valley soil cores")
    env = draft(runs_dir, asked_for(draft_answers=[answer], researchers=[researcher]))
    written = elements(env.payload_as(Document))
    assert written["title"] == ["Hope Valley soil cores"]
    # A Dublin Core creator is a name alone: the ORCID iD and employers have no element.
    assert written["creator"] == [researcher.researcher_name]
