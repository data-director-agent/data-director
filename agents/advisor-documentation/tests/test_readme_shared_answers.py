"""Answers the researcher gave for the metadata record, and facts people decided, offered as
suggestions in the README (#1284, docs/specs/drafting.md, invariant 7): beside each question on
the same value, derived as `answer`, never written into the README."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from test_prose import sample, template_draft

from dd_agent_advisor_documentation.sections import load_sections
from dd_sdk.contract.facts import (
    Affiliation,
    AffiliationKind,
    FactKind,
    ProjectFact,
    ResearcherRecord,
)
from dd_sdk.contract.models import (
    Derivation,
    DocumentKind,
    DocumentQuestion,
)
from dd_sdk.contract.questions import SUGGESTED_FROM_RESEARCHERS, SharedAnswer, SharedField

TITLE = "Soil cores from Hallam Moor"
PLACE = "Hallam Moor, South Yorkshire"
GIVEN = [
    SharedAnswer(
        shared_field=SharedField.TITLE,
        answer_text=TITLE,
        answered_question="q-" + "1" * 16,
        answered_in=DocumentKind.METADATA_RECORD,
    ),
    SharedAnswer(
        shared_field=SharedField.PLACE,
        answer_text=PLACE,
        answered_question="q-" + "2" * 16,
        answered_in=DocumentKind.METADATA_RECORD,
    ),
]
LICENCE = ProjectFact(fact_kind=FactKind.LICENCE, fact_subject="dataset", licence_id="CC-BY-4.0")


def by_target(questions: list[DocumentQuestion]) -> dict[str, DocumentQuestion]:
    return {q.gap_part or q.gap_section or "": q for q in questions}


def test_the_readme_template_names_the_shared_fields() -> None:
    shares = {
        part.label: part.shares
        for section in load_sections()
        for part in section.parts
        if part.shares is not None
    } | {s.heading: s.shares for s in load_sections() if s.shares is not None}
    assert shares["Title"] == SharedField.TITLE
    assert shares["Funding"] == SharedField.FUNDER
    assert shares["Access and licence"] == SharedField.LICENCE


def test_a_metadata_answer_is_offered_in_the_readme_and_not_written(runs_dir: Path) -> None:
    asked = sample("soil-survey.readme.draft.json").model_copy(
        update={"shared_answers": GIVEN, "project_decisions": [LICENCE]}
    )
    document = template_draft(runs_dir, asked)
    questions = by_target(document.document_questions)
    for target, text, source in (
        ("Title", TITLE, "metadata_record"),
        ("Geographic location", PLACE, "metadata_record"),
        ("Access and licence", "CC-BY-4.0", "decision"),
    ):
        question = questions[target]
        assert question.suggested_answer == text
        assert question.suggestion_derivation == Derivation.ANSWER
        assert question.suggested_from == source
    # Nothing is written until the researcher saves it as their answer.
    assert TITLE not in document.document_text and PLACE not in document.document_text
    assert questions["Creators"].suggested_answer is None


def kept(orcid: str, name: str | None, employer: str | None = None) -> ResearcherRecord:
    affiliations = (
        [
            Affiliation(
                put_code="1",
                affiliation_kind=AffiliationKind.EMPLOYMENT,
                organisation_name=employer,
            )
        ]
        if employer
        else []
    )
    return ResearcherRecord(
        orcid_id=orcid,
        researcher_name=name,
        affiliations=affiliations,
        record_retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        record_source="orcid",
    )


def test_the_projects_people_are_offered_as_the_creators(runs_dir: Path) -> None:
    people = [
        kept("https://orcid.org/0000-0002-1825-0097", "Ada Moor", "University of Sheffield"),
        kept("https://orcid.org/0000-0001-5109-3700", None),
        kept("https://orcid.org/0000-0003-1415-9269", "Ben Hallam"),
    ]
    asked = sample("soil-survey.readme.draft.json").model_copy(update={"researchers": people})
    document = template_draft(runs_dir, asked)
    question = by_target(document.document_questions)["Creators"]
    lines = (question.suggested_answer or "").splitlines()
    # A person without a name is left out; the rest keep the order they arrived in.
    assert len(lines) == 2
    assert lines[0].startswith("Ada Moor") and "University of Sheffield" in lines[0]
    assert lines[1].startswith("Ben Hallam")
    assert question.suggestion_derivation == Derivation.ANSWER
    assert question.suggested_from == SUGGESTED_FROM_RESEARCHERS
    # Only offered: never written into the README.
    assert "Ada Moor" not in document.document_text


def test_a_creators_answer_given_elsewhere_comes_before_the_projects_people(
    runs_dir: Path,
) -> None:
    given = SharedAnswer(
        shared_field=SharedField.CREATORS,
        answer_text="The Moor team",
        answered_question="q-" + "3" * 16,
        answered_in=DocumentKind.METADATA_RECORD,
    )
    asked = sample("soil-survey.readme.draft.json").model_copy(
        update={
            "shared_answers": [given],
            "researchers": [kept("https://orcid.org/0000-0002-1825-0097", "Ada Moor")],
        }
    )
    question = by_target(template_draft(runs_dir, asked).document_questions)["Creators"]
    assert question.suggested_answer == "The Moor team"
    assert question.suggested_from == "metadata_record"


def test_no_named_researcher_leaves_the_creators_question_without_a_suggestion(
    runs_dir: Path,
) -> None:
    asked = sample("soil-survey.readme.draft.json").model_copy(
        update={"researchers": [kept("https://orcid.org/0000-0002-1825-0097", None)]}
    )
    question = by_target(template_draft(runs_dir, asked).document_questions)["Creators"]
    assert question.suggested_answer is None
