"""advisor.metadata drafts in any registered standard, from its definition alone
(docs/specs/metadata-standards.md; #1359): a made-up standard with other property names and a
second serialisation is drafted in with no change to the agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_advisor_metadata.evals.drafting import load_cases
from dd_harness import orcid
from dd_harness.testing import SAMPLE_ID, TEST_PRINCIPAL, make_conductor, request, sample_record
from dd_metadata_records import JSON, Definition, Standards, Tree, load
from dd_metadata_records.standards import DATACITE_4
from dd_sdk.contract.models import (
    Document,
    DraftAnswer,
    DraftRequest,
    Envelope,
    OutcomeStatus,
    ReasonCode,
    RequirementField,
    ResearcherRecord,
)

TOY = load(Path(__file__).with_name("data") / "toy-standard.yaml")
TOY_URI = "https://example.org/toy"


@dataclass(frozen=True)
class ToyCodec:
    """A second serialisation for the toy standard: compact, key-sorted JSON."""

    codec_id: str = "toy-test"
    media_type: str = "application/x-toy"

    def parse(self, text: str) -> Tree:
        tree: Tree = json.loads(text)
        return tree

    def emit(self, tree: Tree) -> str:
        return json.dumps(tree, sort_keys=True, separators=(",", ":"))


def standards(toy: Definition = TOY) -> Standards:
    return Standards([DATACITE_4, toy], [JSON, ToyCodec()])


def asked_for(fields: list[tuple[str, str]], **update: Any) -> DraftRequest:
    base = DraftRequest.model_validate(load_cases()[0]["input"])
    assert base.requirements is not None
    requirements = base.requirements.model_copy(
        update={
            "conforms_to": TOY_URI,
            "licences": [],
            "fields": [
                RequirementField(property=prop, term=term, obligation="required")
                for prop, term in fields
            ],
        }
    )
    return base.model_copy(update={"requirements": requirements, **update})


FIELDS = [("title", "schema:name"), ("creator", "schema:creator")]


def draft(runs_dir: Path, asked: DraftRequest, toy: Definition = TOY) -> Envelope:
    librarian = MetadataLibrarian(standards=standards(toy))
    conductor = make_conductor(runs_dir, librarian)
    return conductor.invoke(request("advisor.metadata", asked), acting_for=TEST_PRINCIPAL)


def test_a_record_is_drafted_in_a_second_standard_with_a_question_for_each_gap(
    runs_dir: Path,
) -> None:
    env = draft(runs_dir, asked_for(FIELDS))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    document = env.payload_as(Document)
    assert (document.conforms_to, document.media_type) == (TOY_URI, "application/json")
    record = json.loads(document.document_text)
    assert record == {"title": None, "creator": [{"name": None}]}
    asked = {q.gap_property: q.question_prompt for q in document.document_questions}
    assert asked == {
        "title": "What is the dataset called?",
        "creator[0].name": "Who made the dataset?",
    }
    # The statement names the standard by its definition.
    assert "Toy record" in env.outcome.statement


def test_an_answer_is_placed_as_given_in_the_second_standard(runs_dir: Path) -> None:
    first = draft(runs_dir, asked_for(FIELDS)).payload_as(Document)
    title = next(q for q in first.document_questions if q.gap_property == "title")
    answer = DraftAnswer(answered_question=title.question_id, answer_text="Hope Valley soil cores")
    env = draft(runs_dir, asked_for(FIELDS, draft_answers=[answer]))
    record = json.loads(env.payload_as(Document).document_text)
    assert record["title"] == "Hope Valley soil cores"
    assert title.question_id not in {
        q.question_id for q in env.payload_as(Document).document_questions
    }


def test_a_researcher_is_written_in_the_second_standards_own_keys(runs_dir: Path) -> None:
    kept = orcid.normalise(
        sample_record(),
        principal_id=f"https://sandbox.orcid.org/{SAMPLE_ID}",
        retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
        source="https://pub.sandbox.orcid.org/v3.0/record",
    )
    researchers = [ResearcherRecord.model_validate(kept)]
    env = draft(runs_dir, asked_for(FIELDS, researchers=researchers))
    (creator,) = json.loads(env.payload_as(Document).document_text)["creator"]
    # Only what the toy standard has a key for: its name and its ORCID iD.
    assert creator == {"name": researchers[0].researcher_name, "orcid": researchers[0].orcid_id}


def test_a_question_has_the_same_identifier_in_either_serialisation(runs_dir: Path) -> None:
    """Invariant 5: a question is named by the property's logical path, whatever serialisation
    the record is written in; a gap is written as the serialisation writes one (invariant 6)."""
    json_first = draft(runs_dir, asked_for(FIELDS)).payload_as(Document)
    toy_first = replace(TOY, serialisations=tuple(reversed(TOY.serialisations)))
    text_first = draft(runs_dir, asked_for(FIELDS), toy_first).payload_as(Document)
    assert text_first.media_type == "application/x-toy"
    assert [q.question_id for q in json_first.document_questions] == [
        q.question_id for q in text_first.document_questions
    ]
    assert json.loads(text_first.document_text)["title"] == ":unav"
    # Read back, the gap is no value.
    read = standards(toy_first).by_uri(TOY_URI)
    assert read is not None
    assert read.read(text_first.document_text, "application/x-toy").values("title") == []


def test_a_standard_no_definition_covers_is_not_drafted(runs_dir: Path) -> None:
    asked = asked_for(FIELDS)
    assert asked.requirements is not None
    other = asked.requirements.model_copy(update={"conforms_to": "https://example.org/other"})
    env = draft(runs_dir, asked.model_copy(update={"requirements": other}))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED
